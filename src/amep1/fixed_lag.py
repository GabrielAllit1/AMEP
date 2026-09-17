from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from typing import Any

import numpy as np

from .backend import EstimatorBackend, EstimatorSnapshot
from .types import MeasurementResult


class FixedLagWindowError(RuntimeError):
    pass


@dataclass(frozen=True)
class DelayedMeasurement:
    kind: str
    values: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    frame: str
    source: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    allow_fusion: bool = True

    def validate(self) -> None:
        if not self.kind or not self.source or not self.frame:
            raise ValueError("delayed measurement kind/source/frame must be non-empty")
        values = np.asarray(self.values, dtype=float)
        covariance = np.asarray(self.covariance, dtype=float)
        if values.ndim != 1 or values.size == 0:
            raise ValueError("delayed measurement values must be a non-empty vector")
        if covariance.shape != (values.size, values.size):
            raise ValueError("delayed measurement covariance dimension mismatch")
        if not np.all(np.isfinite(values)) or not np.all(np.isfinite(covariance)):
            raise ValueError("delayed measurement contains non-finite values")


@dataclass(frozen=True)
class FixedLagOptimizationResult:
    applied_delayed_measurements: int
    replayed_events: int
    oldest_retained_timestamp_s: float | None
    newest_timestamp_s: float | None
    delayed_results: tuple[MeasurementResult, ...]


@dataclass(frozen=True)
class _PredictionEvent:
    sequence: int
    timestamp_s: float
    prediction_input: object


@dataclass(frozen=True)
class _MeasurementEvent:
    sequence: int
    timestamp_s: float
    measurement: DelayedMeasurement
    delayed: bool = False


_HistoryEvent = _PredictionEvent | _MeasurementEvent


