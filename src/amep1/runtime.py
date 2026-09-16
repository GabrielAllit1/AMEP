from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .authority import NavigationSupervisor
from .backend import EstimatorBackend
from .consistency import CrossSourceConsistencyMonitor
from .constraints import ConstraintCoverage
from .estimator import TimebaseError
from .health import SensorHealthManager
from .integrity import IntegrityEngine, IntegrityReport
from .solution import PNTSolution
from .source_registry import SourceClass, SourceRegistry
from .time_alignment import IngestResult, MeasurementEnvelope, TimeAligner, TimeAlignmentResult
from .types import HorizontalIMUInput, MeasurementResult, NavigationStatus


@dataclass
class AMEPRuntime:
    estimator: EstimatorBackend
    health: SensorHealthManager
    coverage: ConstraintCoverage
    supervisor: NavigationSupervisor = field(default_factory=NavigationSupervisor)
    time_aligner: TimeAligner = field(default_factory=TimeAligner)
    integrity: IntegrityEngine = field(default_factory=IntegrityEngine)
    source_registry: SourceRegistry = field(default_factory=SourceRegistry)
    consistency: CrossSourceConsistencyMonitor = field(default_factory=CrossSourceConsistencyMonitor)
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
        result = self.estimator.update(
            np.array([E, N], dtype=float),
            np.array([[1, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0]], dtype=float),
            np.eye(2) * float(sigma) ** 2,
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
        H = np.zeros((2, 7)); H[0, 2] = 1.0; H[1, 3] = 1.0
        result = self.estimator.update(
            np.array([Vw_E, Vw_N], dtype=float), H, np.eye(2) * float(sigma) ** 2,
            source=source, allow_fusion=self.health.may_fuse(source),
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
        H = np.zeros((2, 7)); H[0, 2] = H[0, 4] = 1.0; H[1, 3] = H[1, 5] = 1.0
        result = self.estimator.update(
            np.array([Vg_E, Vg_N], dtype=float), H, np.eye(2) * float(sigma) ** 2,
            source=source, allow_fusion=self.health.may_fuse(source),
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
        H = np.zeros((2, 7)); H[0, 4] = 1.0; H[1, 5] = 1.0
        result = self.estimator.update(
            np.array([C_E, C_N], dtype=float), H, np.eye(2) * float(sigma) ** 2,
            source=source, allow_fusion=self.health.may_fuse(source),
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
        H = np.zeros((1, 7)); H[0, 6] = 1.0
        result = self.estimator.update(
            np.array([psi], dtype=float), H, np.array([[float(sigma) ** 2]]),
            source=source, angle_rows=(0,), allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def _source_contract_error(self, envelope: MeasurementEnvelope, timestamp_uncertainty_s: float) -> str | None:
        descriptor = self.source_registry.descriptor(envelope.source)
        if descriptor is None:
            return None
        if descriptor.clock_domain != envelope.clock_domain:
            return "source_clock_domain_mismatch"
        if descriptor.provenance_required and not envelope.provenance:
            return "source_provenance_required"
        if (
            descriptor.max_timestamp_uncertainty_s is not None
            and timestamp_uncertainty_s > descriptor.max_timestamp_uncertainty_s
        ):
            return "source_timestamp_uncertainty_exceeded"
        expected_kind = {
            SourceClass.ABSOLUTE_POSITION: "position",
            SourceClass.WATER_VELOCITY: "water_velocity",
            SourceClass.GROUND_VELOCITY: "ground_velocity",
            SourceClass.CURRENT_PRIOR: "current_prior",
            SourceClass.HEADING: "heading",
        }.get(descriptor.source_class)
        if expected_kind is not None and envelope.kind != expected_kind:
            return "source_measurement_class_mismatch"
        return None

    def ingest_measurement(
        self,
        envelope: MeasurementEnvelope,
        *,
        now_s: float | None = None,
    ) -> IngestResult:
        """Align, validate, cross-check, gate, fuse, and health-account a measurement."""
        alignment = self.time_aligner.align(envelope, now_s=now_s, commit=False)
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
            "ground_velocity": (2, (), ((0, 2, 1.0), (0, 4, 1.0), (1, 3, 1.0), (1, 5, 1.0))),
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

        source_contract_error = self._source_contract_error(
            envelope, aligned.timestamp_uncertainty_s
        )
        if source_contract_error is not None:
            rejected = TimeAlignmentResult(False, source_contract_error, aligned)
            return IngestResult(False, source_contract_error, rejected, None)

        if envelope.kind == "position":
            consistency = self.consistency.assess_position(aligned, self.source_registry)
            if not consistency.consistent:
                rejected = TimeAlignmentResult(False, "cross_source_consistency_conflict", aligned)
                return IngestResult(False, "cross_source_consistency_conflict", rejected, None)

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
            self.time_aligner.commit(aligned)
            if envelope.kind == "position" and result.accepted and result.fused:
                self.consistency.commit_position(aligned, self.source_registry)
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
            source_registry=self.source_registry,
            consistency=self.consistency.last_report,
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
            source_registry=self.source_registry,
            consistency=self.consistency.last_report,
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
