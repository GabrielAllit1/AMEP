from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .enums import SensorHealth
from .types import CoverageResult


@dataclass(frozen=True)
class ConstraintSpec:
    observed_state_indices: tuple[int, ...]
    weight: float = 1.0
    absolute_position: bool = False
    gnss: bool = False

    def __post_init__(self) -> None:
        if not self.observed_state_indices:
            raise ValueError("constraint must observe at least one state")
        if any(index < 0 for index in self.observed_state_indices):
            raise ValueError("state indices must be >= 0")
        if self.weight <= 0:
            raise ValueError("constraint weight must be > 0")


class ConstraintCoverage:
    """Local diagonalized information-rank heuristic.

    ``state_dim`` is supplied by the platform profile. The reference maritime
    profile uses seven states, but orchestration no longer hardcodes that value.
    This heuristic is deliberately not represented as formal nonlinear
    observability.
    """

    def __init__(self, *, state_dim: int = 7) -> None:
        if state_dim < 1:
            raise ValueError("state_dim must be >= 1")
        self.state_dim = int(state_dim)
        self._specs: dict[str, ConstraintSpec] = {}

    def register(self, source: str, spec: ConstraintSpec) -> None:
        if not source:
            raise ValueError("source must be non-empty")
        if any(index >= self.state_dim for index in spec.observed_state_indices):
            raise ValueError(
                f"constraint state index exceeds configured state_dim={self.state_dim}"
            )
        self._specs[source] = spec

    def configuration(self) -> dict[str, object]:
        return {
            "state_dim": self.state_dim,
            "sources": {
                source: {
                    "observed_state_indices": spec.observed_state_indices,
                    "weight": spec.weight,
                    "absolute_position": spec.absolute_position,
                    "gnss": spec.gnss,
                }
                for source, spec in sorted(self._specs.items())
            },
        }

    def compute(self, health: dict[str, SensorHealth]) -> CoverageResult:
        diagonal = np.zeros(self.state_dim, dtype=float)
        healthy: list[str] = []
        absolute: list[str] = []
        has_gnss = False
        has_non_gnss_abs = False

        for source, spec in self._specs.items():
            if health.get(source, SensorHealth.UNKNOWN) not in {
                SensorHealth.ONLINE,
                SensorHealth.DEGRADED,
            }:
                continue
            healthy.append(source)
            for index in spec.observed_state_indices:
                diagonal[index] += spec.weight
            if spec.absolute_position:
                absolute.append(source)
                if spec.gnss:
                    has_gnss = True
                else:
                    has_non_gnss_abs = True

        positive = diagonal[diagonal > 0]
        rank = int(np.count_nonzero(diagonal > 1e-12))
        condition_number = (
            float(np.max(positive) / np.min(positive)) if positive.size else float("inf")
        )
        return CoverageResult(
            information_rank=rank,
            state_dim=self.state_dim,
            condition_number=condition_number,
            information_diagonal=tuple(float(value) for value in diagonal),
            healthy_sources=tuple(sorted(healthy)),
            active_absolute_sources=tuple(sorted(absolute)),
            has_healthy_gnss=has_gnss,
            has_healthy_non_gnss_absolute=has_non_gnss_abs,
        )
