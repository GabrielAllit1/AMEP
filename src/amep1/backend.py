from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from .types import MeasurementResult


@dataclass(frozen=True)
class EstimatorSnapshot:
    """Portable horizontal navigation projection from a platform estimator.

    Internal estimator state dimension and representation are intentionally not
    exposed to the orchestration layer. Optional maritime fields are populated by
    AMEPFilter and may be absent for other platform-specific estimators.
    """

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
    """State-dimension-agnostic real-time estimator contract.

    Measurement semantics cross the boundary as named kinds plus values and
    covariance; each estimator owns its own state layout and observation models.
    This permits an ESKF or another platform-specific estimator to replace the
    seven-state maritime filter without making ``AMEPRuntime`` construct its H.
    """

    last_t: float | None

    def predict(self, prediction_input: object) -> float: ...

    def update_measurement(
        self,
        kind: str,
        values: np.ndarray,
        covariance: np.ndarray,
        *,
        source: str,
        allow_fusion: bool = True,
    ) -> MeasurementResult: ...

    def snapshot(self) -> EstimatorSnapshot: ...

    def containment_proxy(self) -> float: ...


@runtime_checkable
class DelayedMeasurementBackend(Protocol):
    """Optional seam for fixed-lag/factor-graph delayed-measurement processing.

    The real-time estimator may intentionally reject out-of-order input. A
    smoother can implement this interface in parallel and return corrected state
    products without changing the deterministic low-latency estimator contract.
    """

    def ingest_delayed(self, *, source: str, timestamp_s: float, payload: object) -> None: ...

    def optimize(self, *, now_s: float) -> object: ...
