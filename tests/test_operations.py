import pytest

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    CommunicationsSupervisor,
    DeadlineWatchdog,
    HorizontalIMUInput,
    LinkPolicy,
    NavMode,
    TimebaseError,
    build_reference_health_and_constraints,
)


def test_comms_priority_and_failover():
    c = CommunicationsSupervisor()
    c.register("primary", LinkPolicy(priority=0, max_heartbeat_age_s=1.0))
    c.register("secondary", LinkPolicy(priority=1, max_heartbeat_age_s=3.0))
    c.heartbeat("primary", 0.0); c.heartbeat("secondary", 0.0)
    assert c.active_link(0.5) == "primary"
    assert c.active_link(1.5) == "secondary"
    assert c.active_link(3.5) is None


def test_watchdog_detects_deadline_and_nonmonotonic_time():
    w = DeadlineWatchdog(expected_period_s=0.1, deadline_s=0.15)
    assert w.observe(0.0).ok
    assert w.observe(0.1).ok
    miss = w.observe(0.30)
    assert not miss.ok and miss.reason == "deadline_missed"
    bad = w.observe(0.29)
    assert not bad.ok and bad.reason == "non_monotonic_time"


def test_reference_profile_has_published_generic_sources():
    health, coverage = build_reference_health_and_constraints()
    states = health.states()
    assert {"gnss","radar_map_fix","bathy_map_fix","visual_map_fix","speed_log","ground_velocity","current_prior","gyrocompass"} <= set(states)
    assert coverage.compute(states).information_rank == 0


def test_runtime_prediction_fault_latches_safe_hold():
    health, coverage = build_reference_health_and_constraints()
    rt = AMEPRuntime(AMEPFilter(), health, coverage)
    rt.predict(HorizontalIMUInput(1.0, 0, 0, 0))
    with pytest.raises(TimebaseError):
        rt.predict(HorizontalIMUInput(1.0, 0, 0, 0))
    assert rt.status(1.0).mode == NavMode.SAFE_HOLD
    assert rt.hard_fault_reason is not None
