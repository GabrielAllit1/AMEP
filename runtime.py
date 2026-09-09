from __future__ import annotations

from dataclasses import dataclass, field

from .authority import NavigationSupervisor
from .constraints import ConstraintCoverage, ConstraintSpec
from .estimator import AMEPFilter, TimebaseError
from .health import SensorHealthManager
from .types import HorizontalIMUInput, MeasurementResult, NavigationStatus


@dataclass
class AMEPRuntime:
    estimator: AMEPFilter
    health: SensorHealthManager
    coverage: ConstraintCoverage
    supervisor: NavigationSupervisor = field(default_factory=NavigationSupervisor)
    hard_fault_reason: str | None = None

    def predict(self, imu: HorizontalIMUInput) -> float:
        try:
            return self.estimator.predict(imu)
        except (TimebaseError, ValueError) as exc:
            self.hard_fault_reason = f"prediction_fault:{exc}"
            self.supervisor.force_safe_hold(self.hard_fault_reason)
            raise

    def clear_hard_fault(self) -> None:
        """Explicit operator/integration recovery hook after the root cause is handled."""
        self.hard_fault_reason = None

    def _finalize_measurement(self, source: str, timestamp_s: float, result: MeasurementResult) -> MeasurementResult:
        self.health.observe(source, timestamp_s, result)
        return result

    def update_position(self, *, timestamp_s: float, source: str, E: float, N: float, sigma: float) -> MeasurementResult:
        result = self.estimator.update_position(E, N, sigma, source=source, allow_fusion=self.health.may_fuse(source))
        return self._finalize_measurement(source, timestamp_s, result)

    def update_water_velocity(self, *, timestamp_s: float, source: str, Vw_E: float, Vw_N: float, sigma: float) -> MeasurementResult:
        result = self.estimator.update_water_velocity(Vw_E, Vw_N, sigma, source=source, allow_fusion=self.health.may_fuse(source))
        return self._finalize_measurement(source, timestamp_s, result)

    def update_ground_velocity(self, *, timestamp_s: float, source: str, Vg_E: float, Vg_N: float, sigma: float) -> MeasurementResult:
        result = self.estimator.update_ground_velocity(Vg_E, Vg_N, sigma, source=source, allow_fusion=self.health.may_fuse(source))
        return self._finalize_measurement(source, timestamp_s, result)

    def update_current_prior(self, *, timestamp_s: float, source: str, C_E: float, C_N: float, sigma: float) -> MeasurementResult:
        result = self.estimator.update_current_prior(C_E, C_N, sigma, source=source, allow_fusion=self.health.may_fuse(source))
        return self._finalize_measurement(source, timestamp_s, result)

    def update_heading(self, *, timestamp_s: float, source: str, psi: float, sigma: float) -> MeasurementResult:
        result = self.estimator.update_heading(psi, sigma, source=source, allow_fusion=self.health.may_fuse(source))
        return self._finalize_measurement(source, timestamp_s, result)

    def status(self, now_s: float | None = None) -> NavigationStatus:
        timestamp = self.estimator.last_t if now_s is None else now_s
        if timestamp is not None:
            self.health.refresh(timestamp)
        coverage = self.coverage.compute(self.health.states())
        if self.hard_fault_reason is not None:
            mode = self.supervisor.force_safe_hold(self.hard_fault_reason)
        else:
            mode = self.supervisor.update(coverage)
        vg_e, vg_n = self.estimator.ground_velocity
        E, N = self.estimator.position
        return NavigationStatus(
            timestamp_s=timestamp,
            mode=mode,
            east_m=E,
            north_m=N,
            ground_velocity_e_mps=vg_e,
            ground_velocity_n_mps=vg_n,
            heading_rad=self.estimator.heading,
            containment_proxy_m=self.estimator.containment_proxy(),
            information_rank=coverage.information_rank,
            state_dim=coverage.state_dim,
            active_absolute_sources=coverage.active_absolute_sources,
            sensor_health=self.health.states(),
            reason=self.supervisor.reason,
        )