class FixedLagBackendAdapter:
    """Deterministic bounded-lag rewind/replay adapter for an EstimatorBackend.

    This adapter is intentionally independent of one estimator state layout. It
    keeps a deep-copy checkpoint representing all events older than the lag
    horizon and replays retained predictions/measurements in navigation-time
    order when a delayed measurement arrives.

    Backend state must be deepcopy-compatible. This is suitable for research,
    replay, radar/vision/bathymetry latency experiments, and integration tests.
    It is not a factor graph, real-time smoother, or target-hardware timing
    guarantee.
    """

    timestamp_metadata_key = "normalized_timestamp_s"

    def __init__(
        self,
        backend: EstimatorBackend,
        *,
        lag_s: float = 5.0,
        max_events: int = 100_000,
    ) -> None:
        if lag_s <= 0:
            raise ValueError("lag_s must be > 0")
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        self._backend = backend
        self.lag_s = float(lag_s)
        self.max_events = int(max_events)
        self._origin: EstimatorBackend = deepcopy(backend)
        self._origin_time_s = None if backend.last_t is None else float(backend.last_t)
        self._history: list[_HistoryEvent] = []
        self._pending: list[_MeasurementEvent] = []
        self._sequence = 0

    @property
    def backend(self) -> EstimatorBackend:
        return self._backend

    @property
    def last_t(self) -> float | None:
        return self._backend.last_t

    @property
    def measurement_kinds(self) -> tuple[str, ...]:
        return self._backend.measurement_kinds

    @property
    def accepted_frames(self) -> tuple[str, ...]:
        return self._backend.accepted_frames

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    @staticmethod
    def _event_key(event: _HistoryEvent) -> tuple[float, int]:
        return float(event.timestamp_s), int(event.sequence)

    @staticmethod
    def _prediction_timestamp(prediction_input: object, backend: EstimatorBackend) -> float:
        timestamp = getattr(prediction_input, "timestamp_s", None)
        if timestamp is None:
            timestamp = backend.last_t
        if timestamp is None:
            raise ValueError("prediction input/backend does not expose a timestamp")
        value = float(timestamp)
        if not isfinite(value):
            raise ValueError("prediction timestamp must be finite")
        return value

    def _measurement_timestamp(
        self,
        metadata: Mapping[str, object] | None,
    ) -> float:
        timestamp: object | None = None
        if metadata is not None:
            timestamp = metadata.get(self.timestamp_metadata_key)
        if timestamp is None:
            timestamp = self._backend.last_t
        if timestamp is None:
            raise ValueError(
                f"measurement metadata must contain {self.timestamp_metadata_key!r} "
                "before the first prediction"
            )
        if not isinstance(timestamp, Real):
            raise TypeError("measurement timestamp must be a real number")
        value = float(timestamp)
        if not isfinite(value):
            raise ValueError("measurement timestamp must be finite")
        return value

    def _ensure_capacity(self, additional: int = 1) -> None:
        if len(self._history) + len(self._pending) + additional > self.max_events:
            raise FixedLagWindowError(
                "fixed-lag event capacity exceeded; reduce lag/rate or increase max_events"
            )

    def predict(self, prediction_input: object) -> float:
        dt = self._backend.predict(prediction_input)
        timestamp = self._prediction_timestamp(prediction_input, self._backend)
        self._compact(timestamp)
        self._ensure_capacity()
        self._history.append(
            _PredictionEvent(
                self._next_sequence(),
                timestamp,
                deepcopy(prediction_input),
            )
        )
        return dt

    def update_measurement(
        self,
        kind: str,
        values: np.ndarray,
        covariance: np.ndarray,
        *,
        frame: str,
        source: str,
        metadata: Mapping[str, object] | None = None,
        allow_fusion: bool = True,
    ) -> MeasurementResult:
        timestamp = self._measurement_timestamp(metadata)
        if self.last_t is not None and timestamp < float(self.last_t) - 1e-12:
            raise FixedLagWindowError(
                "out-of-sequence measurement requires ingest_delayed()"
            )
        result = self._backend.update_measurement(
            kind,
            np.asarray(values, dtype=float),
            np.asarray(covariance, dtype=float),
            frame=frame,
            source=source,
            metadata=metadata,
            allow_fusion=allow_fusion,
        )
        if self.last_t is not None:
            self._compact(float(self.last_t))
        self._ensure_capacity()
        measurement = DelayedMeasurement(
            kind=kind,
            values=tuple(float(value) for value in np.asarray(values, dtype=float)),
            covariance=tuple(
                tuple(float(value) for value in row)
                for row in np.asarray(covariance, dtype=float)
            ),
            frame=frame,
            source=source,
            metadata={} if metadata is None else dict(metadata),
            allow_fusion=allow_fusion,
        )
        measurement.validate()
        self._history.append(
            _MeasurementEvent(
                self._next_sequence(),
                timestamp,
                measurement,
                delayed=False,
            )
        )
        return result

    def _payload_to_measurement(
        self,
        *,
        source: str,
        payload: object,
    ) -> DelayedMeasurement:
        if isinstance(payload, DelayedMeasurement):
            measurement = payload
        elif isinstance(payload, Mapping):
            measurement = DelayedMeasurement(
                kind=str(payload["kind"]),
                values=tuple(float(value) for value in payload["values"]),
                covariance=tuple(
                    tuple(float(value) for value in row)
                    for row in payload["covariance"]
                ),
                frame=str(payload.get("frame", "local_ENU")),
                source=str(payload.get("source", source)),
                metadata=dict(payload.get("metadata", {})),
                allow_fusion=bool(payload.get("allow_fusion", True)),
            )
        else:
            raise TypeError(
                "payload must be DelayedMeasurement or a compatible mapping"
            )
        if measurement.source != source:
            raise ValueError("delayed measurement source argument/payload mismatch")
        measurement.validate()
        return measurement

    def ingest_delayed(
        self,
        *,
        source: str,
        timestamp_s: float,
        payload: object,
    ) -> None:
        timestamp = float(timestamp_s)
        if not isfinite(timestamp):
            raise ValueError("delayed timestamp must be finite")
        if self.last_t is None:
            raise FixedLagWindowError("cannot ingest delayed data before prediction")
        newest = float(self.last_t)
        if timestamp > newest + 1e-12:
            raise FixedLagWindowError("delayed measurement timestamp is in the future")
        if timestamp < newest - self.lag_s:
            raise FixedLagWindowError("delayed measurement falls outside fixed-lag window")
        if self._origin_time_s is not None and timestamp <= self._origin_time_s:
            raise FixedLagWindowError("delayed measurement predates retained replay checkpoint")

        measurement = self._payload_to_measurement(source=source, payload=payload)
        self._ensure_capacity()
        self._pending.append(
            _MeasurementEvent(
                self._next_sequence(),
                timestamp,
                measurement,
                delayed=True,
            )
        )

    @staticmethod
    def _apply_event(
        backend: EstimatorBackend,
        event: _HistoryEvent,
    ) -> MeasurementResult | None:
        if isinstance(event, _PredictionEvent):
            backend.predict(deepcopy(event.prediction_input))
            return None
        measurement = event.measurement
        metadata = dict(measurement.metadata)
        metadata[FixedLagBackendAdapter.timestamp_metadata_key] = float(event.timestamp_s)
        return backend.update_measurement(
            measurement.kind,
            np.asarray(measurement.values, dtype=float),
            np.asarray(measurement.covariance, dtype=float),
            frame=measurement.frame,
            source=measurement.source,
            metadata=metadata,
            allow_fusion=measurement.allow_fusion,
        )

    def _replay(
        self,
        events: list[_HistoryEvent],
    ) -> tuple[EstimatorBackend, dict[int, MeasurementResult]]:
        backend = deepcopy(self._origin)
        results: dict[int, MeasurementResult] = {}
        for event in sorted(events, key=self._event_key):
            result = self._apply_event(backend, event)
            if result is not None:
                results[event.sequence] = result
        return backend, results

    def optimize(self, *, now_s: float) -> FixedLagOptimizationResult:
        now = float(now_s)
        if not isfinite(now):
            raise ValueError("now_s must be finite")
        if self.last_t is not None and now < float(self.last_t) - self.lag_s:
            raise FixedLagWindowError("optimization time predates retained fixed-lag window")

        if not self._pending:
            self._compact(now)
            timestamps = [event.timestamp_s for event in self._history]
            return FixedLagOptimizationResult(
                applied_delayed_measurements=0,
                replayed_events=0,
                oldest_retained_timestamp_s=min(timestamps) if timestamps else None,
                newest_timestamp_s=self.last_t,
                delayed_results=(),
            )

        delayed_sequences = {event.sequence for event in self._pending}
        combined = [*self._history, *self._pending]
        if len(combined) > self.max_events:
            raise FixedLagWindowError("fixed-lag event capacity exceeded during optimize")

        rebuilt, results = self._replay(combined)
        self._backend = rebuilt
        self._history = combined
        delayed_results = tuple(
            results[sequence]
            for sequence in sorted(delayed_sequences)
            if sequence in results
        )
        applied = len(self._pending)
        self._pending.clear()
        self._compact(now)

        timestamps = [event.timestamp_s for event in self._history]
        return FixedLagOptimizationResult(
            applied_delayed_measurements=applied,
            replayed_events=len(combined),
            oldest_retained_timestamp_s=min(timestamps) if timestamps else None,
            newest_timestamp_s=self.last_t,
            delayed_results=delayed_results,
        )

    def _compact(self, now_s: float) -> None:
        if self._pending or not self._history:
            return
        cutoff = float(now_s) - self.lag_s
        old = [event for event in self._history if event.timestamp_s <= cutoff]
        if not old:
            return

        old_ids = {event.sequence for event in old}
        base = deepcopy(self._origin)
        for event in sorted(old, key=self._event_key):
            self._apply_event(base, event)
        self._origin = base
        self._origin_time_s = max(event.timestamp_s for event in old)
        self._history = [
            event for event in self._history if event.sequence not in old_ids
        ]

    def snapshot(self) -> EstimatorSnapshot:
        return self._backend.snapshot()

    def containment_proxy(self) -> float:
        return self._backend.containment_proxy()

    def configuration(self) -> dict[str, Any]:
        return {
            "lag_s": self.lag_s,
            "max_events": self.max_events,
            "timestamp_metadata_key": self.timestamp_metadata_key,
            "wrapped_backend_type": (
                f"{type(self._backend).__module__}.{type(self._backend).__qualname__}"
            ),
        }
