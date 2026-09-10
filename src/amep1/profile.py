from __future__ import annotations

from .config import SourcePolicy
from .constraints import ConstraintCoverage, ConstraintSpec
from .health import SensorHealthManager


def build_reference_health_and_constraints() -> tuple[SensorHealthManager, ConstraintCoverage]:
    """Create generic AMEP-1 v1.0 source classes with conservative example freshness.

    Freshness values are integration defaults only and must be replaced with declared
    interface/update-rate budgets for the actual vessel and sensors.
    """
    health = SensorHealthManager()
    coverage = ConstraintCoverage()

    definitions = {
        "gnss": (SourcePolicy(max_age_s=2.0), ConstraintSpec((0, 1), absolute_position=True, gnss=True)),
        "radar_map_fix": (SourcePolicy(max_age_s=3.0), ConstraintSpec((0, 1), absolute_position=True)),
        "bathy_map_fix": (SourcePolicy(max_age_s=5.0), ConstraintSpec((0, 1), absolute_position=True)),
        "visual_map_fix": (SourcePolicy(max_age_s=2.0), ConstraintSpec((0, 1), absolute_position=True)),
        "speed_log": (SourcePolicy(max_age_s=1.0), ConstraintSpec((2, 3))),
        "ground_velocity": (SourcePolicy(max_age_s=1.0), ConstraintSpec((2, 3, 4, 5))),
        "current_prior": (SourcePolicy(max_age_s=30.0), ConstraintSpec((4, 5))),
        "gyrocompass": (SourcePolicy(max_age_s=0.5), ConstraintSpec((6,))),
    }
    for name, (policy, spec) in definitions.items():
        health.register(name, policy)
        coverage.register(name, spec)
    return health, coverage
