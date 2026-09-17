from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
from scipy.stats import chi2

from .source_registry import SourceRegistry
from .time_alignment import AlignedMeasurement


@dataclass(frozen=True)
class SourceConflict:
    source_a: str
    source_b: str
    failure_domain_a: str
    failure_domain_b: str
    frame: str
    nis: float
    threshold: float
    time_separation_s: float


@dataclass(frozen=True)
class ConsistencyReport:
    checked_pairs: int
    conflicts: tuple[SourceConflict, ...]
    worst_nis: float | None
    threshold: float
    latched: bool = False
    recovery_consistent_checks: int = 0
    recovery_required_checks: int = 0

    @property
    def consistent(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True)
class ConsistencyPolicy:
    probability: float = 0.997
    max_time_separation_s: float = 0.10
    retention_s: float = 2.0
    recovery_consecutive_consistent_checks: int = 3

    def __post_init__(self) -> None:
        probability = float(self.probability)
        max_separation = float(self.max_time_separation_s)
        retention = float(self.retention_s)
        if not all(isfinite(value) for value in (probability, max_separation, retention)):
            raise ValueError("consistency policy values must be finite")
        if not 0.5 < probability < 1.0:
            raise ValueError("probability must be in (0.5, 1.0)")
        if max_separation < 0:
            raise ValueError("max_time_separation_s must be >= 0")
        if retention <= 0:
            raise ValueError("retention_s must be > 0")
        if self.recovery_consecutive_consistent_checks < 1:
            raise ValueError("recovery_consecutive_consistent_checks must be >= 1")


@dataclass(frozen=True)
class _AbsoluteObservation:
    source: str
    timestamp_s: float
    frame: str
    value: np.ndarray
    covariance: np.ndarray
    failure_domain: str
    integrity_dependencies: frozenset[str]


