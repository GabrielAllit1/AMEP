from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .enums import NavMode, SensorHealth
from .integrity import IntegrityReport, IntegrityStatus


@dataclass(frozen=True)
class PNTSolution:
    """Evidence-bounded AMEP navigation output contract.

    Attitude and validated navigation time are not produced by the current
    seven-state horizontal estimator, and no validated protection bound exists.
    Those absences are represented explicitly instead of inferred by consumers.
    """

    timestamp_s: float | None
    mode: NavMode
    east_m: float
    north_m: float
    ground_velocity_e_mps: float
    ground_velocity_n_mps: float
    water_velocity_e_mps: float
    water_velocity_n_mps: float
    current_e_mps: float
    current_n_mps: float
    heading_rad: float
    covariance: tuple[tuple[float, ...], ...]
    containment_proxy_95_m: float
    horizontal_protection_bound_m: float | None
    protection_bound_validated: bool
    integrity_status: IntegrityStatus
    integrity: IntegrityReport
    information_rank: int
    state_dim: int
    active_absolute_sources: tuple[str, ...]
    sensor_health: Mapping[str, SensorHealth]
    source_age_s: Mapping[str, float | None]
    reason: str
    attitude_available: bool = False
    navigation_time_validated: bool = False
