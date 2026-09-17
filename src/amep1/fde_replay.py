from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from .fde import (
    FaultHypothesis,
    RiskAllocation,
    SolutionCandidate,
    SolutionSeparationMonitor,
    SolutionSeparationReport,
    derive_fault_hypotheses,
)
from .math_utils import nearest_psd, symmetrize
from .replay import (
    DeterministicReplay,
    ReplayEvent,
    ReplayMeasurementEvent,
    ReplayResult,
)
from .runtime import AMEPRuntime
from .solution import PNTSolution

RuntimeFactory = Callable[[], AMEPRuntime]


@dataclass(frozen=True)
class HypothesisReplayResult:
    hypothesis: FaultHypothesis
    replay: ReplayResult
    excluded_measurement_events: int
    candidate: SolutionCandidate


@dataclass(frozen=True)
class MultiHypothesisReplayResult:
    """Primary replay, generated subset solutions, and separation decision."""

    primary: ReplayResult
    alternatives: tuple[HypothesisReplayResult, ...]
    risk_allocation: RiskAllocation
    separation: SolutionSeparationReport


def _horizontal_covariance(solution: PNTSolution) -> np.ndarray:
    labels = tuple(solution.covariance_labels)
    covariance = np.asarray(solution.covariance, dtype=float)
    if covariance.shape != (len(labels), len(labels)):
        raise ValueError("PNT solution covariance shape does not match covariance labels")

    index_pair: tuple[int, int] | None = None
    for east_label, north_label in (("E_m", "N_m"), ("dE_m", "dN_m")):
        if east_label in labels and north_label in labels:
            index_pair = (labels.index(east_label), labels.index(north_label))
            break
    if index_pair is None:
        raise ValueError(
            "PNT solution does not expose recognized horizontal position covariance labels"
        )

    horizontal = symmetrize(covariance[np.ix_(index_pair, index_pair)])
    if not np.all(np.isfinite(horizontal)):
        raise ValueError("horizontal solution covariance contains non-finite values")
    return nearest_psd(horizontal, 1e-15)


def _candidate(
    hypothesis: FaultHypothesis,
    replay: ReplayResult,
) -> SolutionCandidate:
    solution = replay.final_solution
    covariance = _horizontal_covariance(solution)
    return SolutionCandidate(
        hypothesis=hypothesis,
        horizontal_position_m=(float(solution.east_m), float(solution.north_m)),
        horizontal_covariance_m2=(
            (float(covariance[0, 0]), float(covariance[0, 1])),
            (float(covariance[1, 0]), float(covariance[1, 1])),
        ),
    )


def _shared_final_time(events: tuple[ReplayEvent, ...]) -> float:
    if not events:
        raise ValueError("multi-hypothesis replay requires at least one event")
    return max(
        float(event.arrival_time_s)
        if isinstance(event, ReplayMeasurementEvent)
        else float(event.timestamp_s)
        for event in events
    )


class MultiHypothesisReplay:
    """Generate FDE subset solutions by replaying the actual estimator/runtime path.

    For every declared fault hypothesis, measurements from the hypothesis' source
    set are removed while prediction events and all remaining measurements are
    replayed in the same receive-time/sequence order. This turns the existing
    estimator-independent solution-separation monitor into an executable SIL FDE
    campaign path instead of requiring callers to manufacture alternative
    solutions by hand.

    A fresh runtime must be returned on every ``runtime_factory`` call. The
    resulting separation statistic is still a research/SIL statistic: the
    existing monitor combines primary and subset covariances and does not claim a
    certified RAIM cross-covariance model or validated maritime protection level.
    """

    def __init__(
        self,
        runtime_factory: RuntimeFactory,
        *,
        monitor: SolutionSeparationMonitor | None = None,
    ) -> None:
        self.runtime_factory = runtime_factory
        self.monitor = monitor or SolutionSeparationMonitor()

    def run(
        self,
        events: Iterable[ReplayEvent],
        *,
        hypotheses: tuple[FaultHypothesis, ...] | None = None,
        safety_credit_only: bool = True,
        total_integrity_risk: float = 1e-3,
        residual_fraction: float = 0.10,
        final_now_s: float | None = None,
    ) -> MultiHypothesisReplayResult:
        event_tuple = tuple(events)
        shared_final_now = (
            _shared_final_time(event_tuple) if final_now_s is None else float(final_now_s)
        )
        if not np.isfinite(shared_final_now):
            raise ValueError("final_now_s must be finite")

        primary_runtime = self.runtime_factory()
        primary = DeterministicReplay().run(
            primary_runtime,
            event_tuple,
            final_now_s=shared_final_now,
        )

        active_sources = tuple(
            sorted(
                {
                    event.envelope.source
                    for event in event_tuple
                    if isinstance(event, ReplayMeasurementEvent)
                }
            )
        )
        selected_hypotheses = (
            derive_fault_hypotheses(
                primary_runtime.source_registry,
                active_sources,
                safety_credit_only=safety_credit_only,
            )
            if hypotheses is None
            else tuple(hypotheses)
        )
        if not selected_hypotheses:
            raise ValueError("no FDE fault hypotheses were available for replay")

        allocation = RiskAllocation.equal(
            selected_hypotheses,
            total_integrity_risk=total_integrity_risk,
            residual_fraction=residual_fraction,
        )

        alternatives: list[HypothesisReplayResult] = []
        candidates: list[SolutionCandidate] = []
        for hypothesis in selected_hypotheses:
            excluded = set(hypothesis.excluded_sources)
            filtered_events = tuple(
                event
                for event in event_tuple
                if not (
                    isinstance(event, ReplayMeasurementEvent)
                    and event.envelope.source in excluded
                )
            )
            excluded_count = sum(
                1
                for event in event_tuple
                if isinstance(event, ReplayMeasurementEvent)
                and event.envelope.source in excluded
            )
            runtime = self.runtime_factory()
            replay = DeterministicReplay().run(
                runtime,
                filtered_events,
                final_now_s=shared_final_now,
            )
            candidate = _candidate(hypothesis, replay)
            candidates.append(candidate)
            alternatives.append(
                HypothesisReplayResult(
                    hypothesis=hypothesis,
                    replay=replay,
                    excluded_measurement_events=excluded_count,
                    candidate=candidate,
                )
            )

        primary_covariance = _horizontal_covariance(primary.final_solution)
        separation = self.monitor.evaluate(
            primary_position_m=(
                float(primary.final_solution.east_m),
                float(primary.final_solution.north_m),
            ),
            primary_covariance_m2=(
                (
                    float(primary_covariance[0, 0]),
                    float(primary_covariance[0, 1]),
                ),
                (
                    float(primary_covariance[1, 0]),
                    float(primary_covariance[1, 1]),
                ),
            ),
            alternatives=tuple(candidates),
            risk_allocation=allocation,
        )
        return MultiHypothesisReplayResult(
            primary=primary,
            alternatives=tuple(alternatives),
            risk_allocation=allocation,
            separation=separation,
        )
