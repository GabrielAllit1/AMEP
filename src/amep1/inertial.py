from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import cos, isfinite, radians, sin, sqrt

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.stats import chi2

from .backend import EstimatorSnapshot
from .math_utils import nearest_psd, require_finite, symmetrize, wrap_angle
from .types import MeasurementResult


def _skew(v: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(v, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def _quat_normalize(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float).reshape(4)
    n = float(np.linalg.norm(q))
    if not isfinite(n) or n <= 0.0:
        raise ValueError("quaternion must have finite non-zero norm")
    q = q / n
    return -q if q[0] < 0.0 else q


def _quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dtype=float,
    )


def _quat_from_rotvec(rotvec: np.ndarray) -> np.ndarray:
    r = np.asarray(rotvec, dtype=float).reshape(3)
    angle = float(np.linalg.norm(r))
    if angle < 1e-12:
        return _quat_normalize(np.array([1.0, *(0.5 * r)], dtype=float))
    axis = r / angle
    half = 0.5 * angle
    return np.array([np.cos(half), *(axis * np.sin(half))], dtype=float)


def _quat_to_dcm(q: np.ndarray) -> np.ndarray:
    w, x, y, z = _quat_normalize(q)
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _yaw_from_dcm(c_nb: np.ndarray) -> float:
    # ENU yaw: 0 = north (+Y), +pi/2 = east (+X), matching the AMEP convention.
    forward_n = c_nb[:, 0]
    return wrap_angle(float(np.arctan2(forward_n[0], forward_n[1])))


def _gravity_magnitude(latitude_rad: float, altitude_m: float) -> float:
    s2 = sin(latitude_rad) ** 2
    g0 = 9.7803253359 * (1.0 + 0.00193185265241 * s2) / sqrt(
        1.0 - 0.00669437999013 * s2
    )
    return float(g0 - 3.086e-6 * altitude_m)


@dataclass(frozen=True)
class StrapdownIMUInput:
    """Raw strapdown IMU sample.

    Specific force and angular rate are expressed in the body frame. Unlike
    ``HorizontalIMUInput``, gravity must *not* be removed before constructing
    this object.
    """

    timestamp_s: float
    specific_force_body_mps2: tuple[float, float, float]
    angular_rate_body_rps: tuple[float, float, float]

    def validate(self) -> None:
        values = np.array(
            [
                self.timestamp_s,
                *self.specific_force_body_mps2,
                *self.angular_rate_body_rps,
            ],
            dtype=float,
        )
        require_finite("strapdown IMU sample", values)


@dataclass(frozen=True)
class StrapdownESKFConfig:
    """Local-level 15-error-state ESKF configuration for SIL and integration work.

    Noise values are spectral-density / random-walk assumptions, not calibrated
    values for any particular IMU. Platform deployment must replace them with
    measured values and validate the frame/timebase assumptions.
    """

    latitude_deg: float = 0.0
    altitude_m: float = 0.0
    gate_probability: float = 0.997
    containment_probability: float = 0.95
    min_dt_s: float = 1e-6
    max_dt_s: float = 0.10
    covariance_eigen_floor: float = 1e-12
    accel_noise_density_mps2_sqrt_hz: float = 0.03
    gyro_noise_density_rps_sqrt_hz: float = radians(0.02)
    accel_bias_random_walk_mps2_sqrt_hz: float = 0.001
    gyro_bias_random_walk_rps_sqrt_hz: float = radians(0.002)
    earth_rate_rad_s: float = 7.292115e-5

    def __post_init__(self) -> None:
        numeric = {
            "latitude_deg": self.latitude_deg,
            "altitude_m": self.altitude_m,
            "gate_probability": self.gate_probability,
            "containment_probability": self.containment_probability,
            "min_dt_s": self.min_dt_s,
            "max_dt_s": self.max_dt_s,
            "covariance_eigen_floor": self.covariance_eigen_floor,
            "accel_noise_density_mps2_sqrt_hz": self.accel_noise_density_mps2_sqrt_hz,
            "gyro_noise_density_rps_sqrt_hz": self.gyro_noise_density_rps_sqrt_hz,
            "accel_bias_random_walk_mps2_sqrt_hz": self.accel_bias_random_walk_mps2_sqrt_hz,
            "gyro_bias_random_walk_rps_sqrt_hz": self.gyro_bias_random_walk_rps_sqrt_hz,
            "earth_rate_rad_s": self.earth_rate_rad_s,
        }
        if not all(isfinite(float(v)) for v in numeric.values()):
            raise ValueError("StrapdownESKFConfig values must be finite")
        if not -90.0 <= self.latitude_deg <= 90.0:
            raise ValueError("latitude_deg must be in [-90, 90]")
        if not 0.5 < self.gate_probability < 1.0:
            raise ValueError("gate_probability must be in (0.5, 1.0)")
        if not 0.5 < self.containment_probability < 1.0:
            raise ValueError("containment_probability must be in (0.5, 1.0)")
        if self.min_dt_s <= 0.0 or self.max_dt_s <= self.min_dt_s:
            raise ValueError("invalid ESKF dt bounds")
        if self.covariance_eigen_floor <= 0.0:
            raise ValueError("covariance_eigen_floor must be > 0")
        if any(
            value < 0.0
            for value in (
                self.accel_noise_density_mps2_sqrt_hz,
                self.gyro_noise_density_rps_sqrt_hz,
                self.accel_bias_random_walk_mps2_sqrt_hz,
                self.gyro_bias_random_walk_rps_sqrt_hz,
                self.earth_rate_rad_s,
            )
        ):
            raise ValueError("ESKF noise densities and earth rate must be >= 0")


@dataclass
class StrapdownESKF:
    """Local-ENU strapdown INS / 15-error-state ESKF reference backend.

    Nominal state: position(3), velocity(3), body-to-ENU quaternion(4),
    accelerometer bias(3), gyroscope bias(3). The covariance is over the standard
    15-state error vector [dp, dv, dtheta, dba, dbg]. Earth rotation, local WGS-84
    normal gravity, Coriolis acceleration, IMU bias states, Joseph updates, and
    covariance-reset after attitude injection are represented.

    This closes the *software implementation* gap for a replaceable inertial
    backend. It does not constitute IMU calibration, coning/sculling validation,
    target-hardware timing evidence, or operational maritime validation.
    """

    config: StrapdownESKFConfig = field(default_factory=StrapdownESKFConfig)
    position_enu_m: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    velocity_enu_mps: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    quaternion_body_to_enu: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    )
    accel_bias_body_mps2: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    gyro_bias_body_rps: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    P: np.ndarray = field(default_factory=lambda: np.eye(15, dtype=float))
    last_t: float | None = None
    measurement_kinds: tuple[str, ...] = field(
        init=False, default=("position", "ground_velocity", "heading")
    )
    accepted_frames: tuple[str, ...] = field(init=False, default=("local_ENU",))

    def __post_init__(self) -> None:
        self.position_enu_m = np.asarray(self.position_enu_m, dtype=float).reshape(3)
        self.velocity_enu_mps = np.asarray(self.velocity_enu_mps, dtype=float).reshape(3)
        self.quaternion_body_to_enu = _quat_normalize(self.quaternion_body_to_enu)
        self.accel_bias_body_mps2 = np.asarray(self.accel_bias_body_mps2, dtype=float).reshape(3)
        self.gyro_bias_body_rps = np.asarray(self.gyro_bias_body_rps, dtype=float).reshape(3)
        self.P = np.asarray(self.P, dtype=float).reshape(15, 15)
        for name, value in (
            ("position", self.position_enu_m),
            ("velocity", self.velocity_enu_mps),
            ("accelerometer bias", self.accel_bias_body_mps2),
            ("gyroscope bias", self.gyro_bias_body_rps),
            ("covariance", self.P),
        ):
            require_finite(name, value)
        self.P = nearest_psd(self.P, self.config.covariance_eigen_floor)

    @property
    def latitude_rad(self) -> float:
        return radians(self.config.latitude_deg)

    @property
    def gravity_mps2(self) -> float:
        return _gravity_magnitude(self.latitude_rad, self.config.altitude_m)

    @property
    def earth_rate_enu_rps(self) -> np.ndarray:
        lat = self.latitude_rad
        rate = self.config.earth_rate_rad_s
        return np.array([0.0, rate * cos(lat), rate * sin(lat)], dtype=float)

    def predict(self, prediction_input: object) -> float:
        if not isinstance(prediction_input, StrapdownIMUInput):
            raise TypeError("StrapdownESKF expects StrapdownIMUInput prediction data")
        imu = prediction_input
        imu.validate()
        if self.last_t is None:
            self.last_t = float(imu.timestamp_s)
            return 0.0
        dt = float(imu.timestamp_s - self.last_t)
        if dt < self.config.min_dt_s:
            raise ValueError(f"non-monotonic or too-small ESKF dt: {dt:.9f}s")
        if dt > self.config.max_dt_s:
            raise ValueError(
                f"ESKF prediction gap {dt:.6f}s exceeds max_dt_s={self.config.max_dt_s:.6f}s"
            )
        self.last_t = float(imu.timestamp_s)

        f_b = np.asarray(imu.specific_force_body_mps2, dtype=float) - self.accel_bias_body_mps2
        omega_ib_b = np.asarray(imu.angular_rate_body_rps, dtype=float) - self.gyro_bias_body_rps
        c_nb = _quat_to_dcm(self.quaternion_body_to_enu)
        omega_ie_n = self.earth_rate_enu_rps
        omega_nb_b = omega_ib_b - c_nb.T @ omega_ie_n
        specific_force_n = c_nb @ f_b
        gravity_n = np.array([0.0, 0.0, -self.gravity_mps2], dtype=float)
        acceleration_n = (
            specific_force_n
            + gravity_n
            - 2.0 * np.cross(omega_ie_n, self.velocity_enu_mps)
        )

        self.position_enu_m = (
            self.position_enu_m
            + self.velocity_enu_mps * dt
            + 0.5 * acceleration_n * dt * dt
        )
        self.velocity_enu_mps = self.velocity_enu_mps + acceleration_n * dt
        dq = _quat_from_rotvec(omega_nb_b * dt)
        self.quaternion_body_to_enu = _quat_normalize(
            _quat_multiply(self.quaternion_body_to_enu, dq)
        )

        f = np.zeros((15, 15), dtype=float)
        f[0:3, 3:6] = np.eye(3)
        f[3:6, 3:6] = -2.0 * _skew(omega_ie_n)
        f[3:6, 6:9] = -_skew(specific_force_n)
        f[3:6, 9:12] = -c_nb
        f[6:9, 6:9] = -_skew(omega_ie_n)
        f[6:9, 12:15] = -c_nb

        g = np.zeros((15, 12), dtype=float)
        g[3:6, 0:3] = c_nb
        g[6:9, 3:6] = c_nb
        g[9:12, 6:9] = np.eye(3)
        g[12:15, 9:12] = np.eye(3)
        q_c = np.diag(
            [
                *([self.config.accel_noise_density_mps2_sqrt_hz**2] * 3),
                *([self.config.gyro_noise_density_rps_sqrt_hz**2] * 3),
                *([self.config.accel_bias_random_walk_mps2_sqrt_hz**2] * 3),
                *([self.config.gyro_bias_random_walk_rps_sqrt_hz**2] * 3),
            ]
        )
        phi = np.eye(15) + f * dt
        q_d = g @ q_c @ g.T * dt
        self.P = nearest_psd(
            phi @ self.P @ phi.T + q_d,
            self.config.covariance_eigen_floor,
        )
        return dt

    def _update_error_state(
        self,
        residual: np.ndarray,
        h: np.ndarray,
        r: np.ndarray,
        *,
        source: str,
        allow_fusion: bool,
    ) -> MeasurementResult:
        residual = np.asarray(residual, dtype=float).reshape(-1)
        h = np.asarray(h, dtype=float)
        r = np.asarray(r, dtype=float)
        dimension = residual.size
        if h.shape != (dimension, 15):
            raise ValueError(f"H must have shape {(dimension, 15)}, got {h.shape}")
        if r.shape != (dimension, dimension):
            raise ValueError(f"R must have shape {(dimension, dimension)}, got {r.shape}")
        require_finite("measurement residual", residual)
        require_finite("measurement covariance", r)
        if np.min(np.linalg.eigvalsh(symmetrize(r))) <= 0.0:
            raise ValueError("measurement covariance must be positive definite")

        s = nearest_psd(h @ self.P @ h.T + r, self.config.covariance_eigen_floor)
        factor = cho_factor(s, lower=True, check_finite=True)
        nis = float(residual.T @ cho_solve(factor, residual))
        threshold = float(chi2.ppf(self.config.gate_probability, df=dimension))
        accepted = nis <= threshold
        if not accepted:
            return MeasurementResult(
                source, False, False, nis, threshold, dimension, "innovation_rejected"
            )
        if not allow_fusion:
            return MeasurementResult(
                source, True, False, nis, threshold, dimension, "accepted_probe_only"
            )

        pht = self.P @ h.T
        gain = cho_solve(factor, pht.T).T
        dx = gain @ residual
        self.position_enu_m += dx[0:3]
        self.velocity_enu_mps += dx[3:6]
        dtheta = dx[6:9]
        self.quaternion_body_to_enu = _quat_normalize(
            _quat_multiply(_quat_from_rotvec(dtheta), self.quaternion_body_to_enu)
        )
        self.accel_bias_body_mps2 += dx[9:12]
        self.gyro_bias_body_rps += dx[12:15]

        identity = np.eye(15)
        kh = gain @ h
        self.P = (identity - kh) @ self.P @ (identity - kh).T + gain @ r @ gain.T
        reset = np.eye(15)
        reset[6:9, 6:9] = np.eye(3) - 0.5 * _skew(dtheta)
        self.P = nearest_psd(
            reset @ self.P @ reset.T,
            self.config.covariance_eigen_floor,
        )
        return MeasurementResult(
            source, True, True, nis, threshold, dimension, "accepted_and_fused"
        )

    def update_measurement(
        self,
        kind: str,
        values: np.ndarray,
        covariance: np.ndarray,
        *,
        frame: str,
        source: str,
        metadata: Mapping[str, object] | None = None,
        allow_fusion: bool = True,
    ) -> MeasurementResult:
        del metadata
        if frame not in self.accepted_frames:
            raise ValueError(f"StrapdownESKF requires local_ENU measurements, got {frame}")
        z = np.asarray(values, dtype=float).reshape(-1)
        r = np.asarray(covariance, dtype=float)
        h = np.zeros((z.size, 15), dtype=float)
        if kind == "position":
            if z.size not in (2, 3):
                raise ValueError("position measurement must have dimension 2 or 3")
            residual = z - self.position_enu_m[: z.size]
            h[:, : z.size] = np.eye(z.size)
        elif kind == "ground_velocity":
            if z.size not in (2, 3):
                raise ValueError("ground_velocity measurement must have dimension 2 or 3")
            residual = z - self.velocity_enu_mps[: z.size]
            h[:, 3 : 3 + z.size] = np.eye(z.size)
        elif kind == "heading":
            if z.size != 1:
                raise ValueError("heading measurement must have dimension 1")
            predicted = _yaw_from_dcm(_quat_to_dcm(self.quaternion_body_to_enu))
            residual = np.array([wrap_angle(float(z[0]) - predicted)], dtype=float)
            h[0, 8] = 1.0
        else:
            raise ValueError(f"unsupported StrapdownESKF measurement kind: {kind}")
        return self._update_error_state(
            residual,
            h,
            r,
            source=source,
            allow_fusion=allow_fusion,
        )

    def snapshot(self) -> EstimatorSnapshot:
        return EstimatorSnapshot(
            frame="local_ENU",
            east_m=float(self.position_enu_m[0]),
            north_m=float(self.position_enu_m[1]),
            ground_velocity_e_mps=float(self.velocity_enu_mps[0]),
            ground_velocity_n_mps=float(self.velocity_enu_mps[1]),
            heading_rad=_yaw_from_dcm(_quat_to_dcm(self.quaternion_body_to_enu)),
            covariance=self.P.copy(),
            state_schema_id="amep1.strapdown_eskf.local_enu.v1",
            covariance_labels=(
                "dE_m",
                "dN_m",
                "dU_m",
                "dV_E_mps",
                "dV_N_mps",
                "dV_U_mps",
                "dtheta_E_rad",
                "dtheta_N_rad",
                "dtheta_U_rad",
                "dba_x_mps2",
                "dba_y_mps2",
                "dba_z_mps2",
                "dbg_x_rps",
                "dbg_y_rps",
                "dbg_z_rps",
            ),
        )

    def containment_proxy(self) -> float:
        horizontal = symmetrize(self.P[:2, :2])
        largest = float(np.max(np.linalg.eigvalsh(horizontal)))
        threshold = float(chi2.ppf(self.config.containment_probability, df=2))
        return float(np.sqrt(max(0.0, threshold * largest)))
