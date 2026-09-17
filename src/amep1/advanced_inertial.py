from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import cos, pi, radians, sin, sqrt, tan

import numpy as np

from .inertial import (
    StrapdownESKF,
    StrapdownIMUInput,
    _gravity_magnitude,
    _quat_from_rotvec,
    _quat_multiply,
    _quat_normalize,
    _quat_to_dcm,
    _skew,
)
from .math_utils import nearest_psd, require_finite, wrap_angle
from .types import MeasurementResult

_WGS84_A_M = 6378137.0
_WGS84_E2 = 6.6943799901413165e-3


def _wgs84_curvature_radii(latitude_rad: float) -> tuple[float, float]:
    """Return meridian and prime-vertical radii (R_M, R_N) in metres."""
    s = sin(float(latitude_rad))
    denominator = 1.0 - _WGS84_E2 * s * s
    root = sqrt(denominator)
    r_n = _WGS84_A_M / root
    r_m = _WGS84_A_M * (1.0 - _WGS84_E2) / (denominator * root)
    return float(r_m), float(r_n)


def compensate_coning_sculling(
    delta_theta_body: np.ndarray,
    delta_velocity_body: np.ndarray,
    *,
    previous_delta_theta_body: np.ndarray | None = None,
    previous_delta_velocity_body: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a standard previous/current incremental coning-sculling correction.

    Inputs are raw body-frame angular and specific-force velocity increments for
    the current integration interval. When the previous increments are available,
    the 1/12 cross-coupling terms are included. The 1/2 within-interval rotational
    correction is always applied to the velocity increment.

    This is an executable SIL mechanization primitive. Its coefficients still
    require validation against the sampling architecture and IMU data sheet of a
    real installation before operational use.
    """

    dtheta = np.asarray(delta_theta_body, dtype=float).reshape(3)
    dvel = np.asarray(delta_velocity_body, dtype=float).reshape(3)
    require_finite("delta_theta_body", dtheta)
    require_finite("delta_velocity_body", dvel)

    corrected_theta = dtheta.copy()
    corrected_velocity = dvel + 0.5 * np.cross(dtheta, dvel)

    if (previous_delta_theta_body is None) != (previous_delta_velocity_body is None):
        raise ValueError("previous coning/sculling increments must be supplied together")
    if previous_delta_theta_body is not None and previous_delta_velocity_body is not None:
        previous_theta = np.asarray(previous_delta_theta_body, dtype=float).reshape(3)
        previous_velocity = np.asarray(previous_delta_velocity_body, dtype=float).reshape(3)
        require_finite("previous_delta_theta_body", previous_theta)
        require_finite("previous_delta_velocity_body", previous_velocity)
        corrected_theta += np.cross(previous_theta, dtheta) / 12.0
        corrected_velocity += (
            np.cross(previous_theta, dvel) + np.cross(previous_velocity, dtheta)
        ) / 12.0

    return corrected_theta, corrected_velocity


@dataclass
class CompensatedStrapdownESKF(StrapdownESKF):
    """Higher-fidelity local-level strapdown ESKF for AMEP SIL campaigns.

    Relative to :class:`StrapdownESKF`, this backend adds:

    - previous/current incremental coning and sculling compensation;
    - WGS-84 meridian/prime-vertical curvature radii;
    - local transport rate in the ENU navigation frame;
    - Earth + transport-rate attitude mechanization;
    - Coriolis + transport-rate velocity mechanization;
    - first-order transport-rate velocity coupling in the covariance dynamics;
    - local normal-gravity latitude/height gradients;
    - lever-arm-aware position and velocity measurement Jacobians.

    The state is still the same 15-error-state ESKF. This implementation closes
    an architecture/SIL gap; it is not evidence that a particular IMU sampling,
    calibration, vessel flexure, timing, or installation model is correct.
    """

    _previous_delta_theta_body: np.ndarray | None = field(
        default=None, init=False, repr=False
    )
    _previous_delta_velocity_body: np.ndarray | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._previous_delta_theta_body = None
        self._previous_delta_velocity_body = None

    @property
    def current_altitude_m(self) -> float:
        return float(self.config.altitude_m + self.position_enu_m[2])

    @property
    def current_latitude_rad(self) -> float:
        reference_latitude = radians(self.config.latitude_deg)
        reference_r_m, _ = _wgs84_curvature_radii(reference_latitude)
        denominator = max(1.0, reference_r_m + self.config.altitude_m)
        latitude = reference_latitude + float(self.position_enu_m[1]) / denominator
        return float(np.clip(latitude, -0.5 * pi + 1e-8, 0.5 * pi - 1e-8))

    @property
    def curvature_radii_m(self) -> tuple[float, float]:
        return _wgs84_curvature_radii(self.current_latitude_rad)

    @property
    def gravity_mps2(self) -> float:
        return _gravity_magnitude(self.current_latitude_rad, self.current_altitude_m)

    @property
    def earth_rate_enu_rps(self) -> np.ndarray:
        latitude = self.current_latitude_rad
        rate = self.config.earth_rate_rad_s
        return np.array(
            [0.0, rate * cos(latitude), rate * sin(latitude)], dtype=float
        )

    def transport_rate_velocity_jacobian(self) -> np.ndarray:
        """Return d(omega_en^n)/d(v^n) for ENU local-level mechanization."""
        latitude = self.current_latitude_rad
        altitude = self.current_altitude_m
        r_m, r_n = self.curvature_radii_m
        north_denominator = max(1.0, r_m + altitude)
        east_denominator = max(1.0, r_n + altitude)
        return np.array(
            [
                [0.0, -1.0 / north_denominator, 0.0],
                [1.0 / east_denominator, 0.0, 0.0],
                [tan(latitude) / east_denominator, 0.0, 0.0],
            ],
            dtype=float,
        )

    def transport_rate_enu_rps(
        self, velocity_enu_mps: np.ndarray | None = None
    ) -> np.ndarray:
        velocity = (
            self.velocity_enu_mps
            if velocity_enu_mps is None
            else np.asarray(velocity_enu_mps, dtype=float).reshape(3)
        )
        require_finite("transport-rate velocity", velocity)
        return self.transport_rate_velocity_jacobian() @ velocity

    def navigation_rate_enu_rps(
        self, velocity_enu_mps: np.ndarray | None = None
    ) -> np.ndarray:
        return self.earth_rate_enu_rps + self.transport_rate_enu_rps(velocity_enu_mps)

    def _gravity_position_jacobian(self) -> np.ndarray:
        latitude = self.current_latitude_rad
        altitude = self.current_altitude_m
        r_m, _ = self.curvature_radii_m
        epsilon = 1e-6
        g_plus = _gravity_magnitude(latitude + epsilon, altitude)
        g_minus = _gravity_magnitude(latitude - epsilon, altitude)
        dg_dlatitude = (g_plus - g_minus) / (2.0 * epsilon)
        jacobian = np.zeros((3, 3), dtype=float)
        jacobian[2, 1] = -dg_dlatitude / max(1.0, r_m + altitude)
        jacobian[2, 2] = 3.086e-6
        return jacobian

    def predict(self, prediction_input: object) -> float:
        if not isinstance(prediction_input, StrapdownIMUInput):
            raise TypeError(
                "CompensatedStrapdownESKF expects StrapdownIMUInput prediction data"
            )
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

        f_b = (
            np.asarray(imu.specific_force_body_mps2, dtype=float)
            - self.accel_bias_body_mps2
        )
        omega_ib_b = (
            np.asarray(imu.angular_rate_body_rps, dtype=float) - self.gyro_bias_body_rps
        )
        raw_delta_theta = omega_ib_b * dt
        raw_delta_velocity = f_b * dt
        delta_theta_ib_b, delta_velocity_b = compensate_coning_sculling(
            raw_delta_theta,
            raw_delta_velocity,
            previous_delta_theta_body=self._previous_delta_theta_body,
            previous_delta_velocity_body=self._previous_delta_velocity_body,
        )

        c_nb = _quat_to_dcm(self.quaternion_body_to_enu)
        velocity_before = self.velocity_enu_mps.copy()
        omega_ie_n = self.earth_rate_enu_rps
        omega_en_n = self.transport_rate_enu_rps(velocity_before)
        omega_in_n = omega_ie_n + omega_en_n

        # Compensate the body increment for rotation of the local navigation frame.
        delta_theta_nb_b = delta_theta_ib_b - c_nb.T @ omega_in_n * dt

        # Rotate the sculling-corrected specific-force increment through the
        # midpoint navigation frame to avoid treating C_b^n as constant.
        nav_midpoint = np.eye(3) - 0.5 * _skew(omega_in_n * dt)
        delta_velocity_specific_n = nav_midpoint @ c_nb @ delta_velocity_b

        gravity_n = np.array([0.0, 0.0, -self.gravity_mps2], dtype=float)
        coriolis_transport_n = -np.cross(
            2.0 * omega_ie_n + omega_en_n, velocity_before
        )
        delta_velocity_n = delta_velocity_specific_n + (
            gravity_n + coriolis_transport_n
        ) * dt
        velocity_after = velocity_before + delta_velocity_n
        self.position_enu_m = self.position_enu_m + 0.5 * (
            velocity_before + velocity_after
        ) * dt
        self.velocity_enu_mps = velocity_after
        self.quaternion_body_to_enu = _quat_normalize(
            _quat_multiply(
                self.quaternion_body_to_enu,
                _quat_from_rotvec(delta_theta_nb_b),
            )
        )

        specific_force_n = delta_velocity_specific_n / dt
        transport_jacobian = self.transport_rate_velocity_jacobian()
        omega_coriolis_n = 2.0 * omega_ie_n + omega_en_n

        f = np.zeros((15, 15), dtype=float)
        f[0:3, 3:6] = np.eye(3)
        f[3:6, 0:3] = self._gravity_position_jacobian()
        f[3:6, 3:6] = -_skew(omega_coriolis_n) + _skew(
            velocity_before
        ) @ transport_jacobian
        f[3:6, 6:9] = -_skew(specific_force_n)
        f[3:6, 9:12] = -c_nb
        f[6:9, 3:6] = -transport_jacobian
        f[6:9, 6:9] = -_skew(omega_in_n)
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
        f_dt = f * dt
        phi = np.eye(15) + f_dt + 0.5 * (f_dt @ f_dt)
        q_d = g @ q_c @ g.T * dt
        self.P = nearest_psd(
            phi @ self.P @ phi.T + q_d,
            self.config.covariance_eigen_floor,
        )

        self._previous_delta_theta_body = raw_delta_theta.copy()
        self._previous_delta_velocity_body = raw_delta_velocity.copy()
        return dt

    @staticmethod
    def _lever_arm_from_metadata(metadata: Mapping[str, object] | None) -> np.ndarray:
        if metadata is None or "lever_arm_body_m" not in metadata:
            return np.zeros(3, dtype=float)
        lever = np.asarray(metadata["lever_arm_body_m"], dtype=float).reshape(3)
        require_finite("lever_arm_body_m", lever)
        return lever

    def position_measurement_model(
        self,
        *,
        dimension: int,
        lever_arm_body_m: np.ndarray | tuple[float, float, float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if dimension not in (2, 3):
            raise ValueError("position measurement must have dimension 2 or 3")
        lever = (
            np.zeros(3, dtype=float)
            if lever_arm_body_m is None
            else np.asarray(lever_arm_body_m, dtype=float).reshape(3)
        )
        require_finite("lever_arm_body_m", lever)
        c_nb = _quat_to_dcm(self.quaternion_body_to_enu)
        lever_n = c_nb @ lever
        predicted = self.position_enu_m + lever_n
        h_full = np.zeros((3, 15), dtype=float)
        h_full[:, 0:3] = np.eye(3)
        h_full[:, 6:9] = -_skew(lever_n)
        return predicted[:dimension], h_full[:dimension, :]

    def ground_velocity_measurement_model(
        self,
        *,
        dimension: int,
        lever_arm_body_m: np.ndarray | tuple[float, float, float] | None = None,
        angular_rate_body_rps: np.ndarray | tuple[float, float, float] | None = None,
        angular_rate_is_raw_imu: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        if dimension not in (2, 3):
            raise ValueError("ground_velocity measurement must have dimension 2 or 3")
        lever = (
            np.zeros(3, dtype=float)
            if lever_arm_body_m is None
            else np.asarray(lever_arm_body_m, dtype=float).reshape(3)
        )
        require_finite("lever_arm_body_m", lever)
        if np.linalg.norm(lever) > 0.0 and angular_rate_body_rps is None:
            raise ValueError(
                "angular_rate_body_rps is required for a non-zero velocity lever arm"
            )
        omega = (
            np.zeros(3, dtype=float)
            if angular_rate_body_rps is None
            else np.asarray(angular_rate_body_rps, dtype=float).reshape(3)
        )
        require_finite("angular_rate_body_rps", omega)

        c_nb = _quat_to_dcm(self.quaternion_body_to_enu)
        if angular_rate_is_raw_imu:
            omega = (
                omega
                - self.gyro_bias_body_rps
                - c_nb.T @ self.navigation_rate_enu_rps(self.velocity_enu_mps)
            )
        rotational_velocity_n = c_nb @ np.cross(omega, lever)
        predicted = self.velocity_enu_mps + rotational_velocity_n

        h_full = np.zeros((3, 15), dtype=float)
        h_full[:, 3:6] = np.eye(3)
        h_full[:, 6:9] = -_skew(rotational_velocity_n)
        if angular_rate_is_raw_imu:
            h_full[:, 12:15] = c_nb @ _skew(lever)
        return predicted[:dimension], h_full[:dimension, :]

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
        if frame not in self.accepted_frames:
            raise ValueError(
                f"CompensatedStrapdownESKF requires local_ENU measurements, got {frame}"
            )
        if kind == "heading":
            return super().update_measurement(
                kind,
                values,
                covariance,
                frame=frame,
                source=source,
                metadata=metadata,
                allow_fusion=allow_fusion,
            )

        z = np.asarray(values, dtype=float).reshape(-1)
        r = np.asarray(covariance, dtype=float)
        lever = self._lever_arm_from_metadata(metadata)
        if kind == "position":
            predicted, h = self.position_measurement_model(
                dimension=z.size,
                lever_arm_body_m=lever,
            )
        elif kind == "ground_velocity":
            angular_rate: object | None = (
                None if metadata is None else metadata.get("angular_rate_body_rps")
            )
            raw_imu = bool(
                False
                if metadata is None
                else metadata.get("angular_rate_is_raw_imu", False)
            )
            predicted, h = self.ground_velocity_measurement_model(
                dimension=z.size,
                lever_arm_body_m=lever,
                angular_rate_body_rps=angular_rate,  # type: ignore[arg-type]
                angular_rate_is_raw_imu=raw_imu,
            )
        else:
            raise ValueError(
                f"unsupported CompensatedStrapdownESKF measurement kind: {kind}"
            )
        residual = z - predicted
        return self._update_error_state(
            residual,
            h,
            r,
            source=source,
            allow_fusion=allow_fusion,
        )

    def snapshot(self):  # type: ignore[no-untyped-def]
        snapshot = super().snapshot()
        return replace(
            snapshot,
            state_schema_id="amep1.strapdown_eskf.compensated_local_enu.v1",
        )
