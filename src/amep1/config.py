from dataclasses import dataclass, field
from math import radians


@dataclass(frozen=True)
class ProcessNoiseConfig:
    # AMEP-1 v1.0 research defaults. These are not vessel/IMU calibrated.
    q_pos_coef: float = 0.08
    q_vel_coef: float = 0.025
    q_current_coef: float = 0.008
    q_heading_coef_rad: float = radians(0.015)


@dataclass(frozen=True)
class EstimatorConfig:
    gate_probability: float = 0.997
    containment_probability: float = 0.95
    min_dt_s: float = 1e-6
    max_dt_s: float = 0.50
    covariance_eigen_floor: float = 1e-12
    process_noise: ProcessNoiseConfig = field(default_factory=ProcessNoiseConfig)

    def __post_init__(self) -> None:
        if not 0.5 < self.gate_probability < 1.0:
            raise ValueError("gate_probability must be in (0.5, 1.0)")
        if not 0.5 < self.containment_probability < 1.0:
            raise ValueError("containment_probability must be in (0.5, 1.0)")
        if self.min_dt_s <= 0 or self.max_dt_s <= self.min_dt_s:
            raise ValueError("invalid estimator dt bounds")
        if self.covariance_eigen_floor <= 0:
            raise ValueError("covariance_eigen_floor must be > 0")


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime assurance switches that do not alter estimator mathematics.

    ``allow_legacy_direct_updates`` exists only for backward compatibility with
    pre-envelope integrations and unit tests. Production-oriented profiles should
    set it to False so every measurement must pass timing, provenance, dependency,
    and pre-fusion consistency checks through ``ingest_measurement``.
    """

    allow_legacy_direct_updates: bool = True


@dataclass(frozen=True)
class SourcePolicy:
    max_age_s: float
    isolate_after_consecutive_rejections: int = 3
    rejection_window: int = 20
    min_window_samples: int = 8
    max_rejection_fraction: float = 0.50
    recovery_consecutive_accepts: int = 5

    def __post_init__(self) -> None:
        if self.max_age_s <= 0:
            raise ValueError("max_age_s must be > 0")
        if self.isolate_after_consecutive_rejections < 1:
            raise ValueError("isolation threshold must be >= 1")
        if self.rejection_window < 1:
            raise ValueError("rejection_window must be >= 1")
        if not 0 <= self.max_rejection_fraction <= 1:
            raise ValueError("max_rejection_fraction must be in [0,1]")
        if self.recovery_consecutive_accepts < 1:
            raise ValueError("recovery_consecutive_accepts must be >= 1")
