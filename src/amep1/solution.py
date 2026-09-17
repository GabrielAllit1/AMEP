from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .enums import NavMode, SensorHealth
from .integrity import IntegrityReport, IntegrityStatus


@dataclass(frozen=True)
class PNTSolution:
    """Evidence-bounded navigation output contract.

    Covariance is self-describing through ``state_schema_id`` and
    ``covariance_labels``. The containment proxy is reported together with its
    configured probability rather than encoding a probability into the field
    name. Backend-specific maritime quantities remain nullable.
    """

    timestamp_s: float | None
    mode: NavMode
    frame: str
    east_m: float
    north_m: float
    ground_velocity_e_mps: float
    ground_velocity_n_mps: float
    water_velocity_e_mps: float | None
    water_velocity_n_mps: float | None
    current_e_mps: float | None
    current_n_mps: float | None
    heading_rad: float
    covariance: tuple[tuple[float, ...], ...]
    state_schema_id: str
    covariance_labels: tuple[str, ...]
    containment_probability: float
    horizontal_containment_proxy_m: float
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
