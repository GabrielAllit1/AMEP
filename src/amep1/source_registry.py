from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


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
    """Declared integration and common-cause metadata for one source.

    ``failure_domain`` identifies the source's primary measurement-generation
    chain. ``dependencies`` declares additional shared integrity dependencies,
    such as a clock, map, preprocessing service, receiver, compute service, or
    power domain. Declarations are engineering assumptions, not proof of
    statistical independence.

    Safety credit is conservative by default. A source may receive safety credit
    only when provenance is required, a finite timestamp-uncertainty budget is
    declared, and a non-empty assurance reference identifies the review/evidence
    basis for granting that credit.
    """

    name: str
    source_class: SourceClass
    failure_domain: str
    absolute_position: bool = False
    gnss: bool = False
    safety_credit: bool = False
    clock_domain: str = "navigation"
    provenance_required: bool = False
    max_timestamp_uncertainty_s: float | None = None
    assurance_reference: str | None = None
    dependencies: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("source name must be non-empty")
        if not self.failure_domain:
            raise ValueError("failure_domain must be non-empty")
        if not self.clock_domain:
            raise ValueError("clock_domain must be non-empty")
        if any(not dependency for dependency in self.dependencies):
            raise ValueError("dependency names must be non-empty")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("dependency names must not contain duplicates")
        for key, value in self.attributes.items():
            if not isinstance(key, str) or not key:
                raise ValueError("attribute keys must be non-empty strings")
            if not isinstance(value, str):
                raise ValueError("attribute values must be strings")
        if self.max_timestamp_uncertainty_s is not None:
            uncertainty = float(self.max_timestamp_uncertainty_s)
            if not isfinite(uncertainty) or uncertainty < 0:
                raise ValueError(
                    "max_timestamp_uncertainty_s must be finite and >= 0"
                )
        if self.gnss and not self.absolute_position:
            raise ValueError("GNSS source must declare absolute_position=True")
        if self.safety_credit:
            if not self.provenance_required:
                raise ValueError("safety-credit source must require provenance")
            if self.max_timestamp_uncertainty_s is None:
                raise ValueError(
                    "safety-credit source must declare max_timestamp_uncertainty_s"
                )
            if self.assurance_reference is None or not self.assurance_reference.strip():
                raise ValueError(
                    "safety-credit source must declare assurance_reference"
                )

    @property
    def integrity_dependencies(self) -> frozenset[str]:
        return frozenset((self.failure_domain, *self.dependencies))


class SourceRegistry:
    """Registry separating source identity and dependencies from estimation."""

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

    def configuration(self) -> tuple[dict[str, object], ...]:
        return tuple(
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
                "assurance_reference": descriptor.assurance_reference,
                "dependencies": tuple(sorted(descriptor.dependencies)),
                "attributes": dict(sorted(descriptor.attributes.items())),
            }
            for descriptor in self.descriptors()
        )

    def fingerprint(self) -> str:
        """Stable SHA-256 fingerprint of the declared source dependency model."""
        canonical = json.dumps(
            self.configuration(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _eligible(
        self,
        sources: Iterable[str],
        *,
        absolute_only: bool,
        safety_credit_only: bool,
        non_gnss_only: bool,
    ) -> tuple[SourceDescriptor, ...]:
        eligible: list[SourceDescriptor] = []
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
            eligible.append(descriptor)
        return tuple(eligible)

    def failure_domains(
        self,
        sources: Iterable[str],
        *,
        absolute_only: bool = False,
        safety_credit_only: bool = True,
        non_gnss_only: bool = False,
    ) -> tuple[str, ...]:
        descriptors = self._eligible(
            sources,
            absolute_only=absolute_only,
            safety_credit_only=safety_credit_only,
            non_gnss_only=non_gnss_only,
        )
        return tuple(sorted({descriptor.failure_domain for descriptor in descriptors}))

    def maximum_independent_count(
        self,
        sources: Iterable[str],
        *,
        absolute_only: bool = False,
        safety_credit_only: bool = True,
        non_gnss_only: bool = False,
    ) -> int:
        """Return the largest pairwise dependency-disjoint source subset.

        Navigation source sets are expected to remain small, so exhaustive subset
        search is deterministic and auditable. If source counts become large, the
        integration should replace this implementation with an explicitly reviewed
        graph optimization rather than silently changing the integrity semantics.
        """
        descriptors = self._eligible(
            sources,
            absolute_only=absolute_only,
            safety_credit_only=safety_credit_only,
            non_gnss_only=non_gnss_only,
        )
        for size in range(len(descriptors), 0, -1):
            for subset in itertools.combinations(descriptors, size):
                occupied: set[str] = set()
                independent = True
                for descriptor in subset:
                    dependencies = set(descriptor.integrity_dependencies)
                    if occupied.intersection(dependencies):
                        independent = False
                        break
                    occupied.update(dependencies)
                if independent:
                    return size
        return 0

    def unregistered(self, sources: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(source for source in sources if source not in self._sources))
