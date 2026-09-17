import math

import numpy as np
import pytest

from amep1 import (
    DetectionTrial,
    NMEA0183Adapter,
    NMEA0183StreamDecoder,
    RiskAllocation,
    SensorInstallation,
    SolutionCandidate,
    SolutionSeparationMonitor,
    SourceClass,
    SourceDescriptor,
    SourceRegistry,
    StrapdownESKF,
    StrapdownESKFConfig,
    StrapdownIMUInput,
    derive_fault_hypotheses,
    parse_nmea0183_sentence,
    summarize_detection_trials,
    validate_nmea0183_sentence,
)


def _nmea(payload: str) -> str:
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return f"${payload}*{checksum:02X}"


def _safety_absolute(
    name: str,
    failure_domain: str,
    *,
    dependencies: tuple[str, ...] = (),
) -> SourceDescriptor:
    return SourceDescriptor(
        name=name,
        source_class=SourceClass.ABSOLUTE_POSITION,
        failure_domain=failure_domain,
        absolute_position=True,
        safety_credit=True,
        provenance_required=True,
        max_timestamp_uncertainty_s=0.05,
        assurance_reference=f"test:{name}",
        dependencies=dependencies,
    )


def _calibration_covariance(diagonal: float = 0.01):
    covariance = np.eye(6) * diagonal
    return tuple(tuple(float(value) for value in row) for row in covariance)


def test_strapdown_eskf_stationary_and_position_update():
    config = StrapdownESKFConfig(latitude_deg=27.0, max_dt_s=0.2)
    estimator = StrapdownESKF(config=config, P=np.eye(15) * 0.5)
    earth_rate = tuple(estimator.earth_rate_enu_rps)
    gravity = estimator.gravity_mps2

    estimator.predict(StrapdownIMUInput(0.0, (0.0, 0.0, gravity), earth_rate))
    for step in range(1, 11):
        estimator.predict(
            StrapdownIMUInput(step * 0.1, (0.0, 0.0, gravity), earth_rate)
        )

    assert np.linalg.norm(estimator.position_enu_m) < 1e-6
    assert np.linalg.norm(estimator.velocity_enu_mps) < 1e-6

    before = estimator.containment_proxy()
    result = estimator.update_measurement(
        "position",
        np.array([2.0, -1.0]),
        np.eye(2),
        frame="local_ENU",
        source="gnss",
    )
    assert result.accepted and result.fused
    assert estimator.containment_proxy() < before

    snapshot = estimator.snapshot()
    assert snapshot.covariance.shape == (15, 15)
    assert len(snapshot.covariance_labels) == 15
    assert snapshot.state_schema_id == "amep1.strapdown_eskf.local_enu.v1"


def test_strapdown_eskf_constant_acceleration_and_rejects_outlier():
    config = StrapdownESKFConfig(latitude_deg=0.0, max_dt_s=0.2)
    estimator = StrapdownESKF(config=config, P=np.eye(15) * 0.1)
    earth_rate = tuple(estimator.earth_rate_enu_rps)
    gravity = estimator.gravity_mps2

    estimator.predict(StrapdownIMUInput(0.0, (1.0, 0.0, gravity), earth_rate))
    for step in range(1, 11):
        estimator.predict(
            StrapdownIMUInput(step * 0.1, (1.0, 0.0, gravity), earth_rate)
        )

    assert estimator.velocity_enu_mps[0] == pytest.approx(1.0, abs=5e-3)
    assert estimator.position_enu_m[0] == pytest.approx(0.5, abs=5e-3)

    result = estimator.update_measurement(
        "position",
        np.array([1e5, 1e5]),
        np.eye(2),
        frame="local_ENU",
        source="bad_fix",
    )
    assert not result.accepted
    assert not result.fused