class CrossSourceConsistencyMonitor:
    """Near-synchronous consistency check across dependency-disjoint sources.

    Only observations in the same coordinate frame and with disjoint declared
    integrity dependencies are compared. Assessment and commit are separate so a
    contradiction is rejected before estimator mutation. Two-source disagreement
    is integrity evidence, not enough information to identify the faulty source.

    A detected contradiction is latched for integrity purposes. The latch clears
    only after the configured number of consecutive accepted observations each
    produces at least one dependency-disjoint consistent pair. Measurements may
    continue to be assessed while the latch is active so recovery evidence can be
    accumulated without silently restoring navigation authority on the first good
    sample.
    """

    def __init__(self, policy: ConsistencyPolicy | None = None) -> None:
        self.policy = policy or ConsistencyPolicy()
        self._latest: dict[str, _AbsoluteObservation] = {}
        self._latched_conflicts: tuple[SourceConflict, ...] = ()
        self._recovery_consistent_checks = 0
        self._last_report = self._empty_report()

    def _empty_report(self) -> ConsistencyReport:
        return ConsistencyReport(
            checked_pairs=0,
            conflicts=(),
            worst_nis=None,
            threshold=float(chi2.ppf(self.policy.probability, df=2)),
            latched=False,
            recovery_consistent_checks=0,
            recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
        )

    @property
    def last_report(self) -> ConsistencyReport:
        return self._last_report

    def _prune(self, now_s: float) -> None:
        stale = [
            source
            for source, observation in self._latest.items()
            if now_s - observation.timestamp_s > self.policy.retention_s
        ]
        for source in stale:
            self._latest.pop(source, None)

    def _candidate(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
    ) -> tuple[_AbsoluteObservation | None, ConsistencyReport]:
        envelope = aligned.envelope
        descriptor = registry.descriptor(envelope.source)
        threshold = float(chi2.ppf(self.policy.probability, df=2))
        if descriptor is None or not descriptor.absolute_position or not descriptor.safety_credit:
            return None, ConsistencyReport(
                0,
                (),
                None,
                threshold,
                recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
            )
        if envelope.kind != "position" or len(envelope.values) != 2:
            return None, ConsistencyReport(
                0,
                (),
                None,
                threshold,
                recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
            )

        value = np.asarray(envelope.values, dtype=float).reshape(2)
        covariance = np.asarray(envelope.covariance, dtype=float).reshape(2, 2)
        if not np.all(np.isfinite(value)) or not np.all(np.isfinite(covariance)):
            return None, ConsistencyReport(
                0,
                (),
                None,
                threshold,
                recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
            )

        self._prune(aligned.timestamp_s)
        conflicts: list[SourceConflict] = []
        checked = 0
        worst: float | None = None
        dependencies = descriptor.integrity_dependencies

        for other in self._latest.values():
            if other.source == envelope.source:
                continue
            if other.frame != envelope.frame:
                continue
            if other.integrity_dependencies.intersection(dependencies):
                # Shared dependencies mean the observations cannot be treated as
                # independent integrity evidence against each other.
                continue
            separation = abs(aligned.timestamp_s - other.timestamp_s)
            if separation > self.policy.max_time_separation_s:
                continue
            innovation = value - other.value
            S = covariance + other.covariance
            try:
                solved = np.linalg.solve(S, innovation)
            except np.linalg.LinAlgError:
                continue
            nis = float(innovation.T @ solved)
            if not isfinite(nis):
                continue
            checked += 1
            worst = nis if worst is None else max(worst, nis)
            if nis > threshold:
                conflicts.append(
                    SourceConflict(
                        source_a=other.source,
                        source_b=envelope.source,
                        failure_domain_a=other.failure_domain,
                        failure_domain_b=descriptor.failure_domain,
                        frame=envelope.frame,
                        nis=nis,
                        threshold=threshold,
                        time_separation_s=separation,
                    )
                )

        observation = _AbsoluteObservation(
            source=envelope.source,
            timestamp_s=aligned.timestamp_s,
            frame=envelope.frame,
            value=value.copy(),
            covariance=covariance.copy(),
            failure_domain=descriptor.failure_domain,
            integrity_dependencies=dependencies,
        )
        return observation, ConsistencyReport(
            checked_pairs=checked,
            conflicts=tuple(conflicts),
            worst_nis=worst,
            threshold=threshold,
            recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
        )

    def assess_position(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
    ) -> ConsistencyReport:
        _, report = self._candidate(aligned, registry)
        if not report.consistent:
            self.latch_conflict(report)
        return report

    def latch_conflict(self, report: ConsistencyReport) -> None:
        if report.consistent:
            raise ValueError("cannot latch a consistency report without conflicts")
        self._latched_conflicts = report.conflicts
        self._recovery_consistent_checks = 0
        self._last_report = ConsistencyReport(
            checked_pairs=report.checked_pairs,
            conflicts=report.conflicts,
            worst_nis=report.worst_nis,
            threshold=report.threshold,
            latched=True,
            recovery_consistent_checks=0,
            recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
        )

    def commit_position(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
        *,
        report: ConsistencyReport | None = None,
    ) -> None:
        observation, computed = self._candidate(aligned, registry)
        effective = computed if report is None else report
        if not effective.consistent:
            raise ValueError("cannot commit an inconsistent absolute observation")
        if observation is not None:
            self._latest[observation.source] = observation

        if self._latched_conflicts:
            if effective.checked_pairs > 0:
                self._recovery_consistent_checks += 1
            if (
                self._recovery_consistent_checks
                >= self.policy.recovery_consecutive_consistent_checks
            ):
                self._latched_conflicts = ()
                self._last_report = ConsistencyReport(
                    checked_pairs=effective.checked_pairs,
                    conflicts=(),
                    worst_nis=effective.worst_nis,
                    threshold=effective.threshold,
                    latched=False,
                    recovery_consistent_checks=self._recovery_consistent_checks,
                    recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
                )
                self._recovery_consistent_checks = 0
            else:
                self._last_report = ConsistencyReport(
                    checked_pairs=effective.checked_pairs,
                    conflicts=self._latched_conflicts,
                    worst_nis=self._last_report.worst_nis,
                    threshold=effective.threshold,
                    latched=True,
                    recovery_consistent_checks=self._recovery_consistent_checks,
                    recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
                )
        else:
            self._last_report = ConsistencyReport(
                checked_pairs=effective.checked_pairs,
                conflicts=(),
                worst_nis=effective.worst_nis,
                threshold=effective.threshold,
                latched=False,
                recovery_consistent_checks=0,
                recovery_required_checks=self.policy.recovery_consecutive_consistent_checks,
            )

    def observe_position(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
    ) -> ConsistencyReport:
        report = self.assess_position(aligned, registry)
        if report.consistent:
            self.commit_position(aligned, registry, report=report)
        return report
