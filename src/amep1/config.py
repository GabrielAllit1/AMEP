from dataclasses import dataclass, field
from math import isfinite, radians


@dataclass(frozen=True)
class ProcessNoiseConfig:
    # AMEP-1 v1.0 research defaults. These are not vessel/IMU calibrated.
    q_pos_coef: float = 0.08
    q_vel_coef: float = 0.025
    q_current_coef: float = 0.008
    q_heading_coef_rad: float = radians(0.015)

    def __post_init__(self) -> None:
        for name, value in (
            ("q_pos_coef", self.q_pos_coef),
            ("q_vel_coef", self.q_vel_coef),
            ("q_current_coef", self.q_current_coef),
            ("q_heading_coef_rad", self.q_heading_coef_rad),
        ):
            numeric = float(value)
            if not isfinite(numeric) or numeric < 0:
                raise ValueError(f"{name} must be finite and >= 0")


@dataclass(frozen=True)
class EstimatorConfig:
    gate_probability: float = 0.997
    containment_probability: float = 0.95
    min_dt_s: float = 1e-6
    max_dt_s: float = 0.50
    covariance_eigen_floor: float = 1e-12
    process_noise: ProcessNoiseConfig = field(default_factory=ProcessNoiseConfig)

    def __post_init__(self) -> None:
        gate_probability = float(self.gate_probability)
        containment_probability = float(self.containment_probability)
        min_dt_s = float(self.min_dt_s)
        max_dt_s = float(self.max_dt_s)
        covariance_eigen_floor = float(self.covariance_eigen_floor)

        if not isfinite(gate_probability) or not 0.5 < gate_probability < 1.0:
            raise ValueError("gate_probability must be finite and in (0.5, 1.0)")
        if (
            not isfinite(containment_probability)
            or not 0.5 < containment_probability < 1.0
        ):
            raise ValueError(
                "containment_probability must be finite and in (0.5, 1.0)"
            )
        if not isfinite(min_dt_s) or not isfinite(max_dt_s):
            raise ValueError("estimator dt bounds must be finite")
        if min_dt_s <= 0 or max_dt_s <= min_dt_s:
            raise ValueError("invalid estimator dt bounds")
        if not isfinite(covariance_eigen_floor) or covariance_eigen_floor <= 0:
            raise ValueError("covariance_eigen_floor must be finite and > 0")


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime assurance switches.

    The default policy is fail-closed: normalized sources must be registered,
    legacy direct-update bypasses are disabled, and behavior-affecting runtime
    configuration must be explicitly sealed before prediction or measurement
    ingestion.

    ``compatibility()`` is an explicit opt-in for legacy research integrations.
    It must not be used as evidence of an assured integration.
    """

    allow_legacy_direct_updates: bool = False
    require_registered_sources: bool = True
    require_configuration_seal: bool = True

    @classmethod
    def compatibility(cls) -> "RuntimePolicy":
        return cls(
            allow_legacy_direct_updates=True,
            require_registered_sources=False,
            require_configuration_seal=False,
        )


@dataclass(frozen=True)
class SourcePolicy:
    max_age_s: float
    isolate_after_consecutive_rejections: int = 3
    rejection_window: int = 20
    min_window_samples: int = 8
    max_rejection_fraction: float = 0.50
    recovery_consecutive_accepts: int = 5

    def __post_init__(self) -> None:
        max_age_s = float(self.max_age_s)
        max_rejection_fraction = float(self.max_rejection_fraction)

        if not isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("max_age_s must be finite and > 0")
        if self.isolate_after_consecutive_rejections < 1:
            raise ValueError("isolation threshold must be >= 1")
        if self.rejection_window < 1:
            raise ValueError("rejection_window must be >= 1")
        if self.min_window_samples < 1:
            raise ValueError("min_window_samples must be >= 1")
        if self.min_window_samples > self.rejection_window:
            raise ValueError("min_window_samples must be <= rejection_window")
        if (
            not isfinite(max_rejection_fraction)
            or not 0 <= max_rejection_fraction <= 1
        ):
            raise ValueError("max_rejection_fraction must be finite and in [0,1]")
        if self.recovery_consecutive_accepts < 1:
            raise ValueError("recovery_consecutive_accepts must be >= 1")
