from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field

from .config import SourcePolicy
from .enums import SensorHealth
from .types import MeasurementResult


@dataclass
class SourceRecord:
    policy: SourcePolicy
    state: SensorHealth = SensorHealth.UNKNOWN
    last_seen_s: float | None = None
    consecutive_rejections: int = 0
    consecutive_probe_accepts: int = 0
    recent_accepts: deque[bool] = field(default_factory=deque)
    manual_isolated: bool = False

    def __post_init__(self) -> None:
        self.recent_accepts = deque(maxlen=self.policy.rejection_window)


class SensorHealthManager:
    def __init__(self) -> None:
        self._records: dict[str, SourceRecord] = {}

    def register(self, source: str, policy: SourcePolicy) -> None:
        if source in self._records:
            raise ValueError(f"source already registered: {source}")
        self._records[source] = SourceRecord(policy=policy)

    def _record(self, source: str) -> SourceRecord:
        try:
            return self._records[source]
        except KeyError as exc:
            raise KeyError(f"unregistered source: {source}") from exc

    def configuration(self) -> dict[str, dict[str, object]]:
        return {
            source: dict(asdict(record.policy))
            for source, record in sorted(self._records.items())
        }

    def manual_isolate(self, source: str, isolated: bool = True) -> None:
        record = self._record(source)
        record.manual_isolated = isolated
        if isolated:
            record.state = SensorHealth.ISOLATED
            record.consecutive_probe_accepts = 0
        else:
            record.state = SensorHealth.DEGRADED

    def may_fuse(self, source: str) -> bool:
        return self._record(source).state not in {
            SensorHealth.ISOLATED,
            SensorHealth.STALE,
        }

    def observe(
        self,
        source: str,
        timestamp_s: float,
        result: MeasurementResult,
    ) -> SensorHealth:
        record = self._record(source)
        if record.last_seen_s is not None and timestamp_s < record.last_seen_s:
            record.state = SensorHealth.ISOLATED
            record.consecutive_probe_accepts = 0
            return record.state
        record.last_seen_s = timestamp_s

        if record.manual_isolated:
            record.state = SensorHealth.ISOLATED
            return record.state

        record.recent_accepts.append(result.accepted)

        if record.state == SensorHealth.ISOLATED:
            if result.accepted:
                record.consecutive_probe_accepts += 1
                if (
                    record.consecutive_probe_accepts
                    >= record.policy.recovery_consecutive_accepts
                ):
                    record.state = SensorHealth.DEGRADED
                    record.consecutive_rejections = 0
                    record.consecutive_probe_accepts = 0
            else:
                record.consecutive_probe_accepts = 0
            return record.state

        if result.accepted:
            record.consecutive_rejections = 0
        else:
            record.consecutive_rejections += 1
            if (
                record.consecutive_rejections
                >= record.policy.isolate_after_consecutive_rejections
            ):
                record.state = SensorHealth.ISOLATED
                record.consecutive_probe_accepts = 0
                return record.state

        if len(record.recent_accepts) >= record.policy.min_window_samples:
            rejection_fraction = 1.0 - (
                sum(record.recent_accepts) / len(record.recent_accepts)
            )
            if rejection_fraction > record.policy.max_rejection_fraction:
                record.state = SensorHealth.DEGRADED
                return record.state

        record.state = (
            SensorHealth.ONLINE if result.accepted else SensorHealth.DEGRADED
        )
        return record.state

    def refresh(self, now_s: float) -> None:
        for record in self._records.values():
            if record.manual_isolated or record.last_seen_s is None:
                continue
            if now_s - record.last_seen_s > record.policy.max_age_s:
                record.state = SensorHealth.STALE

    def state(self, source: str) -> SensorHealth:
        return self._record(source).state

    def states(self) -> dict[str, SensorHealth]:
        return {name: record.state for name, record in self._records.items()}

    def source_ages(self, now_s: float) -> dict[str, float | None]:
        """Return age-of-data for every registered source in navigation-clock seconds."""
        now = float(now_s)
        return {
            name: (
                None
                if record.last_seen_s is None
                else max(0.0, now - record.last_seen_s)
            )
            for name, record in self._records.items()
        }
