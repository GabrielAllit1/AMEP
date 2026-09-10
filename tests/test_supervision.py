import numpy as np

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    ConstraintCoverage,
    ConstraintSpec,
    NavMode,
    NavigationSupervisor,
    SensorHealth,
    SensorHealthManager,
    SourcePolicy,
)
from amep1.types import MeasurementResult


def result(source, accepted, fused=False):
    return MeasurementResult(source, accepted, fused, 0.1 if accepted else 100.0, 10.0, 1, "test")


def test_health_isolation_and_recovery_probe_path():
    h = SensorHealthManager()
    h.register("gnss", SourcePolicy(max_age_s=1.0, recovery_consecutive_accepts=2))
    h.observe("gnss", 0.0, result("gnss", True))
    for t in (0.1,0.2,0.3):
        h.observe("gnss", t, result("gnss", False))
    assert h.state("gnss") == SensorHealth.ISOLATED
    assert not h.may_fuse("gnss")
    h.observe("gnss", 0.4, result("gnss", True))
    assert h.state("gnss") == SensorHealth.ISOLATED
    h.observe("gnss", 0.5, result("gnss", True))
    assert h.state("gnss") == SensorHealth.DEGRADED
    assert h.may_fuse("gnss")
    h.observe("gnss", 0.6, result("gnss", True))
    assert h.state("gnss") == SensorHealth.ONLINE


def test_health_freshness_transitions_to_stale():
    h = SensorHealthManager()
    h.register("gyro", SourcePolicy(max_age_s=0.2))
    h.observe("gyro", 0.0, result("gyro", True))
    h.refresh(0.25)
    assert h.state("gyro") == SensorHealth.STALE


def test_degraded_mode_is_reachable_from_real_rank():
    h = {"water": SensorHealth.ONLINE, "gyro": SensorHealth.ONLINE}
    c = ConstraintCoverage()
    c.register("water", ConstraintSpec((2,3)))
    c.register("gyro", ConstraintSpec((6,)))
    cov = c.compute(h)
    assert cov.information_rank == 3
    s = NavigationSupervisor()
    assert s.update(cov) == NavMode.DEGRADED_DEAD_RECKONING


def test_gnss_full_rank_nominal_and_non_gnss_full_rank_resilient():
    c = ConstraintCoverage()
    c.register("gnss", ConstraintSpec((0,1), absolute_position=True, gnss=True))
    c.register("radar", ConstraintSpec((0,1), absolute_position=True))
    c.register("water", ConstraintSpec((2,3)))
    c.register("current", ConstraintSpec((4,5)))
    c.register("gyro", ConstraintSpec((6,)))
    s = NavigationSupervisor()

    health = {k: SensorHealth.ONLINE for k in ("gnss","water","current","gyro")}
    assert s.update(c.compute(health)) == NavMode.NOMINAL

    health = {k: SensorHealth.ONLINE for k in ("radar","water","current","gyro")}
    assert s.update(c.compute(health)) == NavMode.GPS_DENIED_RESILIENT


def test_safe_hold_when_rank_below_three():
    c = ConstraintCoverage(); c.register("gyro", ConstraintSpec((6,)))
    cov = c.compute({"gyro": SensorHealth.ONLINE})
    s = NavigationSupervisor()
    assert s.update(cov) == NavMode.SAFE_HOLD


def test_runtime_isolated_source_is_probe_only_until_recovered():
    h = SensorHealthManager(); h.register("gnss", SourcePolicy(max_age_s=1.0, recovery_consecutive_accepts=2))
    c = ConstraintCoverage(); c.register("gnss", ConstraintSpec((0,1), absolute_position=True, gnss=True))
    rt = AMEPRuntime(AMEPFilter(P=np.eye(7)), h, c)
    # establish source, then isolate manually
    rt.update_position(timestamp_s=0.0, source="gnss", E=0, N=0, sigma=1)
    h.manual_isolate("gnss", True)
    before = rt.estimator.x.copy()
    r = rt.update_position(timestamp_s=0.1, source="gnss", E=0.1, N=0.1, sigma=1)
    assert r.accepted and not r.fused
    assert np.allclose(rt.estimator.x, before)
