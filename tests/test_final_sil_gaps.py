import math

import numpy as np
import pytest

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    CompensatedStrapdownESKF,
    ConstraintCoverage,
    ConstraintSpec,
    HorizontalIMUInput,
    MeasurementEnvelope,
    MultiHypothesisReplay,
    ReplayIMUEvent,
    ReplayMeasurementEvent,
    SensorHealthManager,
    SourceClass,
    SourceDescriptor,
    SourcePolicy,
    SourceRegistry,
    StrapdownESKFConfig,
    StrapdownIMUInput,
    compensate_coning_sculling,
)


def _safety_absolute(name: str, failure_domain: str) -> SourceDescriptor:
    return SourceDescriptor(
        name=name,
        source_class=SourceClass.ABSOLUTE_POSITION,
        failure_domain=failure_domain,
        absolute_position=True,
        safety_credit=True,
        provenance_required=True,
        max_timestamp_uncertainty_s=0.05,
        assurance_reference=f"test:{name}",
    )


def _position_envelope(
    source: str,
    timestamp_s: float,
    east_m: float,
    north_m: float,
) -> MeasurementEnvelope:
    return MeasurementEnvelope(
        source=source,
        kind="position",
        source_timestamp_s=timestamp_s,
        receive_timestamp_s=timestamp_s + 0.01,
        values=(east_m, north_m),
        covariance=((1.0, 0.0), (0.0, 1.0)),
        provenance="test.fixture",
        timestamp_uncertainty_s=0.001,
    )


def _fde_runtime() -> AMEPRuntime:
    health = SensorHealthManager()
    coverage = ConstraintCoverage(state_dim=7)
    registry = SourceRegistry()
    for name, domain in (("radar", "radar_chain"), ("vision", "vision_chain")):
        health.register(name, SourcePolicy(max_age_s=10.0))
        coverage.register(name, ConstraintSpec((0, 1), absolute_position=True))
        registry.register(_safety_absolute(name, domain))
    runtime = AMEPRuntime(
        AMEPFilter(),
        health,
        coverage,
        source_registry=registry,
    )
    runtime.seal_configuration()
    return runtime


def test_coning_sculling_compensation_uses_previous_and_current_increments():
    previous_theta = np.array([0.01, 0.0, 0.0])
    current_theta = np.array([0.0, 0.02, 0.0])
    previous_velocity = np.array([0.0, 0.1, 0.0])
    current_velocity = np.array([0.0, 0.0, 0.2])

    corrected_theta, corrected_velocity = compensate_coning_sculling(
        current_theta,
        current_velocity,
        previous_delta_theta_body=previous_theta,
        previous_delta_velocity_body=previous_velocity,
    )

    expected_theta = current_theta + np.cross(previous_theta, current_theta) / 12.0
    expected_velocity = (
        current_velocity
        + 0.5 * np.cross(current_theta, current_velocity)
        + (
            np.cross(previous_theta, current_velocity)
            + np.cross(previous_velocity, current_theta)
        )
        / 12.0
    )
    assert np.allclose(corrected_theta, expected_theta)
    assert np.allclose(corrected_velocity, expected_velocity)


def test_compensated_eskf_stationary_and_transport_rate_geometry():
    estimator = CompensatedStrapdownESKF(
        config=StrapdownESKFConfig(latitude_deg=45.0, max_dt_s=0.2),
        P=np.eye(15) * 0.1,
    )
    gravity = estimator.gravity_mps2
    earth_rate = tuple(estimator.earth_rate_enu_rps)

    estimator.predict(StrapdownIMUInput(0.0, (0.0, 0.0, gravity), earth_rate))
    for step in range(1, 11):
        estimator.predict(
            StrapdownIMUInput(step * 0.1, (0.0, 0.0, gravity), earth_rate)
        )

    assert np.linalg.norm(estimator.velocity_enu_mps) < 1e-5
    assert np.linalg.norm(estimator.position_enu_m) < 1e-5

    r_m, r_n = estimator.curvature_radii_m
    assert r_m > 6.0e6
    assert r_n > 6.0e6
    transport = estimator.transport_rate_enu_rps(np.array([10.0, 0.0, 0.0]))
    assert transport[0] == pytest.approx(0.0)
    assert transport[1] == pytest.approx(10.0 / (r_n + estimator.current_altitude_m))
    assert transport[2] == pytest.approx(
        10.0 * math.tan(estimator.current_latitude_rad)
        / (r_n + estimator.current_altitude_m)
    )


