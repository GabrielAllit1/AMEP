from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from .types import MeasurementResult


@dataclass(frozen=True)
class EstimatorSnapshot:
    """Portable navigation projection from a platform estimator.

    ``state_schema_id`` and ``covariance_labels`` make the covariance contract
    explicit. A backend may use any internal state representation, but any matrix
    exported through this snapshot must be interpretable without reading backend
    source code.
    """

    frame: str
    east_m: float
    north_m: float
    ground_velocity_e_mps: float
    ground_velocity_n_mps: float
    heading_rad: float
    covariance: np.ndarray
    state_schema_id: str
    covariance_labels: tuple[str, ...]
    water_velocity_e_mps: float | None = None
    water_velocity_n_mps: float | None = None
    current_e_mps: float | None = None
    current_n_mps: float | None = None

    def __post_init__(self) -> None:
        covariance = np.asarray(self.covariance, dtype=float)
        if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
            raise ValueError("snapshot covariance must be square")
        if covariance.shape[0] != len(self.covariance_labels):
            raise ValueError(
                "snapshot covariance dimension must match covariance_labels length"
            )
        if not self.state_schema_id:
            raise ValueError("state_schema_id must be non-empty")
        if any(not label for label in self.covariance_labels):
            raise ValueError("covariance labels must be non-empty")


@runtime_checkable
class EstimatorBackend(Protocol):
    """State-dimension- and frame-aware real-time estimator contract."""

    last_t: float | None

    @property
    def measurement_kinds(self) -> tuple[str, ...]: ...

    @property
    def accepted_frames(self) -> tuple[str, ...]: ...

    @property
    def containment_probability(self) -> float: ...

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
