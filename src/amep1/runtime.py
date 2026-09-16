from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .authority import NavigationSupervisor
from .constraints import ConstraintCoverage
from .estimator import AMEPFilter, TimebaseError
from .health import SensorHealthManager
from .integrity import IntegrityEngine, IntegrityReport
from .solution import PNTSolution
from .time_alignment import IngestResult, MeasurementEnvelope, TimeAligner, TimeAlignmentResult
from .types import HorizontalIMUInput, MeasurementResult, NavigationStatus


@dataclass
class AMEPRuntime:
    estimator: AMEPFilter
    health: SensorHealthManager
    coverage: ConstraintCoverage
    supervisor: NavigationSupervisor = field(default_factory=NavigationSupervisor)
    time_aligner: TimeAligner = field(default_factory=TimeAligner)
    integrity: IntegrityEngine = field(default_factory=IntegrityEngine)
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

    def _finalize_measurement(
        self,
        source: str,
        timestamp_s: float,
        result: MeasurementResult,
    ) -> MeasurementResult:
        self.health.observe(source, timestamp_s, result)
        return result

    def update_position(
        self,
        *,
        timestamp_s: float,
        source: str,
        E: float,
        N: float,
        sigma: float,
    ) -> MeasurementResult:
        result = self.estimator.update_position(
            E,
            N,
            sigma,
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def update_water_velocity(
        self,
        *,
        timestamp_s: float,
        source: str,
        Vw_E: float,
        Vw_N: float,
        sigma: float,
    ) -> MeasurementResult:
        result = self.estimator.update_water_velocity(
            Vw_E,
            Vw_N,
            sigma,
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def update_ground_velocity(
        self,
        *,
        timestamp_s: float,
        source: str,
        Vg_E: float,
        Vg_N: float,
        sigma: float,
    ) -> MeasurementResult:
        result = self.estimator.update_ground_velocity(
            Vg_E,
            Vg_N,
            sigma,
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def update_current_prior(
        self,
        *,
        timestamp_s: float,
        source: str,
        C_E: float,
        C_N: float,
        sigma: float,
    ) -> MeasurementResult:
        result = self.estimator.update_current_prior(
            C_E,
            C_N,
            sigma,
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def update_heading(
        self,
        *,
        timestamp_s: float,
        source: str,
        psi: float,
        sigma: float,
    ) -> MeasurementResult:
        result = self.estimator.update_heading(
            psi,
            sigma,
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def ingest_measurement(
        self,
        envelope: MeasurementEnvelope,
        *,
        now_s: float | None = None,
    ) -> IngestResult:
        """Align, validate, gate, fuse, and health-account one measurement envelope.

        The current estimator consumes local-ENU measurement products. Raw GNSS,
        radar, camera/LiDAR, DVL, and raw IMU adapters remain separate front-end
        responsibilities and must populate this normalized contract explicitly.
        """
        alignment = self.time_aligner.align(envelope, now_s=now_s)
        if not alignment.accepted or alignment.measurement is None:
            return IngestResult(False, alignment.reason, alignment, None)

        aligned = alignment.measurement
        if envelope.frame != "local_ENU":
            rejected = TimeAlignmentResult(False, "unsupported_frame", aligned)
            return IngestResult(False, "unsupported_frame", rejected, None)

        kind_models: dict[
            str,
            tuple[int, tuple[int, ...], tuple[tuple[int, int, float], ...]],
        ] = {
            "position": (2, (), ((0, 0, 1.0), (1, 1, 1.0))),
            "water_velocity": (2, (), ((0, 2, 1.0), (1, 3, 1.0))),
            "ground_velocity": (
                2,
                (),
                ((0, 2, 1.0), (0, 4, 1.0), (1, 3, 1.0), (1, 5, 1.0)),
            ),
            "current_prior": (2, (), ((0, 4, 1.0), (1, 5, 1.0))),
            "heading": (1, (0,), ((0, 6, 1.0),)),
        }
        model = kind_models.get(envelope.kind)
        if model is None:
            rejected = TimeAlignmentResult(False, "unsupported_measurement_kind", aligned)
            return IngestResult(False, "unsupported_measurement_kind", rejected, None)

        dimension, angle_rows, entries = model
        if len(envelope.values) != dimension:
            rejected = TimeAlignmentResult(False, "measurement_dimension_mismatch", aligned)
            return IngestResult(False, "measurement_dimension_mismatch", rejected, None)

        H = np.zeros((dimension, 7), dtype=float)
        for row, col, value in entries:
            H[row, col] = value
        R = np.asarray(envelope.covariance, dtype=float)
        z = np.asarray(envelope.values, dtype=float)

        try:
            allow_fusion = self.health.may_fuse(envelope.source)
            result = self.estimator.update(
                z,
                H,
                R,
                source=envelope.source,
                angle_rows=angle_rows,
                allow_fusion=allow_fusion,
            )
            self._finalize_measurement(envelope.source, aligned.timestamp_s, result)
        except (KeyError, ValueError, np.linalg.LinAlgError) as exc:
            reason = f"measurement_contract_rejected:{exc}"
            rejected = TimeAlignmentResult(False, reason, aligned)
            return IngestResult(False, reason, rejected, None)

        return IngestResult(True, result.reason, alignment, result)

    def integrity_report(self, now_s: float | None = None) -> IntegrityReport:
        timestamp = self.estimator.last_t if now_s is None else float(now_s)
        if timestamp is not None:
            self.health.refresh(timestamp)
        coverage = self.coverage.compute(self.health.states())
        return self.integrity.evaluate(
            timestamp_s=timestamp,
            coverage=coverage,
            sensor_health=self.health.states(),
            containment_proxy_m=self.estimator.containment_proxy(),
            hard_fault_reason=self.hard_fault_reason,
        )

    def status(self, now_s: float | None = None) -> NavigationStatus:
        timestamp = self.estimator.last_t if now_s is None else float(now_s)
        if timestamp is not None:
            self.health.refresh(timestamp)
        states = self.health.states()
        coverage = self.coverage.compute(states)
        integrity = self.integrity.evaluate(
            timestamp_s=timestamp,
            coverage=coverage,
            sensor_health=states,
            containment_proxy_m=self.estimator.containment_proxy(),
            hard_fault_reason=self.hard_fault_reason,
        )
        mode = self.supervisor.update(coverage, integrity)
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
            sensor_health=states,
            reason=self.supervisor.reason,
        )

    def pnt_solution(self, now_s: float | None = None) -> PNTSolution:
        status = self.status(now_s)
        integrity = self.integrity_report(now_s)
        x = self.estimator.x
        covariance = tuple(tuple(float(v) for v in row) for row in self.estimator.P)
        if status.timestamp_s is None:
            source_age_s = {name: None for name in self.health.states()}
        else:
            source_age_s = self.health.source_ages(status.timestamp_s)

        return PNTSolution(
            timestamp_s=status.timestamp_s,
            mode=status.mode,
            east_m=status.east_m,
            north_m=status.north_m,
            ground_velocity_e_mps=status.ground_velocity_e_mps,
            ground_velocity_n_mps=status.ground_velocity_n_mps,
            water_velocity_e_mps=float(x[2]),
            water_velocity_n_mps=float(x[3]),
            current_e_mps=float(x[4]),
            current_n_mps=float(x[5]),
            heading_rad=status.heading_rad,
            covariance=covariance,
            containment_proxy_95_m=status.containment_proxy_m,
            horizontal_protection_bound_m=integrity.horizontal_protection_bound_m,
            protection_bound_validated=integrity.protection_bound_validated,
            integrity_status=integrity.status,
            integrity=integrity,
            information_rank=status.information_rank,
            state_dim=status.state_dim,
            active_absolute_sources=status.active_absolute_sources,
            sensor_health=status.sensor_health,
            source_age_s=source_age_s,
            reason=status.reason,
        )
