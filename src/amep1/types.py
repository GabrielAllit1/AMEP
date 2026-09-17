from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .enums import AuthoritySource, NavMode, SensorHealth


@dataclass(frozen=True)
class HorizontalIMUInput:
    """AMEP estimator input contract.

    a_fwd_mps2 and a_stbd_mps2 MUST already be horizontal, leveled,
    gravity-compensated translational accelerations. Raw accelerometer
    specific force is intentionally not accepted by this type.
    """

    timestamp_s: float
    a_fwd_mps2: float
    a_stbd_mps2: float
    yaw_rate_rps: float
    gravity_compensated: bool = True

    def validate(self) -> None:
        if not self.gravity_compensated:
            raise ValueError(
                "AMEP requires leveled/gravity-compensated horizontal acceleration; "
                "do not feed raw accelerometer specific force directly"
            )


@dataclass(frozen=True)
class MeasurementResult:
    source: str
    accepted: bool
    fused: bool
    nis: float
    threshold: float
    dimension: int
    reason: str


@dataclass(frozen=True)
class CoverageResult:
    information_rank: int
    state_dim: int
    condition_number: float
    information_diagonal: tuple[float, ...]
    healthy_sources: tuple[str, ...]
    active_absolute_sources: tuple[str, ...]
    has_healthy_gnss: bool
    has_healthy_non_gnss_absolute: bool


@dataclass(frozen=True)
class AuthorityDecision:
    source: AuthoritySource
    mode: NavMode
    command: Mapping[str, Any] | None
    reason: str


@dataclass(frozen=True)
class NavigationStatus:
    timestamp_s: float | None
    mode: NavMode
    east_m: float
    north_m: float
    ground_velocity_e_mps: float
    ground_velocity_n_mps: float
    heading_rad: float
    containment_proxy_m: float
    information_rank: int
    state_dim: int
    active_absolute_sources: tuple[str, ...]
    sensor_health: Mapping[str, SensorHealth]
    reason: str
