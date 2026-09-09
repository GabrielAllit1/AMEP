from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .enums import AuthoritySource, NavMode
from .types import AuthorityDecision, CoverageResult


@dataclass(frozen=True)
class NavigationPolicy:
    full_rank: int = 7
    degraded_rank: int = 3


class NavigationSupervisor:
    def __init__(self, policy: NavigationPolicy | None = None) -> None:
        self.policy = policy or NavigationPolicy()
        self.mode = NavMode.SAFE_HOLD
        self.reason = "initial_state"

    def force_safe_hold(self, reason: str) -> NavMode:
        self.mode = NavMode.SAFE_HOLD
        self.reason = reason
        return self.mode

    def update(self, coverage: CoverageResult) -> NavMode:
        rank = coverage.information_rank
        if rank >= self.policy.full_rank and coverage.has_healthy_gnss:
            self.mode = NavMode.NOMINAL
            self.reason = "full_local_constraint_coverage_with_healthy_gnss"
        elif rank >= self.policy.full_rank and coverage.has_healthy_non_gnss_absolute:
            self.mode = NavMode.GPS_DENIED_RESILIENT
            self.reason = "full_local_constraint_coverage_with_non_gnss_absolute_source"
        elif rank >= self.policy.degraded_rank:
            self.mode = NavMode.DEGRADED_DEAD_RECKONING
            self.reason = "partial_constraint_coverage"
        else:
            self.mode = NavMode.SAFE_HOLD
            self.reason = "insufficient_healthy_navigation_constraints"
        return self.mode

    def decide_authority(
        self,
        *,
        operator_command: Mapping[str, Any] | None,
        autonomy_command: Mapping[str, Any] | None,
        has_healthy_command_link: bool,
    ) -> AuthorityDecision:
        if operator_command is not None and has_healthy_command_link:
            return AuthorityDecision(
                source=AuthoritySource.OPERATOR,
                mode=self.mode,
                command=operator_command,
                reason="operator_priority_on_healthy_link",
            )
        if autonomy_command is not None and self.mode in {
            NavMode.NOMINAL,
            NavMode.GPS_DENIED_RESILIENT,
        }:
            return AuthorityDecision(
                source=AuthoritySource.AUTONOMY,
                mode=self.mode,
                command=autonomy_command,
                reason="autonomy_permitted_by_navigation_mode",
            )
        return AuthorityDecision(
            source=AuthoritySource.SAFETY,
            mode=self.mode,
            command=None,
            reason="safe_hold_required_or_no_permitted_command",
        )