def test_lever_arm_position_and_velocity_models_include_attitude_jacobians():
    estimator = CompensatedStrapdownESKF(P=np.eye(15))
    lever = np.array([2.0, 0.0, 0.0])

    predicted_position, position_h = estimator.position_measurement_model(
        dimension=3,
        lever_arm_body_m=lever,
    )
    assert np.allclose(predicted_position, (2.0, 0.0, 0.0))
    assert position_h[1, 8] == pytest.approx(2.0)
    assert position_h[2, 7] == pytest.approx(-2.0)

    predicted_velocity, velocity_h = estimator.ground_velocity_measurement_model(
        dimension=3,
        lever_arm_body_m=lever,
        angular_rate_body_rps=(0.0, 0.0, 1.0),
    )
    assert np.allclose(predicted_velocity, (0.0, 2.0, 0.0))
    assert np.linalg.norm(velocity_h[:, 6:9]) > 0.0

    result = estimator.update_measurement(
        "position",
        predicted_position[:2],
        np.eye(2) * 0.1,
        frame="local_ENU",
        source="gnss_antenna",
        metadata={"lever_arm_body_m": tuple(lever)},
    )
    assert result.accepted
    assert result.fused
    assert result.nis == pytest.approx(0.0)


def test_raw_imu_velocity_lever_arm_model_couples_gyro_bias():
    estimator = CompensatedStrapdownESKF(P=np.eye(15))
    _, h = estimator.ground_velocity_measurement_model(
        dimension=3,
        lever_arm_body_m=(1.5, 0.2, 0.0),
        angular_rate_body_rps=(0.0, 0.0, 0.5),
        angular_rate_is_raw_imu=True,
    )
    assert np.linalg.norm(h[:, 12:15]) > 0.0


def test_multi_hypothesis_replay_generates_subset_solutions_from_events():
    events = (
        ReplayIMUEvent(0, HorizontalIMUInput(0.0, 0.0, 0.0, 0.0)),
        ReplayIMUEvent(1, HorizontalIMUInput(0.1, 0.0, 0.0, 0.0)),
        ReplayMeasurementEvent(2, _position_envelope("radar", 1.0, 0.0, 0.0)),
        ReplayMeasurementEvent(3, _position_envelope("vision", 1.1, 0.5, 0.0)),
        ReplayMeasurementEvent(4, _position_envelope("radar", 2.0, 1.0, 0.0)),
        ReplayMeasurementEvent(5, _position_envelope("vision", 2.1, 1.5, 0.0)),
    )

    result = MultiHypothesisReplay(_fde_runtime).run(
        events,
        total_integrity_risk=1e-2,
    )

    assert result.primary.events_processed == len(events)
    assert len(result.alternatives) == 2
    assert {item.hypothesis.excluded_sources for item in result.alternatives} == {
        ("radar",),
        ("vision",),
    }
    assert all(item.excluded_measurement_events == 2 for item in result.alternatives)
    assert all(item.replay.measurement_events == 2 for item in result.alternatives)
    assert len(result.separation.tests) == 2
    assert {
        test.hypothesis_name for test in result.separation.tests
    } == {item.hypothesis.name for item in result.alternatives}
    assert sum(probability for _, probability in result.risk_allocation.hypothesis_allocations) < 1e-2
