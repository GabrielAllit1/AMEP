from __future__ import annotations

from .config import SourcePolicy
from .constraints import ConstraintCoverage, ConstraintSpec
from .health import SensorHealthManager
from .source_registry import SourceClass, SourceDescriptor, SourceRegistry


def build_reference_health_and_constraints() -> tuple[SensorHealthManager, ConstraintCoverage]:
    """Create generic AMEP-1 source classes with conservative example freshness.

    Freshness values are integration defaults only and must be replaced with declared
    interface/update-rate budgets for the actual vehicle and sensors.
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


def build_reference_source_registry() -> SourceRegistry:
    """Declare reference source roles and *declared* common-cause domains.

    Domain names are architectural assumptions for integrity bookkeeping, not
    evidence of statistical independence. A vehicle integration must replace or
    refine them from its actual sensor, clock, map, RF, power, compute, and data
    dependency analysis before taking safety credit.
    """
    registry = SourceRegistry()
    descriptors = (
        SourceDescriptor(
            "gnss",
            SourceClass.ABSOLUTE_POSITION,
            "gnss_rf_space_receiver_chain",
            absolute_position=True,
            gnss=True,
        ),
        SourceDescriptor(
            "radar_map_fix",
            SourceClass.ABSOLUTE_POSITION,
            "radar_map_localization_chain",
            absolute_position=True,
        ),
        SourceDescriptor(
            "bathy_map_fix",
            SourceClass.ABSOLUTE_POSITION,
            "bathymetry_map_localization_chain",
            absolute_position=True,
        ),
        SourceDescriptor(
            "visual_map_fix",
            SourceClass.ABSOLUTE_POSITION,
            "vision_map_localization_chain",
            absolute_position=True,
        ),
        SourceDescriptor("speed_log", SourceClass.WATER_VELOCITY, "water_speed_sensor_chain"),
        SourceDescriptor("ground_velocity", SourceClass.GROUND_VELOCITY, "ground_velocity_sensor_chain"),
        SourceDescriptor("current_prior", SourceClass.CURRENT_PRIOR, "environmental_current_model_chain"),
        SourceDescriptor("gyrocompass", SourceClass.HEADING, "heading_sensor_chain"),
    )
    for descriptor in descriptors:
        registry.register(descriptor)
    return registry
