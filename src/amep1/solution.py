from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .enums import NavMode, SensorHealth
from .integrity import IntegrityReport, IntegrityStatus


@dataclass(frozen=True)
class PNTSolution:
    """Evidence-bounded navigation output contract.

    ``frame`` is explicit and estimator-specific optional quantities remain
    nullable. The current maritime estimator supplies water-relative velocity and
    surface current; another platform backend need not invent those states.
    Attitude, validated navigation time, and a validated protection bound are
    still represented explicitly as unavailable when the backend cannot support
    them with evidence.
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
