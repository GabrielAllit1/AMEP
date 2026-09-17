from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite

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
    quat = np.asarray(q, dtype=float).reshape(4)
    norm = float(np.linalg.norm(quat))
    if not isfinite(norm) or norm <= 1e-15:
        raise ValueError("attitude quaternion must have finite non-zero norm")
    quat = quat / norm
    if quat[0] < 0.0:
        quat = -quat
    return quat


def _quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = np.asarray(a, dtype=float).reshape(4)
    bw, bx, by, bz = np.asarray(b, dtype=float).reshape(4)
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
    rv = np.asarray(rotvec, dtype=float).reshape(3)
    theta = float(np.linalg.norm(rv))
    if theta < 1e-12:
        return _quat_normalize(np.array([1.0, *(0.5 * rv)], dtype=float))
    half = 0.5 * theta
    axis = rv / theta
    return np.array([np.cos(half), *(np.sin(half) * axis)], dtype=float)


def _quat_to_matrix(q: np.ndarray) -> np.ndarray:
    w, x, y, z = _quat_normalize(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _heading_from_quat(q: np.ndarray) -> float:
    # q maps body FRD axes into local NED. Heading is clockwise from north.
    rotation = _quat_to_matrix(q)
    return wrap_angle(float(np.arctan2(rotation[1, 0], rotation[0, 0])))


@dataclass(frozen=True)
class RawIMUInput:
    """Raw strapdown IMU sample.

    Body frame is FRD: +x forward, +y starboard/right, +z down.
    specific_force_body_mps2 is accelerometer specific force, not gravity-
    compensated translational acceleration. angular_rate_body_rps is the body
    angular-rate vector. Source-side calibration must put both vectors in the
    declared body frame before this backend receives them.
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
        require_finite("raw IMU input", values)


@dataclass(frozen=True)
class StrapdownINSConfig:
    """Local-level strapdown ESKF configuration.

    The mechanization uses a local NED tangent frame with constant normal
    gravity and does not model Earth rotation, transport rate, geodetic-height
    curvature, coning/sculling compensation, or sensor scale/misalignment
    states. Those remain platform-validation work; this backend exists to keep
    raw specific force and bias-aware inertial propagation out of the published
    seven-state AMEP filter.
    """

    gravity_mps2: float = 9.80665
    gate_probability: float = 0.997
    containment_probability: float = 0.95
    min_dt_s: float = 1e-6
    max_dt_s: float = 0.05
    covariance_eigen_floor: float = 1e-12
    accel_noise_density_mps2_sqrt_hz: float = 0.05
    gyro_noise_density_rps_sqrt_hz: float = np.deg2rad(0.05)
    accel_bias_rw_mps2_sqrt_hz: float = 5e-4
    gyro_bias_rw_rps_sqrt_hz: float = np.deg2rad(0.005)

    def __post_init__(self) -> None:
        if self.gravity_mps2 <= 0:
            raise ValueError("gravity_mps2 must be > 0")
        if not 0.5 < self.gate_probability < 1.0:
            raise ValueError("gate_probability must be in (0.5, 1.0)")
        if not 0.5 < self.containment_probability < 1.0:
            raise ValueError("containment_probability must be in (0.5, 1.0)")
        if self.min_dt_s <= 0 or self.max_dt_s <= self.min_dt_s:
            raise ValueError("invalid strapdown dt bounds")
        if self.covariance_eigen_floor <= 0:
            raise ValueError("covariance_eigen_floor must be > 0")
        noises = (
            self.accel_noise_density_mps2_sqrt_hz,
            self.gyro_noise_density_rps_sqrt_hz,
            self.accel_bias_rw_mps2_sqrt_hz,
            self.gyro_bias_rw_rps_sqrt_hz,
        )
        if any(value < 0 for value in noises):
            raise ValueError("noise-density terms must be >= 0")


@dataclass
class StrapdownINSBackend:
    """Bias-aware local-level 15-error-state strapdown INS/ESKF backend.

    Nominal state:
      p_ned[3], v_ned[3], q_nb[4], accel_bias_body[3], gyro_bias_body[3]

    Error-state covariance ordering:
      dp_N, dp_E, dp_D,
      dv_N, dv_E, dv_D,
      dtheta_x, dtheta_y, dtheta_z,
      dba_x, dba_y, dba_z,
      dbg_x, dbg_y, dbg_z

    The implementation is a production-oriented software seam, not validated
    production navigation evidence. Platform calibration, Earth-model fidelity,
    real-data tuning, HIL, and water-trial validation remain mandatory.
    """

    config: StrapdownINSConfig = field(default_factory=StrapdownINSConfig)
    position_ned_m: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    velocity_ned_mps: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    attitude_q_nb: np.ndarray = field(
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
        self.position_ned_m = np.asarray(self.position_ned_m, dtype=float).reshape(3)
        self.velocity_ned_mps = np.asarray(self.velocity_ned_mps, dtype=float).reshape(3)
        self.attitude_q_nb = _quat_normalize(self.attitude_q_nb)
        self.accel_bias_body_mps2 = np.asarray(
            self.accel_bias_body_mps2, dtype=float
        ).reshape(3)
        self.gyro_bias_body_rps = np.asarray(self.gyro_bias_body_rps, dtype=float).reshape(3)
        self.P = np.asarray(self.P, dtype=float).reshape(15, 15)
        for name, value in (
            ("position", self.position_ned_m),
            ("velocity", self.velocity_ned_mps),
            ("accelerometer bias", self.accel_bias_body_mps2),
            ("gyro bias", self.gyro_bias_body_rps),
            ("P", self.P),
        ):
            require_finite(name, value)
        self.P = nearest_psd(self.P, self.config.covariance_eigen_floor)

    def predict(self, prediction_input: object) -> float:
        if not isinstance(prediction_input, RawIMUInput):
            raise TypeError("StrapdownINSBackend expects RawIMUInput")
        imu = prediction_input
        imu.validate()

        if self.last_t is None:
            self.last_t = float(imu.timestamp_s)
            return 0.0

        dt = float(imu.timestamp_s - self.last_t)
        if dt < self.config.min_dt_s:
            raise ValueError(f"non-monotonic or too-small strapdown dt: {dt:.9f}s")
        if dt > self.config.max_dt_s:
            raise ValueError(
                f"strapdown prediction gap {dt:.6f}s exceeds "
                f"max_dt_s={self.config.max_dt_s:.6f}s"
            )
        self.last_t = float(imu.timestamp_s)

        specific_force_body = (
            np.asarray(imu.specific_force_body_mps2, dtype=float)
            - self.accel_bias_body_mps2
        )
        angular_rate_body = (
            np.asarray(imu.angular_rate_body_rps, dtype=float)
            - self.gyro_bias_body_rps
        )

        rotation_nb = _quat_to_matrix(self.attitude_q_nb)
        gravity_ned = np.array([0.0, 0.0, self.config.gravity_mps2], dtype=float)
        acceleration_ned = rotation_nb @ specific_force_body + gravity_ned

        self.position_ned_m = (
            self.position_ned_m
            + self.velocity_ned_mps * dt
            + 0.5 * acceleration_ned * dt * dt
        )
        self.velocity_ned_mps = self.velocity_ned_mps + acceleration_ned * dt
        self.attitude_q_nb = _quat_normalize(
            _quat_multiply(
                self.attitude_q_nb,
                _quat_from_rotvec(angular_rate_body * dt),
            )
        )

        continuous_f = np.zeros((15, 15), dtype=float)
        continuous_f[0:3, 3:6] = np.eye(3)
        continuous_f[3:6, 6:9] = -rotation_nb @ _skew(specific_force_body)
        continuous_f[3:6, 9:12] = -rotation_nb
        continuous_f[6:9, 6:9] = -_skew(angular_rate_body)
        continuous_f[6:9, 12:15] = -np.eye(3)

        noise_map = np.zeros((15, 12), dtype=float)
        noise_map[3:6, 0:3] = rotation_nb
        noise_map[6:9, 3:6] = np.eye(3)
        noise_map[9:12, 6:9] = np.eye(3)
        noise_map[12:15, 9:12] = np.eye(3)
        q_density = np.diag(
            [
                *([self.config.accel_noise_density_mps2_sqrt_hz**2] * 3),
                *([self.config.gyro_noise_density_rps_sqrt_hz**2] * 3),
                *([self.config.accel_bias_rw_mps2_sqrt_hz**2] * 3),
                *([self.config.gyro_bias_rw_rps_sqrt_hz**2] * 3),
            ]
        )
        transition = np.eye(15, dtype=float) + continuous_f * dt
        process_covariance = noise_map @ q_density @ noise_map.T * dt
        self.P = nearest_psd(
            transition @ self.P @ transition.T + process_covariance,
            self.config.covariance_eigen_floor,
        )
        return dt

    def _inject_error(self, correction: np.ndarray) -> None:
        delta = np.asarray(correction, dtype=float).reshape(15)
        self.position_ned_m = self.position_ned_m + delta[0:3]
        self.velocity_ned_mps = self.velocity_ned_mps + delta[3:6]
        self.attitude_q_nb = _quat_normalize(
            _quat_multiply(self.attitude_q_nb, _quat_from_rotvec(delta[6:9]))
        )
        self.accel_bias_body_mps2 = self.accel_bias_body_mps2 + delta[9:12]
        self.gyro_bias_body_rps = self.gyro_bias_body_rps + delta[12:15]

    def _measurement_update(
        self,
        *,
        source: str,
        z: np.ndarray,
        prediction: np.ndarray,
        H: np.ndarray,
        R: np.ndarray,
        angle_rows: tuple[int, ...] = (),
        allow_fusion: bool,
    ) -> MeasurementResult:
        z = np.asarray(z, dtype=float).reshape(-1)
        prediction = np.asarray(prediction, dtype=float).reshape(-1)
        H = np.asarray(H, dtype=float)
        R = np.asarray(R, dtype=float)
        dimension = z.size
        if prediction.shape != (dimension,):
            raise ValueError("measurement prediction dimension mismatch")
        if H.shape != (dimension, 15):
            raise ValueError(f"H must have shape {(dimension, 15)}")
        if R.shape != (dimension, dimension):
            raise ValueError(f"R must have shape {(dimension, dimension)}")
        require_finite("measurement", z)
        require_finite("measurement prediction", prediction)
        require_finite("measurement H", H)
        require_finite("measurement R", R)
        if np.min(np.linalg.eigvalsh(symmetrize(R))) <= 0:
            raise ValueError("measurement covariance must be positive definite")

        residual = z - prediction
        for row in angle_rows:
            residual[row] = wrap_angle(residual[row])

        innovation_covariance = nearest_psd(
            H @ self.P @ H.T + R,
            self.config.covariance_eigen_floor,
        )
        factor = cho_factor(innovation_covariance, lower=True, check_finite=True)
        solved = cho_solve(factor, residual)
        nis = float(residual.T @ solved)
        threshold = float(chi2.ppf(self.config.gate_probability, df=dimension))
        if nis > threshold:
            return MeasurementResult(
                source,
                False,
                False,
                nis,
                threshold,
                dimension,
                "innovation_rejected",
            )
        if not allow_fusion:
            return MeasurementResult(
                source,
                True,
                False,
                nis,
                threshold,
                dimension,
                "accepted_probe_only",
            )

        PHt = self.P @ H.T
        gain = cho_solve(factor, PHt.T).T
        correction = gain @ residual
        self._inject_error(correction)

        identity = np.eye(15, dtype=float)
        KH = gain @ H
        self.P = nearest_psd(
            (identity - KH) @ self.P @ (identity - KH).T + gain @ R @ gain.T,
            self.config.covariance_eigen_floor,
        )
        return MeasurementResult(
            source,
            True,
            True,
            nis,
            threshold,
            dimension,
            "accepted_and_fused",
        )

    def _position_model(self, dimension: int) -> tuple[np.ndarray, np.ndarray]:
        if dimension not in (2, 3):
            raise ValueError("position measurement must be 2-D [E,N] or 3-D [E,N,U]")
        prediction = np.array(
            [
                self.position_ned_m[1],
                self.position_ned_m[0],
                -self.position_ned_m[2],
            ],
            dtype=float,
        )[:dimension]
        H = np.zeros((dimension, 15), dtype=float)
        H[0, 1] = 1.0
        H[1, 0] = 1.0
        if dimension == 3:
            H[2, 2] = -1.0
        return prediction, H

    def _velocity_model(self, dimension: int) -> tuple[np.ndarray, np.ndarray]:
        if dimension not in (2, 3):
            raise ValueError(
                "ground_velocity measurement must be 2-D [E,N] or 3-D [E,N,U]"
            )
        prediction = np.array(
            [
                self.velocity_ned_mps[1],
                self.velocity_ned_mps[0],
                -self.velocity_ned_mps[2],
            ],
            dtype=float,
        )[:dimension]
        H = np.zeros((dimension, 15), dtype=float)
        H[0, 4] = 1.0
        H[1, 3] = 1.0
        if dimension == 3:
            H[2, 5] = -1.0
        return prediction, H

    def _heading_model(self) -> tuple[np.ndarray, np.ndarray]:
        prediction = np.array([_heading_from_quat(self.attitude_q_nb)], dtype=float)
        H = np.zeros((1, 15), dtype=float)
        epsilon = 1e-7
        base_heading = prediction[0]
        for axis in range(3):
            perturbation = np.zeros(3, dtype=float)
            perturbation[axis] = epsilon
            perturbed_q = _quat_normalize(
                _quat_multiply(self.attitude_q_nb, _quat_from_rotvec(perturbation))
            )
            H[0, 6 + axis] = wrap_angle(
                _heading_from_quat(perturbed_q) - base_heading
            ) / epsilon
        return prediction, H

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
        if kind not in self.measurement_kinds:
            raise ValueError(f"unsupported StrapdownINSBackend measurement kind: {kind}")
        if frame not in self.accepted_frames:
            raise ValueError(f"StrapdownINSBackend requires local_ENU measurements, got {frame}")

        z = np.asarray(values, dtype=float).reshape(-1)
        R = np.asarray(covariance, dtype=float)
        if kind == "position":
            prediction, H = self._position_model(z.size)
            angle_rows: tuple[int, ...] = ()
        elif kind == "ground_velocity":
            prediction, H = self._velocity_model(z.size)
            angle_rows = ()
        else:
            if z.size != 1:
                raise ValueError("heading measurement must be scalar")
            prediction, H = self._heading_model()
            angle_rows = (0,)

        return self._measurement_update(
            source=source,
            z=z,
            prediction=prediction,
            H=H,
            R=R,
            angle_rows=angle_rows,
            allow_fusion=allow_fusion,
        )

    def snapshot(self) -> EstimatorSnapshot:
        return EstimatorSnapshot(
            frame="local_NED",
            east_m=float(self.position_ned_m[1]),
            north_m=float(self.position_ned_m[0]),
            ground_velocity_e_mps=float(self.velocity_ned_mps[1]),
            ground_velocity_n_mps=float(self.velocity_ned_mps[0]),
            heading_rad=_heading_from_quat(self.attitude_q_nb),
            covariance=self.P.copy(),
            state_schema_id="amep1.strapdown_eskf.local_ned.v1",
            covariance_labels=(
                "dN_m",
                "dE_m",
                "dD_m",
                "dvN_mps",
                "dvE_mps",
                "dvD_mps",
                "dtheta_x_rad",
                "dtheta_y_rad",
                "dtheta_z_rad",
                "dba_x_mps2",
                "dba_y_mps2",
                "dba_z_mps2",
                "dbg_x_rps",
                "dbg_y_rps",
                "dbg_z_rps",
            ),
        )

    def containment_proxy(self) -> float:
        position_en = self.P[np.ix_([1, 0], [1, 0])]
        largest_eigenvalue = float(np.max(np.linalg.eigvalsh(position_en)))
        quantile = float(chi2.ppf(self.config.containment_probability, df=2))
        return float(np.sqrt(max(0.0, quantile * largest_eigenvalue)))
