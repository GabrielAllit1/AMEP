from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .evidence import EvidenceLog
from .runtime import AMEPRuntime
from .solution import PNTSolution
from .time_alignment import IngestResult, MeasurementEnvelope
from .types import HorizontalIMUInput


@dataclass(frozen=True)
class ReplayIMUEvent:
    sequence: int
    input: HorizontalIMUInput

    @property
    def timestamp_s(self) -> float:
        return float(self.input.timestamp_s)


@dataclass(frozen=True)
class ReplayMeasurementEvent:
    sequence: int
    envelope: MeasurementEnvelope

    @property
    def timestamp_s(self) -> float:
        return float(self.envelope.source_timestamp_s)


ReplayEvent = ReplayIMUEvent | ReplayMeasurementEvent


@dataclass(frozen=True)
class ReplayResult:
    events_processed: int
    imu_events: int
    measurement_events: int
    accepted_measurements: int
    rejected_measurements: int
    rejection_reasons: tuple[str, ...]
    final_solution: PNTSolution
    evidence: tuple[object, ...]


class DeterministicReplay:
    """Deterministic software replay for estimator/integrity experiments.

    Events are ordered by ``(timestamp_s, sequence)``. The explicit sequence is
    required to make equal-timestamp ordering reproducible across platforms.
    Replay evidence starts with the source-registry fingerprint so results are
    bound to the declared dependency/failure-domain configuration.
    """

    def __init__(self, *, evidence_log: EvidenceLog | None = None) -> None:
        self.evidence_log = evidence_log or EvidenceLog()

    def run(
        self,
        runtime: AMEPRuntime,
        events: Iterable[ReplayEvent],
        *,
        final_now_s: float | None = None,
    ) -> ReplayResult:
        ordered = sorted(events, key=lambda event: (event.timestamp_s, event.sequence))
        self.evidence_log.append(
            "replay_configuration",
            timestamp_s=None,
            payload={
                "event_count": len(ordered),
                "source_registry_sha256": runtime.source_registry.fingerprint(),
            },
        )
        seen_sequences: set[int] = set()
        imu_count = 0
        measurement_count = 0
        accepted = 0
        rejected = 0
        rejection_reasons: list[str] = []

        for event in ordered:
            if event.sequence in seen_sequences:
                raise ValueError(f"duplicate replay sequence: {event.sequence}")
            seen_sequences.add(event.sequence)

            if isinstance(event, ReplayIMUEvent):
                dt = runtime.predict(event.input)
                imu_count += 1
                self.evidence_log.append(
                    "imu_predict",
                    timestamp_s=event.timestamp_s,
                    payload={
                        "sequence": event.sequence,
                        "dt_s": float(dt),
                        "a_fwd_mps2": float(event.input.a_fwd_mps2),
                        "a_stbd_mps2": float(event.input.a_stbd_mps2),
                        "yaw_rate_rps": float(event.input.yaw_rate_rps),
                    },
                )
                continue

            measurement_count += 1
            result: IngestResult = runtime.ingest_measurement(
                event.envelope,
                now_s=event.envelope.receive_timestamp_s,
            )
            if result.accepted:
                accepted += 1
            else:
                rejected += 1
                rejection_reasons.append(result.reason)
            self.evidence_log.append(
                "measurement_ingest",
                timestamp_s=event.timestamp_s,
                payload={
                    "sequence": event.sequence,
                    "source": event.envelope.source,
                    "kind": event.envelope.kind,
                    "accepted": bool(result.accepted),
                    "reason": result.reason,
                },
            )

        if final_now_s is None:
            final_now_s = ordered[-1].timestamp_s if ordered else runtime.estimator.last_t
        solution = runtime.pnt_solution(final_now_s)
        self.evidence_log.append(
            "final_solution",
            timestamp_s=solution.timestamp_s,
            payload={
                "mode": solution.mode.value,
                "integrity_status": solution.integrity_status.value,
                "information_rank": solution.information_rank,
                "east_m": float(solution.east_m),
                "north_m": float(solution.north_m),
                "protection_bound_validated": bool(solution.protection_bound_validated),
            },
        )
        return ReplayResult(
            events_processed=len(ordered),
            imu_events=imu_count,
            measurement_events=measurement_count,
            accepted_measurements=accepted,
            rejected_measurements=rejected,
            rejection_reasons=tuple(rejection_reasons),
            final_solution=solution,
            evidence=self.evidence_log.records(),
        )
