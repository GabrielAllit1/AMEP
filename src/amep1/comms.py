from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class LinkPolicy:
    priority: int
    max_heartbeat_age_s: float
    max_future_skew_s: float = 0.050

    def __post_init__(self) -> None:
        heartbeat_age = float(self.max_heartbeat_age_s)
        future_skew = float(self.max_future_skew_s)
        if self.priority < 0:
            raise ValueError("priority must be >= 0")
        if not isfinite(heartbeat_age) or heartbeat_age <= 0:
            raise ValueError("max_heartbeat_age_s must be finite and > 0")
        if not isfinite(future_skew) or future_skew < 0:
            raise ValueError("max_future_skew_s must be finite and >= 0")


@dataclass
class LinkRecord:
    policy: LinkPolicy
    last_heartbeat_s: float | None = None
    enabled: bool = True


class CommunicationsSupervisor:
    """Deterministic heartbeat freshness selector for command-link metadata.

    This class does not implement transport, authentication, encryption, RF
    control, or command validation. It only selects among already-established
    links using declared heartbeat timing and priority.
    """

    def __init__(self) -> None:
        self._links: dict[str, LinkRecord] = {}

    def register(self, name: str, policy: LinkPolicy) -> None:
        if not name:
            raise ValueError("link name must be non-empty")
        if name in self._links:
            raise ValueError(f"link already registered: {name}")
        self._links[name] = LinkRecord(policy=policy)

    def heartbeat(self, name: str, timestamp_s: float) -> None:
        timestamp = float(timestamp_s)
        if not isfinite(timestamp):
            raise ValueError("heartbeat timestamp must be finite")
        record = self._links[name]
        if record.last_heartbeat_s is not None and timestamp < record.last_heartbeat_s:
            raise ValueError(f"non-monotonic heartbeat for {name}")
        record.last_heartbeat_s = timestamp

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._links[name].enabled = bool(enabled)

    def healthy_links(self, now_s: float) -> tuple[str, ...]:
        now = float(now_s)
        if not isfinite(now):
            raise ValueError("now_s must be finite")

        healthy: list[str] = []
        for name, record in self._links.items():
            if not record.enabled or record.last_heartbeat_s is None:
                continue
            age = now - record.last_heartbeat_s
            if age < -record.policy.max_future_skew_s:
                continue
            if 0.0 <= age <= record.policy.max_heartbeat_age_s or (
                -record.policy.max_future_skew_s <= age < 0.0
            ):
                healthy.append(name)
        return tuple(sorted(healthy, key=lambda item: self._links[item].policy.priority))

    def active_link(self, now_s: float) -> str | None:
        links = self.healthy_links(now_s)
        return links[0] if links else None
