from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, sin

import numpy as np


def _skew(v: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(v, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def _rpy_to_dcm(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    return rz @ ry @ rx


@dataclass(frozen=True)
class SensorInstallation:
    """Measured installation contract for one sensor relative to vessel body.

    ``calibration_covariance`` is ordered as [lever_x, lever_y, lever_z,
    boresight_roll, boresight_pitch, boresight_yaw]. The object records measured
    values and their uncertainty; it does not manufacture or validate those
    values. Operational use still requires a platform-specific survey/calibration
    procedure and evidence.
    """

    sensor_name: str
    sensor_frame: str
    body_frame: str
    lever_arm_body_m: tuple[float, float, float]
    boresight_sensor_to_body_rpy_rad: tuple[float, float, float]
    calibration_covariance: tuple[
        tuple[float, float, float, float, float, float],
        tuple[float, float, float, float, float, float],
        tuple[float, float, float, float, float, float],
        tuple[float, float, float, float, float, float],
        tuple[float, float, float, float, float, float],
        tuple[float, float, float, float, float, float],
    ]
    calibration_id: str
    provenance: str
    measured: bool
    clock_domain: str = "navigation"
    nominal_latency_s: float = 0.0
    latency_uncertainty_s: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            self.sensor_name,
            self.sensor_frame,
            self.body_frame,
            self.calibration_id,
            self.provenance,
            self.clock_domain,
        ):
            if not name.strip():
                raise ValueError("installation identity fields must be non-empty")
        lever = np.asarray(self.lever_arm_body_m, dtype=float)
        boresight = np.asarray(self.boresight_sensor_to_body_rpy_rad, dtype=float)
        covariance = np.asarray(self.calibration_covariance, dtype=float)
        if lever.shape != (3,) or boresight.shape != (3,):
            raise ValueError("lever arm and boresight must each contain three values")
        if covariance.shape != (6, 6):
            raise ValueError("calibration_covariance must have shape (6,6)")
        if not all(
            np.all(np.isfinite(value)) for value in (lever, boresight, covariance)
        ):
            raise ValueError("installation calibration contains non-finite values")
        if not np.allclose(covariance, covariance.T, rtol=1e-10, atol=1e-12):
            raise ValueError("calibration_covariance must be symmetric")
        if np.min(np.linalg.eigvalsh(covariance)) < -1e-15:
            raise ValueError("calibration_covariance must be positive semidefinite")
        latency = float(self.nominal_latency_s)
        latency_uncertainty = float(self.latency_uncertainty_s)
        if not isfinite(latency) or latency < 0.0:
            raise ValueError("nominal_latency_s must be finite and >= 0")
        if not isfinite(latency_uncertainty) or latency_uncertainty < 0.0:
            raise ValueError("latency_uncertainty_s must be finite and >= 0")

    @property
    def sensor_to_body_dcm(self) -> np.ndarray:
        return _rpy_to_dcm(*self.boresight_sensor_to_body_rpy_rad)

    @property
    def covariance_array(self) -> np.ndarray:
        return np.asarray(self.calibration_covariance, dtype=float)

    def transform_vector_sensor_to_body(
        self, vector_sensor: tuple[float, float, float] | np.ndarray
    ) -> np.ndarray:
        vector = np.asarray(vector_sensor, dtype=float).reshape(3)
        if not np.all(np.isfinite(vector)):
            raise ValueError("sensor vector contains non-finite values")
        return self.sensor_to_body_dcm @ vector

    def velocity_at_body_origin(
        self,
        velocity_sensor_frame_mps: tuple[float, float, float] | np.ndarray,
        angular_rate_body_rps: tuple[float, float, float] | np.ndarray,
    ) -> np.ndarray:
        """Move a sensor-frame velocity observation to the body origin.

        Rigid-body relation: v_sensor = v_origin + omega x lever_arm.
        """
        velocity_body = self.transform_vector_sensor_to_body(velocity_sensor_frame_mps)
        omega = np.asarray(angular_rate_body_rps, dtype=float).reshape(3)
        if not np.all(np.isfinite(omega)):
            raise ValueError("angular rate contains non-finite values")
        lever = np.asarray(self.lever_arm_body_m, dtype=float)
        return velocity_body - np.cross(omega, lever)

    def velocity_at_body_origin_with_covariance(
        self,
        velocity_sensor_frame_mps: tuple[float, float, float] | np.ndarray,
        measurement_covariance_sensor: np.ndarray,
        angular_rate_body_rps: tuple[float, float, float] | np.ndarray,
        *,
        angular_rate_covariance_body: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply boresight/lever-arm correction and first-order uncertainty propagation."""
        velocity_sensor = np.asarray(velocity_sensor_frame_mps, dtype=float).reshape(3)
        measurement_covariance = np.asarray(measurement_covariance_sensor, dtype=float)
        omega = np.asarray(angular_rate_body_rps, dtype=float).reshape(3)
        if measurement_covariance.shape != (3, 3):
            raise ValueError("measurement_covariance_sensor must have shape (3,3)")
        if not np.allclose(
            measurement_covariance, measurement_covariance.T, rtol=1e-10, atol=1e-12
        ):
            raise ValueError("measurement covariance must be symmetric")
        if np.min(np.linalg.eigvalsh(measurement_covariance)) < 0.0:
            raise ValueError("measurement covariance must be positive semidefinite")

        c_bs = self.sensor_to_body_dcm
        velocity_body = c_bs @ velocity_sensor
        lever = np.asarray(self.lever_arm_body_m, dtype=float)
        corrected = velocity_body - np.cross(omega, lever)

        covariance = c_bs @ measurement_covariance @ c_bs.T
        calibration_covariance = self.covariance_array
        jacobian_cal = np.zeros((3, 6), dtype=float)
        jacobian_cal[:, 0:3] = -_skew(omega)
        jacobian_cal[:, 3:6] = -_skew(velocity_body)
        covariance += jacobian_cal @ calibration_covariance @ jacobian_cal.T

        if angular_rate_covariance_body is not None:
            omega_covariance = np.asarray(angular_rate_covariance_body, dtype=float)
            if omega_covariance.shape != (3, 3):
                raise ValueError("angular_rate_covariance_body must have shape (3,3)")
            if not np.allclose(
                omega_covariance, omega_covariance.T, rtol=1e-10, atol=1e-12
            ):
                raise ValueError("angular-rate covariance must be symmetric")
            if np.min(np.linalg.eigvalsh(omega_covariance)) < 0.0:
                raise ValueError("angular-rate covariance must be positive semidefinite")
            jacobian_omega = _skew(lever)
            covariance += jacobian_omega @ omega_covariance @ jacobian_omega.T

        return corrected, 0.5 * (covariance + covariance.T)
