from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Iterable

from .evidence import EvidenceLog, EvidenceRecord, JSONValue
from .runtime import AMEPRuntime
from .solution import PNTSolution
from .time_alignment import IngestResult, MeasurementEnvelope
from .types import HorizontalIMUInput


@dataclass(frozen=True)
class ReplayPredictionEvent:
    """Platform-neutral prediction event with an explicit processing timestamp."""

    sequence: int
    timestamp_s: float
    input: object


@dataclass(frozen=True)
class ReplayIMUEvent:
    """Compatibility event for the current maritime ``HorizontalIMUInput``."""

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
    def arrival_time_s(self) -> float:
        """Recorded arrival time used to reproduce online processing order."""
        return float(self.envelope.receive_timestamp_s)


ReplayEvent = ReplayPredictionEvent | ReplayIMUEvent | ReplayMeasurementEvent


@dataclass(frozen=True)
class ReplayResult:
    events_processed: int
    prediction_events: int
    measurement_events: int
    ingest_accepted_measurements: int
    estimator_accepted_measurements: int
    fused_measurements: int
    contract_rejected_measurements: int
    estimator_rejected_measurements: int
    rejection_reasons: tuple[str, ...]
    final_solution: PNTSolution
    evidence: tuple[EvidenceRecord, ...]


def _event_arrival_time(event: ReplayEvent) -> float:
    if isinstance(event, ReplayMeasurementEvent):
        return event.arrival_time_s
    return float(event.timestamp_s)


def _prediction_payload(prediction_input: object) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "input_type": (
            f"{type(prediction_input).__module__}."
            f"{type(prediction_input).__qualname__}"
        )
    }
    if not is_dataclass(prediction_input) or isinstance(prediction_input, type):
        return payload

    for key, value in asdict(prediction_input).items():
        if value is None or isinstance(value, (str, int, float, bool)):
            payload[key] = value
    return payload


class DeterministicReplay:
    """Deterministic replay through the online AMEP runtime.

    Measurement events are processed in recorded receive-time order rather than
    raw source-clock order. Source timestamps are normalized and validated by the
    same ``TimeAligner`` used online. Equal-arrival-time ordering is resolved by
    the explicit replay sequence.
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
        if self.evidence_log.records():
            raise ValueError("replay evidence log must be empty at run start")

        ordered = sorted(
            events,
            key=lambda event: (_event_arrival_time(event), event.sequence),
        )
        configuration = runtime.configuration_manifest()
        configuration_sha256 = runtime.configuration_fingerprint()
        self.evidence_log.append(
            "replay_configuration",
            timestamp_s=None,
            payload={
                "event_count": len(ordered),
                "configuration_sha256": configuration_sha256,
                "configuration": configuration,
            },
        )

        seen_sequences: set[int] = set()
        prediction_count = 0
        measurement_count = 0
        ingest_accepted = 0
        estimator_accepted = 0
        fused = 0
        contract_rejected = 0
        estimator_rejected = 0
        rejection_reasons: list[str] = []

        for event in ordered:
            if event.sequence in seen_sequences:
                raise ValueError(f"duplicate replay sequence: {event.sequence}")
            seen_sequences.add(event.sequence)

            if isinstance(event, ReplayMeasurementEvent):
                measurement_count += 1
                result: IngestResult = runtime.ingest_measurement(
                    event.envelope,
                    now_s=event.envelope.receive_timestamp_s,
                )
                if not result.accepted:
                    contract_rejected += 1
                    rejection_reasons.append(result.reason)
                else:
                    ingest_accepted += 1
                    measurement_result = result.measurement_result
                    if measurement_result is None:
                        raise RuntimeError(
                            "accepted ingest result must include measurement_result"
                        )
                    if measurement_result.accepted:
                        estimator_accepted += 1
                        if measurement_result.fused:
                            fused += 1
                    else:
                        estimator_rejected += 1
                        rejection_reasons.append(measurement_result.reason)

                normalized_timestamp = (
                    None
                    if result.alignment.measurement is None
                    else float(result.alignment.measurement.timestamp_s)
                )
                self.evidence_log.append(
                    "measurement_ingest",
                    timestamp_s=event.arrival_time_s,
                    payload={
                        "sequence": event.sequence,
                        "source": event.envelope.source,
                        "kind": event.envelope.kind,
                        "source_timestamp_s": float(event.envelope.source_timestamp_s),
                        "receive_timestamp_s": float(event.envelope.receive_timestamp_s),
                        "normalized_timestamp_s": normalized_timestamp,
                        "ingest_accepted": bool(result.accepted),
                        "estimator_accepted": (
                            None
                            if result.measurement_result is None
                            else bool(result.measurement_result.accepted)
                        ),
                        "fused": (
                            None
                            if result.measurement_result is None
                            else bool(result.measurement_result.fused)
                        ),
                        "reason": result.reason,
                    },
                )
                continue

            prediction_input = event.input
            dt = runtime.predict(prediction_input)
            prediction_count += 1
            payload = _prediction_payload(prediction_input)
            payload["sequence"] = event.sequence
            payload["dt_s"] = float(dt)
            self.evidence_log.append(
                "prediction",
                timestamp_s=float(event.timestamp_s),
                payload=payload,
            )

        if final_now_s is None:
            final_now_s = (
                _event_arrival_time(ordered[-1])
                if ordered
                else runtime.estimator.last_t
            )
        solution = runtime.pnt_solution(final_now_s)
        self.evidence_log.append(
            "final_solution",
            timestamp_s=solution.timestamp_s,
            payload={
                "mode": solution.mode.value,
                "integrity_status": solution.integrity_status.value,
                "information_rank": solution.information_rank,
                "state_schema_id": solution.state_schema_id,
                "east_m": float(solution.east_m),
                "north_m": float(solution.north_m),
                "protection_bound_validated": bool(
                    solution.protection_bound_validated
                ),
            },
        )
        return ReplayResult(
            events_processed=len(ordered),
            prediction_events=prediction_count,
            measurement_events=measurement_count,
            ingest_accepted_measurements=ingest_accepted,
            estimator_accepted_measurements=estimator_accepted,
            fused_measurements=fused,
            contract_rejected_measurements=contract_rejected,
            estimator_rejected_measurements=estimator_rejected,
            rejection_reasons=tuple(rejection_reasons),
            final_solution=solution,
            evidence=self.evidence_log.records(),
        )
