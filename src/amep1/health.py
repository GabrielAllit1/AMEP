from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

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

    def manual_isolate(self, source: str, isolated: bool = True) -> None:
        rec = self._record(source)
        rec.manual_isolated = isolated
        if isolated:
            rec.state = SensorHealth.ISOLATED
            rec.consecutive_probe_accepts = 0
        else:
            rec.state = SensorHealth.DEGRADED

    def may_fuse(self, source: str) -> bool:
        return self._record(source).state not in {SensorHealth.ISOLATED, SensorHealth.STALE}

    def observe(self, source: str, timestamp_s: float, result: MeasurementResult) -> SensorHealth:
        rec = self._record(source)
        if rec.last_seen_s is not None and timestamp_s < rec.last_seen_s:
            rec.state = SensorHealth.ISOLATED
            rec.consecutive_probe_accepts = 0
            return rec.state
        rec.last_seen_s = timestamp_s

        if rec.manual_isolated:
            rec.state = SensorHealth.ISOLATED
            return rec.state

        rec.recent_accepts.append(result.accepted)

        if rec.state == SensorHealth.ISOLATED:
            if result.accepted:
                rec.consecutive_probe_accepts += 1
                if rec.consecutive_probe_accepts >= rec.policy.recovery_consecutive_accepts:
                    rec.state = SensorHealth.DEGRADED
                    rec.consecutive_rejections = 0
                    rec.consecutive_probe_accepts = 0
            else:
                rec.consecutive_probe_accepts = 0
            return rec.state

        if result.accepted:
            rec.consecutive_rejections = 0
        else:
            rec.consecutive_rejections += 1
            if rec.consecutive_rejections >= rec.policy.isolate_after_consecutive_rejections:
                rec.state = SensorHealth.ISOLATED
                rec.consecutive_probe_accepts = 0
                return rec.state

        if len(rec.recent_accepts) >= rec.policy.min_window_samples:
            rejection_fraction = 1.0 - (sum(rec.recent_accepts) / len(rec.recent_accepts))
            if rejection_fraction > rec.policy.max_rejection_fraction:
                rec.state = SensorHealth.DEGRADED
                return rec.state

        rec.state = SensorHealth.ONLINE if result.accepted else SensorHealth.DEGRADED
        return rec.state

    def refresh(self, now_s: float) -> None:
        for rec in self._records.values():
            if rec.manual_isolated or rec.last_seen_s is None:
                continue
            if now_s - rec.last_seen_s > rec.policy.max_age_s:
                rec.state = SensorHealth.STALE

    def state(self, source: str) -> SensorHealth:
        return self._record(source).state

    def states(self) -> dict[str, SensorHealth]:
        return {name: rec.state for name, rec in self._records.items()}

    def source_ages(self, now_s: float) -> dict[str, float | None]:
        """Return age-of-data for every registered source in navigation-clock seconds."""
        now = float(now_s)
        return {
            name: None if rec.last_seen_s is None else max(0.0, now - rec.last_seen_s)
            for name, rec in self._records.items()
        }
