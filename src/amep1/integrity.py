from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping

from .enums import SensorHealth
from .types import CoverageResult


class IntegrityStatus(str, Enum):
    MONITORING = "MONITORING"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    ALERT = "ALERT"


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


class IntegrityEngine:
    """Evidence-bounded integrity assessment for the current AMEP stack.

    This is intentionally not a certified RAIM/protection-level implementation.
    It consolidates estimator/health/coverage evidence into one explicit contract
    and refuses to label the covariance containment proxy as a protection bound.
    """

    def __init__(self, *, minimum_navigation_rank: int = 3) -> None:
        if minimum_navigation_rank < 1:
            raise ValueError("minimum_navigation_rank must be >= 1")
        self.minimum_navigation_rank = int(minimum_navigation_rank)

    def evaluate(
        self,
        *,
        timestamp_s: float | None,
        coverage: CoverageResult,
        sensor_health: Mapping[str, SensorHealth],
        containment_proxy_m: float,
        hard_fault_reason: str | None = None,
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

        if not isfinite(float(containment_proxy_m)) or containment_proxy_m < 0:
            reasons.append("invalid_containment_proxy")
            return IntegrityReport(
                timestamp_s,
                IntegrityStatus.ALERT,
                False,
                coverage.information_rank,
                coverage.state_dim,
                unhealthy,
                float(containment_proxy_m),
                None,
                False,
                tuple(reasons),
            )

        if hard_fault_reason is not None:
            reasons.append(hard_fault_reason)
            status = IntegrityStatus.ALERT
            permitted = False
        elif coverage.information_rank < self.minimum_navigation_rank:
            reasons.append("insufficient_navigation_constraint_rank")
            status = IntegrityStatus.UNAVAILABLE
            permitted = False
        elif unhealthy:
            reasons.append("one_or_more_sources_degraded_or_unavailable")
            status = IntegrityStatus.DEGRADED
            permitted = True
        else:
            reasons.append("monitoring_without_validated_protection_bound")
            status = IntegrityStatus.MONITORING
            permitted = True

        # AMEP-1 v1.0 demonstrated that the covariance-derived radius can be
        # severely overconfident under correlated common-mode bias. Keep the
        # protection-bound contract explicitly unavailable until a validated
        # integrity architecture closes that evidence gap.
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
        )
