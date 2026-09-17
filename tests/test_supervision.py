import numpy as np

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    ConstraintCoverage,
    ConstraintSpec,
    NavigationSupervisor,
    NavMode,
    RuntimePolicy,
    SensorHealth,
    SensorHealthManager,
    SourcePolicy,
)
from amep1.types import MeasurementResult


def result(source, accepted, fused=False):
    return MeasurementResult(
        source,
        accepted,
        fused,
        0.1 if accepted else 100.0,
        10.0,
        1,
        "test",
    )


def test_health_isolation_and_recovery_probe_path():
    health = SensorHealthManager()
    health.register(
        "gnss",
        SourcePolicy(max_age_s=1.0, recovery_consecutive_accepts=2),
    )
    health.observe("gnss", 0.0, result("gnss", True))
    for timestamp in (0.1, 0.2, 0.3):
        health.observe("gnss", timestamp, result("gnss", False))
    assert health.state("gnss") == SensorHealth.ISOLATED
    assert not health.may_fuse("gnss")
    health.observe("gnss", 0.4, result("gnss", True))
    assert health.state("gnss") == SensorHealth.ISOLATED
    health.observe("gnss", 0.5, result("gnss", True))
    assert health.state("gnss") == SensorHealth.DEGRADED
    assert health.may_fuse("gnss")
    health.observe("gnss", 0.6, result("gnss", True))
    assert health.state("gnss") == SensorHealth.ONLINE


def test_health_freshness_transitions_to_stale():
    health = SensorHealthManager()
    health.register("gyro", SourcePolicy(max_age_s=0.2))
    health.observe("gyro", 0.0, result("gyro", True))
    health.refresh(0.25)
    assert health.state("gyro") == SensorHealth.STALE


def test_degraded_mode_is_reachable_from_real_rank():
    health = {"water": SensorHealth.ONLINE, "gyro": SensorHealth.ONLINE}
    coverage = ConstraintCoverage()
    coverage.register("water", ConstraintSpec((2, 3)))
    coverage.register("gyro", ConstraintSpec((6,)))
    result_coverage = coverage.compute(health)
    assert result_coverage.information_rank == 3
    supervisor = NavigationSupervisor()
    assert supervisor.update(result_coverage) == NavMode.DEGRADED_DEAD_RECKONING


def test_gnss_full_rank_is_nominal_but_non_gnss_requires_integrity_evidence():
    coverage = ConstraintCoverage()
    coverage.register(
        "gnss",
        ConstraintSpec((0, 1), absolute_position=True, gnss=True),
    )
    coverage.register("radar", ConstraintSpec((0, 1), absolute_position=True))
    coverage.register("water", ConstraintSpec((2, 3)))
    coverage.register("current", ConstraintSpec((4, 5)))
    coverage.register("gyro", ConstraintSpec((6,)))
    supervisor = NavigationSupervisor()

    gnss_health = {
        source: SensorHealth.ONLINE
        for source in ("gnss", "water", "current", "gyro")
    }
    assert supervisor.update(coverage.compute(gnss_health)) == NavMode.NOMINAL

    non_gnss_health = {
        source: SensorHealth.ONLINE
        for source in ("radar", "water", "current", "gyro")
    }
    assert (
        supervisor.update(coverage.compute(non_gnss_health))
        == NavMode.DEGRADED_DEAD_RECKONING
    )
    assert supervisor.reason == "non_gnss_full_coverage_without_integrity_evidence"


def test_safe_hold_when_rank_below_three():
    coverage = ConstraintCoverage()
    coverage.register("gyro", ConstraintSpec((6,)))
    result_coverage = coverage.compute({"gyro": SensorHealth.ONLINE})
    supervisor = NavigationSupervisor()
    assert supervisor.update(result_coverage) == NavMode.SAFE_HOLD


def test_runtime_isolated_source_is_probe_only_until_recovered():
    health = SensorHealthManager()
    health.register(
        "gnss",
        SourcePolicy(max_age_s=1.0, recovery_consecutive_accepts=2),
    )
    coverage = ConstraintCoverage()
    coverage.register(
        "gnss",
        ConstraintSpec((0, 1), absolute_position=True, gnss=True),
    )
    runtime = AMEPRuntime(
        AMEPFilter(P=np.eye(7)),
        health,
        coverage,
        runtime_policy=RuntimePolicy.compatibility(),
    )
    runtime.update_position(
        timestamp_s=0.0,
        source="gnss",
        E=0,
        N=0,
        sigma=1,
    )
    health.manual_isolate("gnss", True)
    before = runtime.estimator.x.copy()
    update = runtime.update_position(
        timestamp_s=0.1,
        source="gnss",
        E=0.1,
        N=0.1,
        sigma=1,
    )
    assert update.accepted and not update.fused
    assert np.allclose(runtime.estimator.x, before)
