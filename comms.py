from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkPolicy:
    priority: int
    max_heartbeat_age_s: float

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("priority must be >= 0")
        if self.max_heartbeat_age_s <= 0:
            raise ValueError("max_heartbeat_age_s must be > 0")


@dataclass
class LinkRecord:
    policy: LinkPolicy
    last_heartbeat_s: float | None = None
    enabled: bool = True


class CommunicationsSupervisor:
    def __init__(self) -> None:
        self._links: dict[str, LinkRecord] = {}

    def register(self, name: str, policy: LinkPolicy) -> None:
        if name in self._links:
            raise ValueError(f"link already registered: {name}")
        self._links[name] = LinkRecord(policy=policy)

    def heartbeat(self, name: str, timestamp_s: float) -> None:
        rec = self._links[name]
        if rec.last_heartbeat_s is not None and timestamp_s < rec.last_heartbeat_s:
            raise ValueError(f"non-monotonic heartbeat for {name}")
        rec.last_heartbeat_s = float(timestamp_s)

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._links[name].enabled = bool(enabled)

    def healthy_links(self, now_s: float) -> tuple[str, ...]:
        healthy = []
        for name, rec in self._links.items():
            if not rec.enabled or rec.last_heartbeat_s is None:
                continue
            if now_s - rec.last_heartbeat_s <= rec.policy.max_heartbeat_age_s:
                healthy.append(name)
        return tuple(sorted(healthy, key=lambda n: self._links[n].policy.priority))

    def active_link(self, now_s: float) -> str | None:
        links = self.healthy_links(now_s)
        return links[0] if links else None
