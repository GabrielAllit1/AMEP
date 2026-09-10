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
        if any(i < 0 or i >= 7 for i in self.observed_state_indices):
            raise ValueError("state index out of range")
        if self.weight <= 0:
            raise ValueError("constraint weight must be > 0")


class ConstraintCoverage:
    """Implements the paper's diagonalized local information-rank heuristic.

    This is deliberately not represented as formal nonlinear observability.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ConstraintSpec] = {}

    def register(self, source: str, spec: ConstraintSpec) -> None:
        self._specs[source] = spec

    def compute(self, health: dict[str, SensorHealth]) -> CoverageResult:
        diag = np.zeros(7, dtype=float)
        healthy: list[str] = []
        absolute: list[str] = []
        has_gnss = False
        has_non_gnss_abs = False

        for source, spec in self._specs.items():
            # DEGRADED remains usable in the local-coverage heuristic; ISOLATED/STALE do not.
            if health.get(source, SensorHealth.UNKNOWN) not in {
                SensorHealth.ONLINE,
                SensorHealth.DEGRADED,
            }:
                continue
            healthy.append(source)
            for idx in spec.observed_state_indices:
                diag[idx] += spec.weight
            if spec.absolute_position:
                absolute.append(source)
                if spec.gnss:
                    has_gnss = True
                else:
                    has_non_gnss_abs = True

        positive = diag[diag > 0]
        rank = int(np.count_nonzero(diag > 1e-12))
        cond = float(np.max(positive) / np.min(positive)) if positive.size else float("inf")
        return CoverageResult(
            information_rank=rank,
            state_dim=7,
            condition_number=cond,
            information_diagonal=tuple(float(v) for v in diag),
            healthy_sources=tuple(sorted(healthy)),
            active_absolute_sources=tuple(sorted(absolute)),
            has_healthy_gnss=has_gnss,
            has_healthy_non_gnss_absolute=has_non_gnss_abs,
        )
