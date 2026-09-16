from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping


class SourceClass(str, Enum):
    ABSOLUTE_POSITION = "ABSOLUTE_POSITION"
    RELATIVE_POSITION = "RELATIVE_POSITION"
    WATER_VELOCITY = "WATER_VELOCITY"
    GROUND_VELOCITY = "GROUND_VELOCITY"
    HEADING = "HEADING"
    CURRENT_PRIOR = "CURRENT_PRIOR"
    INERTIAL = "INERTIAL"
    RF_HEALTH = "RF_HEALTH"
    TIME_REFERENCE = "TIME_REFERENCE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class SourceDescriptor:
    """Declared integration metadata for one navigation source.

    ``failure_domain`` is an engineering declaration used to avoid giving
    multiple measurements from a shared dependency false independence credit.
    It is not proof that two differently named domains are statistically or
    physically independent; that still requires system analysis and evidence.
    """

    name: str
    source_class: SourceClass
    failure_domain: str
    absolute_position: bool = False
    gnss: bool = False
    safety_credit: bool = True
    clock_domain: str = "navigation"
    provenance_required: bool = False
    max_timestamp_uncertainty_s: float | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("source name must be non-empty")
        if not self.failure_domain:
            raise ValueError("failure_domain must be non-empty")
        if not self.clock_domain:
            raise ValueError("clock_domain must be non-empty")
        if self.max_timestamp_uncertainty_s is not None and self.max_timestamp_uncertainty_s < 0:
            raise ValueError("max_timestamp_uncertainty_s must be >= 0")
        if self.gnss and not self.absolute_position:
            raise ValueError("GNSS source must declare absolute_position=True")


class SourceRegistry:
    """MOSA-style registry separating sensor identity from estimator logic."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceDescriptor] = {}

    def register(self, descriptor: SourceDescriptor) -> None:
        if descriptor.name in self._sources:
            raise ValueError(f"source already registered: {descriptor.name}")
        self._sources[descriptor.name] = descriptor

    def descriptor(self, source: str) -> SourceDescriptor | None:
        return self._sources.get(source)

    def require(self, source: str) -> SourceDescriptor:
        descriptor = self.descriptor(source)
        if descriptor is None:
            raise KeyError(f"unregistered source descriptor: {source}")
        return descriptor

    def descriptors(self) -> tuple[SourceDescriptor, ...]:
        return tuple(self._sources[name] for name in sorted(self._sources))

    def fingerprint(self) -> str:
        """Stable SHA-256 fingerprint of the declared source dependency model."""
        payload = [
            {
                "name": descriptor.name,
                "source_class": descriptor.source_class.value,
                "failure_domain": descriptor.failure_domain,
                "absolute_position": descriptor.absolute_position,
                "gnss": descriptor.gnss,
                "safety_credit": descriptor.safety_credit,
                "clock_domain": descriptor.clock_domain,
                "provenance_required": descriptor.provenance_required,
                "max_timestamp_uncertainty_s": descriptor.max_timestamp_uncertainty_s,
                "attributes": dict(sorted(descriptor.attributes.items())),
            }
            for descriptor in self.descriptors()
        ]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def failure_domains(
        self,
        sources: Iterable[str],
        *,
        absolute_only: bool = False,
        safety_credit_only: bool = True,
        non_gnss_only: bool = False,
    ) -> tuple[str, ...]:
        domains: set[str] = set()
        for source in sources:
            descriptor = self._sources.get(source)
            if descriptor is None:
                continue
            if absolute_only and not descriptor.absolute_position:
                continue
            if safety_credit_only and not descriptor.safety_credit:
                continue
            if non_gnss_only and descriptor.gnss:
                continue
            domains.add(descriptor.failure_domain)
        return tuple(sorted(domains))

    def unregistered(self, sources: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(source for source in sources if source not in self._sources))
