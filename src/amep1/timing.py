from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchdogResult:
    ok: bool
    interval_s: float | None
    deadline_s: float
    reason: str


class DeadlineWatchdog:
    def __init__(self, *, expected_period_s: float, deadline_s: float) -> None:
        if expected_period_s <= 0 or deadline_s <= 0:
            raise ValueError("period and deadline must be > 0")
        if deadline_s < expected_period_s:
            raise ValueError("deadline_s must be >= expected_period_s")
        self.expected_period_s = float(expected_period_s)
        self.deadline_s = float(deadline_s)
        self.last_t: float | None = None

    def observe(self, timestamp_s: float) -> WatchdogResult:
        timestamp_s = float(timestamp_s)
        if self.last_t is None:
            self.last_t = timestamp_s
            return WatchdogResult(True, None, self.deadline_s, "initialized")
        dt = timestamp_s - self.last_t
        if dt <= 0:
            return WatchdogResult(False, dt, self.deadline_s, "non_monotonic_time")
        self.last_t = timestamp_s
        if dt > self.deadline_s:
            return WatchdogResult(False, dt, self.deadline_s, "deadline_missed")
        return WatchdogResult(True, dt, self.deadline_s, "within_deadline")
