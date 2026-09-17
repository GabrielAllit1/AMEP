from __future__ import annotations

from .config import RuntimePolicy, SourcePolicy
from .constraints import ConstraintCoverage, ConstraintSpec
from .health import SensorHealthManager
from .source_registry import SourceClass, SourceDescriptor, SourceRegistry


def build_reference_health_and_constraints() -> tuple[
    SensorHealthManager, ConstraintCoverage
]:
    """Create the published seven-state research source/coverage profile.

    Freshness values are research integration defaults. They are not vessel,
    sensor, bus, or mission requirements and must be replaced by the platform
    integration profile before operational use.
    """
    health = SensorHealthManager()
    coverage = ConstraintCoverage(state_dim=7)

    definitions = {
        "gnss": (
            SourcePolicy(max_age_s=2.0),
            ConstraintSpec((0, 1), absolute_position=True, gnss=True),
        ),
        "radar_map_fix": (
            SourcePolicy(max_age_s=3.0),
            ConstraintSpec((0, 1), absolute_position=True),
        ),
        "bathy_map_fix": (
            SourcePolicy(max_age_s=5.0),
            ConstraintSpec((0, 1), absolute_position=True),
        ),
        "visual_map_fix": (
            SourcePolicy(max_age_s=2.0),
            ConstraintSpec((0, 1), absolute_position=True),
        ),
        "speed_log": (SourcePolicy(max_age_s=1.0), ConstraintSpec((2, 3))),
        "ground_velocity": (
            SourcePolicy(max_age_s=1.0),
            ConstraintSpec((2, 3, 4, 5)),
        ),
        "current_prior": (
            SourcePolicy(max_age_s=30.0),
            ConstraintSpec((4, 5)),
        ),
        "gyrocompass": (SourcePolicy(max_age_s=0.5), ConstraintSpec((6,))),
    }
    for name, (policy, spec) in definitions.items():
        health.register(name, policy)
        coverage.register(name, spec)
    return health, coverage


def build_research_reference_source_registry() -> SourceRegistry:
    """Declare research source roles without granting unverified safety credit.

    Failure-domain labels document intended physical diversity only. The research
    profile has no verified vehicle dependency analysis, adapter provenance
    contract, or timestamp-uncertainty budget, so no source receives integrity
    safety credit. A platform profile must explicitly opt sources into safety
    credit after those requirements are defined and validated.
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
        SourceDescriptor(
            "speed_log",
            SourceClass.WATER_VELOCITY,
            "water_speed_sensor_chain",
        ),
        SourceDescriptor(
            "ground_velocity",
            SourceClass.GROUND_VELOCITY,
            "ground_velocity_sensor_chain",
        ),
        SourceDescriptor(
            "current_prior",
            SourceClass.CURRENT_PRIOR,
            "environmental_current_model_chain",
        ),
        SourceDescriptor(
            "gyrocompass",
            SourceClass.HEADING,
            "heading_sensor_chain",
        ),
    )
    for descriptor in descriptors:
        registry.register(descriptor)
    return registry


def build_research_reference_runtime():
    """Construct the conservative research reference runtime.

    Every measurement must traverse the normalized ingestion path and every source
    must have a registered contract. The included source declarations intentionally
    grant no non-GNSS resilience safety credit.
    """
    from .estimator import AMEPFilter
    from .runtime import AMEPRuntime

    health, coverage = build_reference_health_and_constraints()
    return AMEPRuntime(
        AMEPFilter(),
        health,
        coverage,
        source_registry=build_research_reference_source_registry(),
        runtime_policy=RuntimePolicy(
            allow_legacy_direct_updates=False,
            require_registered_sources=True,
        ),
    )


def build_reference_source_registry() -> SourceRegistry:
    """Compatibility alias for ``build_research_reference_source_registry``."""
    return build_research_reference_source_registry()


def build_reference_runtime():
    """Compatibility alias for ``build_research_reference_runtime``."""
    return build_research_reference_runtime()
