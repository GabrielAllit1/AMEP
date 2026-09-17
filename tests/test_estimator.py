import numpy as np
import pytest

from amep1 import AMEPFilter, EstimatorConfig, HorizontalIMUInput, TimebaseError


def imu(t, af=0.0, ast=0.0, w=0.0, gc=True):
    return HorizontalIMUInput(t, af, ast, w, gc)


def test_predict_preserves_published_water_current_decomposition():
    estimator = AMEPFilter(x=np.array([0, 0, 2, 3, 0.5, -0.25, 0], float))
    estimator.predict(imu(0.0))
    estimator.predict(imu(0.1))
    assert estimator.position == pytest.approx((0.25, 0.275))
    assert estimator.ground_velocity == pytest.approx((2.5, 2.75))


def test_heading_jacobian_matches_finite_difference():
    base = np.array([0, 0, 1, 1, 0, 0, 0.4], float)
    epsilon = 1e-7

    def step(heading):
        estimator = AMEPFilter(x=base.copy())
        estimator.x[6] = heading
        estimator.predict(imu(0.0))
        estimator.predict(imu(0.1, af=0.8, ast=-0.2))
        return estimator.x.copy()

    numeric = (step(base[6] + epsilon) - step(base[6] - epsilon)) / (2 * epsilon)
    heading = base[6]
    a_east = 0.8 * np.sin(heading) + (-0.2) * np.cos(heading)
    a_north = 0.8 * np.cos(heading) - (-0.2) * np.sin(heading)
    expected = np.array(
        [
            0.5 * a_north * 0.1**2,
            -0.5 * a_east * 0.1**2,
            a_north * 0.1,
            -a_east * 0.1,
        ]
    )
    assert numeric[:4] == pytest.approx(expected, abs=1e-8)


def test_raw_specific_force_contract_fails_closed():
    estimator = AMEPFilter()
    with pytest.raises(ValueError):
        estimator.predict(imu(0.0, gc=False))


def test_nonmonotonic_time_fails_closed():
    estimator = AMEPFilter()
    estimator.predict(imu(1.0))
    with pytest.raises(TimebaseError):
        estimator.predict(imu(1.0))


def test_large_prediction_gap_fails_closed():
    estimator = AMEPFilter(config=EstimatorConfig(max_dt_s=0.2))
    estimator.predict(imu(0.0))
    with pytest.raises(TimebaseError):
        estimator.predict(imu(0.3))


def test_position_update_reduces_position_covariance():
    estimator = AMEPFilter()
    before = np.trace(estimator.P[:2, :2])
    result = estimator.update_position(1, -2, 1.0, source="gnss")
    assert result.accepted and result.fused
    assert np.trace(estimator.P[:2, :2]) < before


def test_gross_outlier_is_rejected():
    estimator = AMEPFilter(P=np.eye(7))
    result = estimator.update_position(1e5, -1e5, 1.0, source="gnss")
    assert not result.accepted
    assert not result.fused


def test_ground_velocity_observes_water_plus_current():
    estimator = AMEPFilter(
        x=np.array([0, 0, 2, 3, 1, -1, 0], float), P=np.eye(7)
    )
    result = estimator.update_ground_velocity(3, 2, 0.1, source="dvl_bottom")
    assert result.accepted
    assert estimator.ground_velocity == pytest.approx((3, 2), abs=0.05)


def test_current_prior_is_supported():
    estimator = AMEPFilter(P=np.eye(7) * 2)
    result = estimator.update_current_prior(0.7, -0.4, 0.1, source="current_prior")
    assert result.accepted
    assert estimator.x[4:6] == pytest.approx((0.7, -0.4), abs=0.05)


def test_heading_residual_wraps():
    estimator = AMEPFilter(
        x=np.array([0, 0, 0, 0, 0, 0, np.pi - 0.01]), P=np.eye(7)
    )
    result = estimator.update_heading(-np.pi + 0.01, 0.1, source="gyro")
    assert result.accepted
    assert abs(abs(estimator.heading) - np.pi) < 0.05


def test_covariance_remains_symmetric_psd():
    estimator = AMEPFilter()
    estimator.predict(imu(0.0))
    for index in range(1, 20):
        estimator.predict(imu(index * 0.01, af=0.1, ast=-0.03, w=0.02))
    assert np.allclose(estimator.P, estimator.P.T, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(estimator.P)) > 0


def test_snapshot_publishes_covariance_schema():
    snapshot = AMEPFilter().snapshot()
    assert snapshot.state_schema_id == "amep1.horizontal.v1"
    assert snapshot.covariance.shape == (7, 7)
    assert len(snapshot.covariance_labels) == 7
    assert snapshot.covariance_labels[0:2] == ("E_m", "N_m")
