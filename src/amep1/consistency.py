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
    nis: float
    threshold: float
    time_separation_s: float


@dataclass(frozen=True)
class ConsistencyReport:
    checked_pairs: int
    conflicts: tuple[SourceConflict, ...]
    worst_nis: float | None
    threshold: float

    @property
    def consistent(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True)
class ConsistencyPolicy:
    probability: float = 0.997
    max_time_separation_s: float = 0.10
    retention_s: float = 2.0

    def __post_init__(self) -> None:
        if not 0.5 < self.probability < 1.0:
            raise ValueError("probability must be in (0.5, 1.0)")
        if self.max_time_separation_s < 0:
            raise ValueError("max_time_separation_s must be >= 0")
        if self.retention_s <= 0:
            raise ValueError("retention_s must be > 0")


@dataclass(frozen=True)
class _AbsoluteObservation:
    source: str
    timestamp_s: float
    value: np.ndarray
    covariance: np.ndarray
    failure_domain: str


class CrossSourceConsistencyMonitor:
    """Near-synchronous consistency check across declared independent sources.

    Assessment and commit are separate so a contradictory absolute fix can be
    rejected before it mutates either the estimator or the monitor history.
    The latched report is changed only by a detected conflict or a successfully
    committed observation; an EKF-rejected candidate cannot clear prior evidence.
    """

    def __init__(self, policy: ConsistencyPolicy | None = None) -> None:
        self.policy = policy or ConsistencyPolicy()
        self._latest: dict[str, _AbsoluteObservation] = {}
        self._last_report = ConsistencyReport(
            checked_pairs=0,
            conflicts=(),
            worst_nis=None,
            threshold=float(chi2.ppf(self.policy.probability, df=2)),
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
            return None, ConsistencyReport(0, (), None, threshold)
        if envelope.kind != "position" or len(envelope.values) != 2:
            return None, ConsistencyReport(0, (), None, threshold)

        value = np.asarray(envelope.values, dtype=float).reshape(2)
        covariance = np.asarray(envelope.covariance, dtype=float).reshape(2, 2)
        if not np.all(np.isfinite(value)) or not np.all(np.isfinite(covariance)):
            return None, ConsistencyReport(0, (), None, threshold)

        self._prune(aligned.timestamp_s)
        conflicts: list[SourceConflict] = []
        checked = 0
        worst: float | None = None
        for other in self._latest.values():
            if other.source == envelope.source:
                continue
            if other.failure_domain == descriptor.failure_domain:
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
                        nis=nis,
                        threshold=threshold,
                        time_separation_s=separation,
                    )
                )

        observation = _AbsoluteObservation(
            source=envelope.source,
            timestamp_s=aligned.timestamp_s,
            value=value.copy(),
            covariance=covariance.copy(),
            failure_domain=descriptor.failure_domain,
        )
        return observation, ConsistencyReport(
            checked_pairs=checked,
            conflicts=tuple(conflicts),
            worst_nis=worst,
            threshold=threshold,
        )

    def assess_position(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
    ) -> ConsistencyReport:
        _, report = self._candidate(aligned, registry)
        return report

    def latch_conflict(self, report: ConsistencyReport) -> None:
        if report.consistent:
            raise ValueError("cannot latch a consistency report without conflicts")
        self._last_report = report

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
            self._last_report = effective

    def observe_position(
        self,
        aligned: AlignedMeasurement,
        registry: SourceRegistry,
    ) -> ConsistencyReport:
        report = self.assess_position(aligned, registry)
        if report.consistent:
            self.commit_position(aligned, registry, report=report)
        else:
            self.latch_conflict(report)
        return report
