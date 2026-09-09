import numpy as np
import pytest

from amep1 import AMEPFilter, EstimatorConfig, HorizontalIMUInput, TimebaseError


def imu(t, af=0.0, ast=0.0, w=0.0, gc=True):
    return HorizontalIMUInput(t, af, ast, w, gc)


def test_predict_preserves_published_water_current_decomposition():
    f = AMEPFilter(x=np.array([0, 0, 2, 3, 0.5, -0.25, 0], float))
    f.predict(imu(0.0))
    f.predict(imu(0.1))
    assert f.position == pytest.approx((0.25, 0.275))
    assert f.ground_velocity == pytest.approx((2.5, 2.75))


def test_heading_jacobian_matches_finite_difference():
    base = np.array([0, 0, 1, 1, 0, 0, 0.4], float)
    eps = 1e-7
    def step(psi):
        f = AMEPFilter(x=base.copy())
        f.x[6] = psi
        f.predict(imu(0.0))
        f.predict(imu(0.1, af=0.8, ast=-0.2))
        return f.x.copy()
    numeric = (step(base[6] + eps) - step(base[6] - eps)) / (2 * eps)
    psi = base[6]
    aE = 0.8*np.sin(psi) + (-0.2)*np.cos(psi)
    aN = 0.8*np.cos(psi) - (-0.2)*np.sin(psi)
    expected = np.array([0.5*aN*0.1**2, -0.5*aE*0.1**2, aN*0.1, -aE*0.1])
    assert numeric[:4] == pytest.approx(expected, abs=1e-8)


def test_raw_specific_force_contract_fails_closed():
    f = AMEPFilter()
    with pytest.raises(ValueError):
        f.predict(imu(0.0, gc=False))


def test_nonmonotonic_time_fails_closed():
    f = AMEPFilter()
    f.predict(imu(1.0))
    with pytest.raises(TimebaseError):
        f.predict(imu(1.0))


def test_large_prediction_gap_fails_closed():
    f = AMEPFilter(config=EstimatorConfig(max_dt_s=0.2))
    f.predict(imu(0.0))
    with pytest.raises(TimebaseError):
        f.predict(imu(0.3))


def test_position_update_reduces_position_covariance():
    f = AMEPFilter()
    before = np.trace(f.P[:2, :2])
    r = f.update_position(1, -2, 1.0, source="gnss")
    assert r.accepted and r.fused
    assert np.trace(f.P[:2, :2]) < before


def test_gross_outlier_is_rejected():
    f = AMEPFilter(P=np.eye(7))
    r = f.update_position(1e5, -1e5, 1.0, source="gnss")
    assert not r.accepted
    assert not r.fused


def test_ground_velocity_observes_water_plus_current():
    f = AMEPFilter(x=np.array([0,0,2,3,1,-1,0], float), P=np.eye(7))
    r = f.update_ground_velocity(3, 2, 0.1, source="dvl_bottom")
    assert r.accepted
    assert f.ground_velocity == pytest.approx((3,2), abs=0.05)


def test_current_prior_is_supported():
    f = AMEPFilter(P=np.eye(7)*2)
    r = f.update_current_prior(0.7, -0.4, 0.1, source="current_prior")
    assert r.accepted
    assert f.x[4:6] == pytest.approx((0.7, -0.4), abs=0.05)


def test_heading_residual_wraps():
    f = AMEPFilter(x=np.array([0,0,0,0,0,0,np.pi-0.01]), P=np.eye(7))
    r = f.update_heading(-np.pi+0.01, 0.1, source="gyro")
    assert r.accepted
    assert abs(abs(f.heading) - np.pi) < 0.05


def test_covariance_remains_symmetric_psd():
    f = AMEPFilter()
    f.predict(imu(0.0))
    for i in range(1,20):
        f.predict(imu(i*0.01, af=0.1, ast=-0.03, w=0.02))
    assert np.allclose(f.P, f.P.T, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(f.P)) > 0
