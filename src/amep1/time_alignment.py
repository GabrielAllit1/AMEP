from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping

from .types import MeasurementResult


@dataclass(frozen=True)
class MeasurementEnvelope:
    """Transport-neutral sensor measurement contract before estimator fusion.

    Timestamps are explicit so integrations can preserve source time, receive time,
    clock-domain provenance, transport latency, and timestamp uncertainty instead
    of collapsing all measurements onto callback arrival time.
    """

    source: str
    kind: str
    source_timestamp_s: float
    receive_timestamp_s: float
    values: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    frame: str = "local_ENU"
    clock_domain: str = "navigation"
    sequence: int | None = None
    valid: bool = True
    provenance: str | None = None
    timestamp_uncertainty_s: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source must be non-empty")
        if not self.kind:
            raise ValueError("kind must be non-empty")
        if not self.clock_domain:
            raise ValueError("clock_domain must be non-empty")
        if not self.frame:
            raise ValueError("frame must be non-empty")
        scalars = (
            float(self.source_timestamp_s),
            float(self.receive_timestamp_s),
            float(self.timestamp_uncertainty_s),
            *(float(v) for v in self.values),
            *(float(v) for row in self.covariance for v in row),
        )
        if not all(isfinite(v) for v in scalars):
            raise ValueError("measurement envelope contains non-finite numeric data")
        if self.timestamp_uncertainty_s < 0:
            raise ValueError("timestamp_uncertainty_s must be >= 0")
        n = len(self.values)
        if n == 0:
            raise ValueError("values must be non-empty")
        if len(self.covariance) != n or any(len(row) != n for row in self.covariance):
            raise ValueError(f"covariance must have shape {(n, n)}")


@dataclass(frozen=True)
class ClockDomain:
    offset_to_navigation_s: float = 0.0
    uncertainty_s: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.offset_to_navigation_s) or not isfinite(self.uncertainty_s):
            raise ValueError("clock-domain parameters must be finite")
        if self.uncertainty_s < 0:
            raise ValueError("clock-domain uncertainty_s must be >= 0")


@dataclass(frozen=True)
class TimeAlignmentPolicy:
    max_transport_latency_s: float = 2.0
    max_measurement_age_s: float = 5.0
    max_future_skew_s: float = 0.050
    reject_out_of_order: bool = True

    def __post_init__(self) -> None:
        if self.max_transport_latency_s <= 0:
            raise ValueError("max_transport_latency_s must be > 0")
        if self.max_measurement_age_s <= 0:
            raise ValueError("max_measurement_age_s must be > 0")
        if self.max_future_skew_s < 0:
            raise ValueError("max_future_skew_s must be >= 0")


@dataclass(frozen=True)
class AlignedMeasurement:
    envelope: MeasurementEnvelope
    timestamp_s: float
    timestamp_uncertainty_s: float
    transport_latency_s: float
    age_s: float


@dataclass(frozen=True)
class TimeAlignmentResult:
    accepted: bool
    reason: str
    measurement: AlignedMeasurement | None = None


@dataclass(frozen=True)
class IngestResult:
    accepted: bool
    reason: str
    alignment: TimeAlignmentResult
    measurement_result: MeasurementResult | None


class TimeAligner:
    """Normalize sensor timestamps into the navigation clock domain.

    This initial implementation deliberately rejects delayed/out-of-order samples
    that the current real-time EKF cannot rewind for. A future fixed-lag smoother
    or delayed-state update can relax that policy without changing the envelope.

    `align(..., commit=False)` provides a two-phase path for runtimes that must
    finish frame/kind validation before advancing a source ordering watermark.
    """

    def __init__(self, policy: TimeAlignmentPolicy | None = None) -> None:
        self.policy = policy or TimeAlignmentPolicy()
        self._domains: dict[str, ClockDomain] = {"navigation": ClockDomain()}
        self._last_timestamp_by_source: dict[str, float] = {}

    def register_clock_domain(
        self,
        name: str,
        *,
        offset_to_navigation_s: float = 0.0,
        uncertainty_s: float = 0.0,
    ) -> None:
        if not name:
            raise ValueError("clock-domain name must be non-empty")
        self._domains[name] = ClockDomain(offset_to_navigation_s, uncertainty_s)

    def commit(self, measurement: AlignedMeasurement) -> None:
        """Advance a source ordering watermark after downstream contract validation."""
        source = measurement.envelope.source
        last = self._last_timestamp_by_source.get(source)
        if last is None or measurement.timestamp_s >= last:
            self._last_timestamp_by_source[source] = float(measurement.timestamp_s)

    def align(
        self,
        envelope: MeasurementEnvelope,
        *,
        now_s: float | None = None,
        commit: bool = True,
    ) -> TimeAlignmentResult:
        try:
            envelope.validate()
        except ValueError as exc:
            return TimeAlignmentResult(False, f"invalid_envelope:{exc}")

        if not envelope.valid:
            return TimeAlignmentResult(False, "source_marked_invalid")

        domain = self._domains.get(envelope.clock_domain)
        if domain is None:
            return TimeAlignmentResult(False, "unknown_clock_domain")

        timestamp_s = float(envelope.source_timestamp_s + domain.offset_to_navigation_s)
        receive_s = float(envelope.receive_timestamp_s)
        now = receive_s if now_s is None else float(now_s)
        if not isfinite(now):
            return TimeAlignmentResult(False, "non_finite_now")

        latency_s = receive_s - timestamp_s
        if latency_s < -self.policy.max_future_skew_s:
            return TimeAlignmentResult(False, "source_time_ahead_of_receive_time")
        if latency_s > self.policy.max_transport_latency_s:
            return TimeAlignmentResult(False, "transport_latency_exceeded")

        age_s = now - timestamp_s
        if age_s < -self.policy.max_future_skew_s:
            return TimeAlignmentResult(False, "measurement_from_future")
        if age_s > self.policy.max_measurement_age_s:
            return TimeAlignmentResult(False, "measurement_too_old")

        last = self._last_timestamp_by_source.get(envelope.source)
        if self.policy.reject_out_of_order and last is not None and timestamp_s < last:
            return TimeAlignmentResult(False, "out_of_order_measurement")

        uncertainty_s = float(envelope.timestamp_uncertainty_s + domain.uncertainty_s)
        aligned = AlignedMeasurement(
            envelope=envelope,
            timestamp_s=timestamp_s,
            timestamp_uncertainty_s=uncertainty_s,
            transport_latency_s=latency_s,
            age_s=max(0.0, age_s),
        )
        if commit:
            self.commit(aligned)
        return TimeAlignmentResult(True, "aligned", aligned)
