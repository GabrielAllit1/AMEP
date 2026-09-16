from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from .types import MeasurementResult


@dataclass(frozen=True)
class EstimatorSnapshot:
    """Portable navigation projection from a platform estimator.

    Internal estimator state dimension and representation are intentionally not
    exposed to orchestration. Optional maritime fields are populated by
    AMEPFilter and may be absent for other platform-specific estimators.
    """

    frame: str
    east_m: float
    north_m: float
    ground_velocity_e_mps: float
    ground_velocity_n_mps: float
    heading_rad: float
    covariance: np.ndarray
    water_velocity_e_mps: float | None = None
    water_velocity_n_mps: float | None = None
    current_e_mps: float | None = None
    current_n_mps: float | None = None


@runtime_checkable
class EstimatorBackend(Protocol):
    """State-dimension- and frame-aware real-time estimator contract.

    Measurements cross the boundary as semantic kinds, values, covariance and
    frame. Each estimator owns its internal state layout and observation models.
    """

    last_t: float | None

    def predict(self, prediction_input: object) -> float: ...

    def update_measurement(
        self,
        kind: str,
        values: np.ndarray,
        covariance: np.ndarray,
        *,
        frame: str,
        source: str,
        metadata: Mapping[str, object] | None = None,
        allow_fusion: bool = True,
    ) -> MeasurementResult: ...

    def snapshot(self) -> EstimatorSnapshot: ...

    def containment_proxy(self) -> float: ...


@runtime_checkable
class DelayedMeasurementBackend(Protocol):
    """Optional seam for fixed-lag/factor-graph delayed-measurement processing."""

    def ingest_delayed(self, *, source: str, timestamp_s: float, payload: object) -> None: ...

    def optimize(self, *, now_s: float) -> object: ...
