from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .types import HorizontalIMUInput, MeasurementResult


@runtime_checkable
class EstimatorBackend(Protocol):
    """Minimal real-time estimator contract consumed by ``AMEPRuntime``.

    The current implementation is ``AMEPFilter``. Keeping runtime orchestration
    behind this protocol permits a future maritime ESKF, invariant filter, or
    another platform-specific real-time estimator without coupling source,
    integrity, replay, or authority layers to one estimator class.
    """

    x: np.ndarray
    P: np.ndarray
    last_t: float | None

    def predict(self, imu: HorizontalIMUInput) -> float: ...

    def update(
        self,
        z: np.ndarray,
        H: np.ndarray,
        R: np.ndarray,
        *,
        source: str,
        angle_rows: tuple[int, ...] = (),
        allow_fusion: bool = True,
    ) -> MeasurementResult: ...

    @property
    def position(self) -> tuple[float, float]: ...

    @property
    def ground_velocity(self) -> tuple[float, float]: ...

    @property
    def heading(self) -> float: ...

    def containment_proxy(self) -> float: ...


@runtime_checkable
class DelayedMeasurementBackend(Protocol):
    """Optional seam for fixed-lag/factor-graph delayed-measurement processing.

    AMEP's current real-time EKF intentionally rejects out-of-order input. A
    smoother can implement this interface in parallel and return corrected state
    products without changing the deterministic real-time estimator contract.
    """

    def ingest_delayed(self, *, source: str, timestamp_s: float, payload: object) -> None: ...

    def optimize(self, *, now_s: float) -> object: ...
