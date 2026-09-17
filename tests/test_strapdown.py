import numpy as np
import pytest

from amep1.strapdown import RawIMUInput, StrapdownINSBackend, StrapdownINSConfig


def raw_imu(t, *, fx=0.0, fy=0.0, fz=None, wx=0.0, wy=0.0, wz=0.0, gravity=9.80665):
    return RawIMUInput(
        timestamp_s=t,
        specific_force_body_mps2=(fx, fy, -gravity if fz is None else fz),
        angular_rate_body_rps=(wx, wy, wz),
    )


def test_stationary_level_imu_does_not_create_horizontal_motion():
    backend = StrapdownINSBackend()
    backend.predict(raw_imu(0.0))
    for index in range(1, 101):
        backend.predict(raw_imu(index * 0.01))

    assert backend.position_ned_m == pytest.approx((0.0, 0.0, 0.0), abs=1e-10)
    assert backend.velocity_ned_mps == pytest.approx((0.0, 0.0, 0.0), abs=1e-10)


def test_forward_specific_force_propagates_north_at_heading_zero():
    backend = StrapdownINSBackend()
    backend.predict(raw_imu(0.0, fx=1.0))
    for index in range(1, 101):
        backend.predict(raw_imu(index * 0.01, fx=1.0))

    assert backend.velocity_ned_mps[0] == pytest.approx(1.0, abs=1e-10)
    assert backend.position_ned_m[0] == pytest.approx(0.5, abs=1e-10)
    assert backend.snapshot().north_m == pytest.approx(0.5, abs=1e-10)


def test_declared_accelerometer_bias_is_removed_from_mechanization():
    backend = StrapdownINSBackend(
        accel_bias_body_mps2=np.array([0.2, 0.0, 0.0], dtype=float)
    )
    backend.predict(raw_imu(0.0, fx=0.2))
    for index in range(1, 51):
        backend.predict(raw_imu(index * 0.01, fx=0.2))

    assert backend.velocity_ned_mps == pytest.approx((0.0, 0.0, 0.0), abs=1e-10)


def test_heading_integrates_bias_corrected_body_rate():
    backend = StrapdownINSBackend(
        gyro_bias_body_rps=np.array([0.0, 0.0, 0.1], dtype=float)
    )
    backend.predict(raw_imu(0.0, wz=0.1))
    for index in range(1, 101):
        backend.predict(raw_imu(index * 0.01, wz=0.1))

    assert backend.snapshot().heading_rad == pytest.approx(0.0, abs=1e-10)


def test_position_measurement_uses_enu_contract_and_reduces_covariance():
    backend = StrapdownINSBackend(P=np.eye(15, dtype=float) * 10.0)
    before = float(np.trace(backend.P[:2, :2]))
    result = backend.update_measurement(
        "position",
        np.array([0.2, -0.1], dtype=float),
        np.eye(2, dtype=float) * 0.25,
        frame="local_ENU",
        source="gnss",
    )

    assert result.accepted and result.fused
    assert backend.snapshot().east_m > 0.0
    assert backend.snapshot().north_m < 0.0
    assert float(np.trace(backend.P[:2, :2])) < before


def test_strapdown_time_and_covariance_contracts_fail_closed():
    backend = StrapdownINSBackend(config=StrapdownINSConfig(max_dt_s=0.02))
    backend.predict(raw_imu(0.0))
    with pytest.raises(ValueError, match="prediction gap"):
        backend.predict(raw_imu(0.03))

    with pytest.raises(ValueError, match="positive definite"):
        StrapdownINSBackend().update_measurement(
            "position",
            np.array([0.0, 0.0]),
            np.zeros((2, 2)),
            frame="local_ENU",
            source="gnss",
        )


def test_strapdown_covariance_remains_symmetric_psd():
    backend = StrapdownINSBackend()
    backend.predict(raw_imu(0.0, fx=0.1, wz=0.01))
    for index in range(1, 101):
        backend.predict(raw_imu(index * 0.01, fx=0.1, wz=0.01))

    assert np.allclose(backend.P, backend.P.T, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(backend.P)) > 0.0
    snapshot = backend.snapshot()
    assert snapshot.state_schema_id == "amep1.strapdown_eskf.local_ned.v1"
    assert snapshot.covariance.shape == (15, 15)
    assert len(snapshot.covariance_labels) == 15
