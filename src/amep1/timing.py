from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class WatchdogResult:
    ok: bool
    interval_s: float | None
    expected_period_s: float
    period_error_s: float | None
    deadline_s: float
    reason: str


class DeadlineWatchdog:
    """Host-side interval/deadline observer for SIL and integration testing.

    It measures interval error against the declared period and rejects non-finite
    or non-monotonic timestamps. It is not a real-time scheduler or WCET proof.
    """

    def __init__(self, *, expected_period_s: float, deadline_s: float) -> None:
        if expected_period_s <= 0 or deadline_s <= 0:
            raise ValueError("period and deadline must be > 0")
        if deadline_s < expected_period_s:
            raise ValueError("deadline_s must be >= expected_period_s")
        self.expected_period_s = float(expected_period_s)
        self.deadline_s = float(deadline_s)
        self.last_t: float | None = None

    def observe(self, timestamp_s: float) -> WatchdogResult:
        timestamp = float(timestamp_s)
        if not isfinite(timestamp):
            return WatchdogResult(
                False,
                None,
                self.expected_period_s,
                None,
                self.deadline_s,
                "non_finite_time",
            )
        if self.last_t is None:
            self.last_t = timestamp
            return WatchdogResult(
                True,
                None,
                self.expected_period_s,
                None,
                self.deadline_s,
                "initialized",
            )

        interval = timestamp - self.last_t
        if interval <= 0:
            return WatchdogResult(
                False,
                interval,
                self.expected_period_s,
                interval - self.expected_period_s,
                self.deadline_s,
                "non_monotonic_time",
            )

        self.last_t = timestamp
        period_error = interval - self.expected_period_s
        if interval > self.deadline_s:
            return WatchdogResult(
                False,
                interval,
                self.expected_period_s,
                period_error,
                self.deadline_s,
                "deadline_missed",
            )
        reason = "on_period" if abs(period_error) <= 1e-12 else "within_deadline"
        return WatchdogResult(
            True,
            interval,
            self.expected_period_s,
            period_error,
            self.deadline_s,
            reason,
        )
