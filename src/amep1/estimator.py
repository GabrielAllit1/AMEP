from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.stats import chi2

from .config import EstimatorConfig
from .math_utils import nearest_psd, require_finite, symmetrize, wrap_angle
from .types import HorizontalIMUInput, MeasurementResult


class TimebaseError(RuntimeError):
    pass


@dataclass
class AMEPFilter:
    """Hardened implementation of the published AMEP-1 v1.0 7-state model.

    State: [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T

    This remains a horizontal research estimator; it is not a full strap-down INS.
    """

    config: EstimatorConfig = field(default_factory=EstimatorConfig)
    x: np.ndarray = field(default_factory=lambda: np.zeros(7, dtype=float))
    P: np.ndarray = field(default_factory=lambda: np.eye(7, dtype=float) * 10.0)
    last_t: float | None = None

    def __post_init__(self) -> None:
        self.x = np.asarray(self.x, dtype=float).reshape(7)
        self.P = np.asarray(self.P, dtype=float).reshape(7, 7)
        require_finite("x", self.x)
        require_finite("P", self.P)
        self.P = nearest_psd(self.P, self.config.covariance_eigen_floor)
        self.x[6] = wrap_angle(self.x[6])

    def predict(self, imu: HorizontalIMUInput) -> float:
        imu.validate()
        require_finite(
            "imu",
            np.array(
                [imu.timestamp_s, imu.a_fwd_mps2, imu.a_stbd_mps2, imu.yaw_rate_rps]
            ),
        )

        if self.last_t is None:
            self.last_t = float(imu.timestamp_s)
            return 0.0

        dt = float(imu.timestamp_s - self.last_t)
        if dt < self.config.min_dt_s:
            raise TimebaseError(f"non-monotonic or too-small dt: {dt:.9f}s")
        if dt > self.config.max_dt_s:
            raise TimebaseError(
                f"prediction gap {dt:.6f}s exceeds max_dt_s={self.config.max_dt_s:.6f}s"
            )
        self.last_t = float(imu.timestamp_s)

        E, N, Vw_E, Vw_N, C_E, C_N, psi = self.x
        s, c = np.sin(psi), np.cos(psi)
        a_E = imu.a_fwd_mps2 * s + imu.a_stbd_mps2 * c
        a_N = imu.a_fwd_mps2 * c - imu.a_stbd_mps2 * s

        self.x = np.array(
            [
                E + (Vw_E + C_E) * dt + 0.5 * a_E * dt * dt,
                N + (Vw_N + C_N) * dt + 0.5 * a_N * dt * dt,
                Vw_E + a_E * dt,
                Vw_N + a_N * dt,
                C_E,
                C_N,
                wrap_angle(psi + imu.yaw_rate_rps * dt),
            ],
            dtype=float,
        )

        # Full Jacobian for the published 2-D acceleration rotation.
        # da_E/dpsi = a_N; da_N/dpsi = -a_E.
        F = np.eye(7, dtype=float)
        F[0, 2] = dt
        F[0, 4] = dt
        F[1, 3] = dt
        F[1, 5] = dt
        F[0, 6] = 0.5 * a_N * dt * dt
        F[1, 6] = -0.5 * a_E * dt * dt
        F[2, 6] = a_N * dt
        F[3, 6] = -a_E * dt

        pn = self.config.process_noise
        q_pos = (pn.q_pos_coef * dt) ** 2
        q_vel = (pn.q_vel_coef * np.sqrt(dt)) ** 2
        q_cur = (pn.q_current_coef * np.sqrt(dt)) ** 2
        q_head = (pn.q_heading_coef_rad * np.sqrt(dt)) ** 2
        Q = np.diag([q_pos, q_pos, q_vel, q_vel, q_cur, q_cur, q_head])

        self.P = nearest_psd(
            F @ self.P @ F.T + Q, self.config.covariance_eigen_floor
        )
        require_finite("predicted state", self.x)
        require_finite("predicted covariance", self.P)
        return dt

    def _innovation(
        self,
        z: np.ndarray,
        H: np.ndarray,
        R: np.ndarray,
        *,
        angle_rows: tuple[int, ...] = (),
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        z = np.asarray(z, dtype=float).reshape(-1)
        H = np.asarray(H, dtype=float)
        R = np.asarray(R, dtype=float)
        m = z.size
        if H.shape != (m, 7):
            raise ValueError(f"H must have shape {(m, 7)}, got {H.shape}")
        if R.shape != (m, m):
            raise ValueError(f"R must have shape {(m, m)}, got {R.shape}")
        require_finite("z", z)
        require_finite("H", H)
        require_finite("R", R)
        if np.min(np.linalg.eigvalsh(symmetrize(R))) <= 0:
            raise ValueError("R must be positive definite")

        r = z - H @ self.x
        for row in angle_rows:
            r[row] = wrap_angle(r[row])
        S = nearest_psd(H @ self.P @ H.T + R, self.config.covariance_eigen_floor)

        factor = cho_factor(S, lower=True, check_finite=True)
        solved_r = cho_solve(factor, r)
        nis = float(r.T @ solved_r)
        threshold = float(chi2.ppf(self.config.gate_probability, df=m))
        return r, S, nis, threshold

    def evaluate_measurement(
        self,
        z: np.ndarray,
        H: np.ndarray,
        R: np.ndarray,
        *,
        source: str,
        angle_rows: tuple[int, ...] = (),
    ) -> MeasurementResult:
        _, _, nis, threshold = self._innovation(z, H, R, angle_rows=angle_rows)
        accepted = nis <= threshold
        return MeasurementResult(
            source=source,
            accepted=accepted,
            fused=False,
            nis=nis,
            threshold=threshold,
            dimension=np.asarray(z).size,
            reason="innovation_within_gate" if accepted else "innovation_rejected",
        )

    def update(
        self,
        z: np.ndarray,
        H: np.ndarray,
        R: np.ndarray,
        *,
        source: str,
        angle_rows: tuple[int, ...] = (),
        allow_fusion: bool = True,
    ) -> MeasurementResult:
        r, S, nis, threshold = self._innovation(z, H, R, angle_rows=angle_rows)
        accepted = nis <= threshold
        if not accepted:
            return MeasurementResult(
                source, False, False, nis, threshold, np.asarray(z).size, "innovation_rejected"
            )
        if not allow_fusion:
            return MeasurementResult(
                source, True, False, nis, threshold, np.asarray(z).size, "accepted_probe_only"
            )

        H = np.asarray(H, dtype=float)
        R = np.asarray(R, dtype=float)
        factor = cho_factor(S, lower=True, check_finite=True)
        # K = P H^T S^-1, computed without explicit inversion.
        PHt = self.P @ H.T
        K = cho_solve(factor, PHt.T).T
        self.x = self.x + K @ r
        self.x[6] = wrap_angle(self.x[6])

        I = np.eye(7, dtype=float)
        KH = K @ H
        self.P = nearest_psd(
            (I - KH) @ self.P @ (I - KH).T + K @ R @ K.T,
            self.config.covariance_eigen_floor,
        )
        require_finite("updated state", self.x)
        require_finite("updated covariance", self.P)
        return MeasurementResult(
            source, True, True, nis, threshold, np.asarray(z).size, "accepted_and_fused"
        )

    def update_position(self, E: float, N: float, sigma: float, *, source: str, allow_fusion: bool = True) -> MeasurementResult:
        H = np.zeros((2, 7)); H[0, 0] = 1.0; H[1, 1] = 1.0
        R = np.eye(2) * float(sigma) ** 2
        return self.update(np.array([E, N]), H, R, source=source, allow_fusion=allow_fusion)

    def update_water_velocity(self, Vw_E: float, Vw_N: float, sigma: float, *, source: str, allow_fusion: bool = True) -> MeasurementResult:
        H = np.zeros((2, 7)); H[0, 2] = 1.0; H[1, 3] = 1.0
        R = np.eye(2) * float(sigma) ** 2
        return self.update(np.array([Vw_E, Vw_N]), H, R, source=source, allow_fusion=allow_fusion)

    def update_ground_velocity(self, Vg_E: float, Vg_N: float, sigma: float, *, source: str, allow_fusion: bool = True) -> MeasurementResult:
        H = np.zeros((2, 7)); H[0, 2] = H[0, 4] = 1.0; H[1, 3] = H[1, 5] = 1.0
        R = np.eye(2) * float(sigma) ** 2
        return self.update(np.array([Vg_E, Vg_N]), H, R, source=source, allow_fusion=allow_fusion)

    def update_current_prior(self, C_E: float, C_N: float, sigma: float, *, source: str, allow_fusion: bool = True) -> MeasurementResult:
        H = np.zeros((2, 7)); H[0, 4] = 1.0; H[1, 5] = 1.0
        R = np.eye(2) * float(sigma) ** 2
        return self.update(np.array([C_E, C_N]), H, R, source=source, allow_fusion=allow_fusion)

    def update_heading(self, psi: float, sigma: float, *, source: str, allow_fusion: bool = True) -> MeasurementResult:
        H = np.zeros((1, 7)); H[0, 6] = 1.0
        R = np.array([[float(sigma) ** 2]])
        return self.update(np.array([psi]), H, R, source=source, angle_rows=(0,), allow_fusion=allow_fusion)

    @property
    def position(self) -> tuple[float, float]:
        return float(self.x[0]), float(self.x[1])

    @property
    def ground_velocity(self) -> tuple[float, float]:
        return float(self.x[2] + self.x[4]), float(self.x[3] + self.x[5])

    @property
    def heading(self) -> float:
        return float(self.x[6])

    def containment_proxy(self) -> float:
        P_EN = symmetrize(self.P[:2, :2])
        lam_max = float(np.max(np.linalg.eigvalsh(P_EN)))
        threshold = float(chi2.ppf(self.config.containment_probability, df=2))
        return float(np.sqrt(max(0.0, threshold * lam_max)))
