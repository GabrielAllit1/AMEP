from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping

from .consistency import ConsistencyReport
from .enums import SensorHealth
from .source_registry import SourceRegistry
from .types import CoverageResult


class IntegrityStatus(str, Enum):
    MONITORING = "MONITORING"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    ALERT = "ALERT"


@dataclass(frozen=True)
class IntegrityPolicy:
    minimum_navigation_rank: int = 3
    minimum_resilient_non_gnss_absolute_domains: int = 2
    require_dependency_model_for_resilient: bool = True
    block_on_cross_source_conflict: bool = True

    def __post_init__(self) -> None:
        if self.minimum_navigation_rank < 1:
            raise ValueError("minimum_navigation_rank must be >= 1")
        if self.minimum_resilient_non_gnss_absolute_domains < 1:
            raise ValueError("minimum_resilient_non_gnss_absolute_domains must be >= 1")


@dataclass(frozen=True)
class IntegrityReport:
    timestamp_s: float | None
    status: IntegrityStatus
    navigation_permitted: bool
    information_rank: int
    state_dim: int
    unhealthy_sources: tuple[str, ...]
    containment_proxy_m: float
    horizontal_protection_bound_m: float | None
    protection_bound_validated: bool
    reasons: tuple[str, ...]
    dependency_model_available: bool = False
    declared_absolute_failure_domains: tuple[str, ...] = ()
    declared_non_gnss_absolute_failure_domains: tuple[str, ...] = ()
    unregistered_active_absolute_sources: tuple[str, ...] = ()
    resilient_navigation_permitted: bool = False
    cross_source_consistent: bool | None = None
    cross_source_conflicts: int = 0


class IntegrityEngine:
    """Evidence-bounded integrity assessment for the AMEP runtime.

    The engine explicitly distinguishes health from independence. Multiple
    healthy sources that share a declared failure domain do not receive multiple
    units of resilience credit. Only ONLINE absolute sources receive diversity
    credit for the resilient-mode decision; DEGRADED sources may still contribute
    to the estimator/coverage heuristic but do not establish high-confidence
    source independence.
    """

    def __init__(
        self,
        *,
        minimum_navigation_rank: int | None = None,
        policy: IntegrityPolicy | None = None,
    ) -> None:
        if policy is not None and minimum_navigation_rank is not None:
            raise ValueError("provide policy or minimum_navigation_rank, not both")
        if policy is None:
            policy = IntegrityPolicy(
                minimum_navigation_rank=(
                    3 if minimum_navigation_rank is None else int(minimum_navigation_rank)
                )
            )
        self.policy = policy

    def evaluate(
        self,
        *,
        timestamp_s: float | None,
        coverage: CoverageResult,
        sensor_health: Mapping[str, SensorHealth],
        containment_proxy_m: float,
        hard_fault_reason: str | None = None,
        source_registry: SourceRegistry | None = None,
        consistency: ConsistencyReport | None = None,
    ) -> IntegrityReport:
        reasons: list[str] = []
        unhealthy = tuple(
            sorted(
                source
                for source, state in sensor_health.items()
                if state in {
                    SensorHealth.DEGRADED,
                    SensorHealth.ISOLATED,
                    SensorHealth.STALE,
                }
            )
        )

        active_absolute = coverage.active_absolute_sources
        creditable_absolute = tuple(
            source
            for source in active_absolute
            if sensor_health.get(source) == SensorHealth.ONLINE
        )
        if source_registry is None:
            dependency_available = False
            abs_domains: tuple[str, ...] = ()
            non_gnss_domains: tuple[str, ...] = ()
            unregistered = tuple(active_absolute)
        else:
            unregistered = source_registry.unregistered(active_absolute)
            dependency_available = bool(active_absolute) and not unregistered
            abs_domains = source_registry.failure_domains(
                creditable_absolute,
                absolute_only=True,
            )
            non_gnss_domains = source_registry.failure_domains(
                creditable_absolute,
                absolute_only=True,
                non_gnss_only=True,
            )

        full_non_gnss = (
            coverage.information_rank >= coverage.state_dim
            and coverage.has_healthy_non_gnss_absolute
        )
        resilient_permitted = full_non_gnss and (
            len(non_gnss_domains)
            >= self.policy.minimum_resilient_non_gnss_absolute_domains
        )
        if self.policy.require_dependency_model_for_resilient and not dependency_available:
            resilient_permitted = False

        cross_source_consistent = None if consistency is None else consistency.consistent
        cross_source_conflicts = 0 if consistency is None else len(consistency.conflicts)

        status = IntegrityStatus.MONITORING
        permitted = True

        if not isfinite(float(containment_proxy_m)) or containment_proxy_m < 0:
            reasons.append("invalid_containment_proxy")
            status = IntegrityStatus.ALERT
            permitted = False
        elif hard_fault_reason is not None:
            reasons.append(hard_fault_reason)
            status = IntegrityStatus.ALERT
            permitted = False
        elif (
            consistency is not None
            and not consistency.consistent
            and self.policy.block_on_cross_source_conflict
        ):
            reasons.append("independent_absolute_sources_inconsistent")
            status = IntegrityStatus.ALERT
            permitted = False
        elif coverage.information_rank < self.policy.minimum_navigation_rank:
            reasons.append("insufficient_navigation_constraint_rank")
            status = IntegrityStatus.UNAVAILABLE
            permitted = False
        elif unhealthy:
            reasons.append("one_or_more_sources_degraded_or_unavailable")
            status = IntegrityStatus.DEGRADED
        else:
            reasons.append("monitoring_without_validated_protection_bound")

        if full_non_gnss and not resilient_permitted:
            if not dependency_available:
                reasons.append("resilience_dependency_model_incomplete")
            elif len(non_gnss_domains) < self.policy.minimum_resilient_non_gnss_absolute_domains:
                reasons.append("insufficient_declared_independent_non_gnss_absolute_domains")

        if unregistered:
            reasons.append("active_absolute_source_missing_dependency_descriptor")

        return IntegrityReport(
            timestamp_s=timestamp_s,
            status=status,
            navigation_permitted=permitted,
            information_rank=coverage.information_rank,
            state_dim=coverage.state_dim,
            unhealthy_sources=unhealthy,
            containment_proxy_m=float(containment_proxy_m),
            horizontal_protection_bound_m=None,
            protection_bound_validated=False,
            reasons=tuple(reasons),
            dependency_model_available=dependency_available,
            declared_absolute_failure_domains=abs_domains,
            declared_non_gnss_absolute_failure_domains=non_gnss_domains,
            unregistered_active_absolute_sources=unregistered,
            resilient_navigation_permitted=resilient_permitted,
            cross_source_consistent=cross_source_consistent,
            cross_source_conflicts=cross_source_conflicts,
        )