def test_dependency_derived_fde_risk_allocation_and_solution_separation():
    registry = SourceRegistry()
    registry.register(
        _safety_absolute("radar", "radar_chain", dependencies=("shared_clock",))
    )
    registry.register(
        _safety_absolute("vision", "vision_chain", dependencies=("shared_clock",))
    )
    registry.register(_safety_absolute("bathy", "bathy_chain"))

    hypotheses = derive_fault_hypotheses(registry, ("radar", "vision", "bathy"))
    assert any(
        hypothesis.common_cause
        and set(hypothesis.excluded_sources) == {"radar", "vision"}
        for hypothesis in hypotheses
    )

    allocation = RiskAllocation.equal(
        hypotheses,
        total_integrity_risk=1e-3,
        residual_fraction=0.10,
    )
    candidate = SolutionCandidate(
        hypotheses[0],
        (50.0, 0.0),
        ((1.0, 0.0), (0.0, 1.0)),
    )
    report = SolutionSeparationMonitor(default_probability=0.99).evaluate(
        primary_position_m=(0.0, 0.0),
        primary_covariance_m2=((1.0, 0.0), (0.0, 1.0)),
        alternatives=(candidate,),
        risk_allocation=allocation,
    )
    assert report.alert
    assert report.tests[0].alert
    assert report.maximum_normalized_statistic > 1.0


def test_fde_detection_metrics_report_false_alert_miss_and_time_to_alert():
    metrics = summarize_detection_trials(
        (
            DetectionTrial(False, False),
            DetectionTrial(False, True),
            DetectionTrial(True, True, 1.0),
            DetectionTrial(True, False),
            DetectionTrial(True, True, 3.0),
        )
    )
    assert metrics.false_alert_rate == 0.5
    assert metrics.missed_detection_rate == pytest.approx(1.0 / 3.0)
    assert metrics.mean_time_to_alert_s == 2.0
    assert metrics.p95_time_to_alert_s is not None
    assert metrics.p95_time_to_alert_s > 2.0


def test_installation_lever_arm_boresight_and_uncertainty_propagation():
    installation = SensorInstallation(
        sensor_name="dvl",
        sensor_frame="dvl",
        body_frame="body",
        lever_arm_body_m=(2.0, 0.0, 0.0),
        boresight_sensor_to_body_rpy_rad=(0.0, 0.0, 0.0),
        calibration_covariance=_calibration_covariance(),
        calibration_id="cal-1",
        provenance="survey.fixture",
        measured=True,
    )

    corrected = installation.velocity_at_body_origin(
        (0.0, 2.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    assert np.allclose(corrected, (0.0, 0.0, 0.0))

    corrected_with_covariance, covariance = (
        installation.velocity_at_body_origin_with_covariance(
            (0.0, 2.0, 0.0),
            np.eye(3) * 0.1,
            (0.0, 0.0, 1.0),
            angular_rate_covariance_body=np.eye(3) * 0.001,
        )
    )
    assert np.allclose(corrected_with_covariance, (0.0, 0.0, 0.0))
    assert np.min(np.linalg.eigvalsh(covariance)) >= -1e-12


def test_nmea0183_parser_adapter_and_stream_decoder():
    gga = _nmea("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
    parsed = parse_nmea0183_sentence(gga)
    assert parsed.fix_quality == 1

    adapter = NMEA0183Adapter(
        geodetic_to_local=lambda latitude, longitude: (latitude * 10.0, longitude * 10.0)
    )
    position = adapter.adapt_line(
        gga,
        source_timestamp_s=1.0,
        receive_timestamp_s=1.01,
    )[0]
    assert position.source == "gnss"
    assert position.kind == "position"

    rmc = _nmea("GPRMC,123519,A,4807.038,N,01131.000,E,10.0,90.0,230394,003.1,W")
    ground_velocity = adapter.adapt_line(
        rmc,
        source_timestamp_s=1.1,
        receive_timestamp_s=1.11,
    )[0]
    assert ground_velocity.values[0] == pytest.approx(10.0 * 0.5144444444444445)
    assert abs(ground_velocity.values[1]) < 1e-9

    hdt = _nmea("HEHDT,123.4,T")
    heading = adapter.adapt_line(
        hdt,
        source_timestamp_s=1.2,
        receive_timestamp_s=1.21,
    )[0]
    assert heading.values[0] == pytest.approx(math.radians(123.4))

    vhw = _nmea("IIVHW,90.0,T,88.0,M,7.5,N,13.9,K")
    water_velocity = adapter.adapt_line(
        vhw,
        source_timestamp_s=1.3,
        receive_timestamp_s=1.31,
    )[0]
    assert water_velocity.source == "speed_log"
    assert water_velocity.values[0] > 0.0

    decoder = NMEA0183StreamDecoder()
    assert decoder.feed((hdt + "\r\n" + rmc + "\n").encode("ascii")) == (hdt, rmc)

    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_nmea0183_sentence("$HEHDT,123.4,T*00")
