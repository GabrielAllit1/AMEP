import math

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
    communications = CommunicationsSupervisor()
    communications.register(
        "primary",
        LinkPolicy(priority=0, max_heartbeat_age_s=1.0),
    )
    communications.register(
        "secondary",
        LinkPolicy(priority=1, max_heartbeat_age_s=3.0),
    )
    communications.heartbeat("primary", 0.0)
    communications.heartbeat("secondary", 0.0)

    assert communications.active_link(0.5) == "primary"
    assert communications.active_link(1.5) == "secondary"
    assert communications.active_link(3.5) is None


def test_future_dated_heartbeat_is_not_healthy_beyond_declared_skew():
    communications = CommunicationsSupervisor()
    communications.register(
        "primary",
        LinkPolicy(
            priority=0,
            max_heartbeat_age_s=1.0,
            max_future_skew_s=0.05,
        ),
    )
    communications.heartbeat("primary", 10.0)

    assert communications.active_link(9.90) is None
    assert communications.active_link(9.97) == "primary"


def test_non_finite_heartbeat_is_rejected():
    communications = CommunicationsSupervisor()
    communications.register(
        "primary",
        LinkPolicy(priority=0, max_heartbeat_age_s=1.0),
    )
    with pytest.raises(ValueError, match="finite"):
        communications.heartbeat("primary", math.nan)


def test_watchdog_detects_deadline_and_nonmonotonic_time():
    watchdog = DeadlineWatchdog(expected_period_s=0.1, deadline_s=0.15)
    initialized = watchdog.observe(0.0)
    on_period = watchdog.observe(0.1)
    miss = watchdog.observe(0.30)
    bad = watchdog.observe(0.29)

    assert initialized.ok
    assert on_period.ok and on_period.reason == "on_period"
    assert on_period.period_error_s == pytest.approx(0.0)
    assert not miss.ok and miss.reason == "deadline_missed"
    assert miss.period_error_s == pytest.approx(0.10)
    assert not bad.ok and bad.reason == "non_monotonic_time"


def test_watchdog_rejects_non_finite_time():
    watchdog = DeadlineWatchdog(expected_period_s=0.1, deadline_s=0.15)
    result = watchdog.observe(math.inf)
    assert not result.ok
    assert result.reason == "non_finite_time"


def test_reference_profile_has_published_generic_sources():
    health, coverage = build_reference_health_and_constraints()
    states = health.states()
    expected = {
        "gnss",
        "radar_map_fix",
        "bathy_map_fix",
        "visual_map_fix",
        "speed_log",
        "ground_velocity",
        "current_prior",
        "gyrocompass",
    }
    assert expected <= set(states)
    assert coverage.compute(states).information_rank == 0


def test_runtime_prediction_fault_latches_safe_hold():
    health, coverage = build_reference_health_and_constraints()
    runtime = AMEPRuntime(AMEPFilter(), health, coverage)
    runtime.predict(HorizontalIMUInput(1.0, 0, 0, 0))
    with pytest.raises(TimebaseError):
        runtime.predict(HorizontalIMUInput(1.0, 0, 0, 0))
    assert runtime.status(1.0).mode == NavMode.SAFE_HOLD
    assert runtime.hard_fault_reason is not None
