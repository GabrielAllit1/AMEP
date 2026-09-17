from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum

import numpy as np

from .authority import NavigationSupervisor
from .backend import EstimatorBackend
from .config import RuntimePolicy
from .consistency import CrossSourceConsistencyMonitor
from .constraints import ConstraintCoverage
from .estimator import TimebaseError
from .evidence import JSONValue, canonical_fingerprint, software_identity
from .health import SensorHealthManager
from .integrity import IntegrityEngine, IntegrityReport
from .solution import PNTSolution
from .source_registry import SourceClass, SourceRegistry
from .time_alignment import (
    IngestResult,
    MeasurementEnvelope,
    TimeAligner,
    TimeAlignmentResult,
)
from .types import MeasurementResult, NavigationStatus


def _jsonable(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    raise TypeError(f"configuration value is not JSON-compatible: {type(value).__name__}")


@dataclass
class AMEPRuntime:
    estimator: EstimatorBackend
    health: SensorHealthManager
    coverage: ConstraintCoverage
    supervisor: NavigationSupervisor = field(default_factory=NavigationSupervisor)
    time_aligner: TimeAligner = field(default_factory=TimeAligner)
    integrity: IntegrityEngine = field(default_factory=IntegrityEngine)
    source_registry: SourceRegistry = field(default_factory=SourceRegistry)
    consistency: CrossSourceConsistencyMonitor = field(
        default_factory=CrossSourceConsistencyMonitor
    )
    runtime_policy: RuntimePolicy = field(default_factory=RuntimePolicy)
    hard_fault_reason: str | None = None

    def predict(self, prediction_input: object) -> float:
        try:
            return self.estimator.predict(prediction_input)
        except (TimebaseError, ValueError, TypeError) as exc:
            self.hard_fault_reason = f"prediction_fault:{exc}"
            self.supervisor.force_safe_hold(self.hard_fault_reason)
            raise

    def clear_hard_fault(self) -> None:
        """Explicit recovery hook after the prediction-fault root cause is handled."""
        self.hard_fault_reason = None

    def configuration_manifest(self) -> dict[str, JSONValue]:
        """Return behavior-affecting runtime configuration plus software identity."""
        estimator_config = getattr(self.estimator, "config", None)
        estimator_configuration: JSONValue
        if estimator_config is None:
            estimator_configuration = None
        else:
            try:
                estimator_configuration = _jsonable(estimator_config)
            except TypeError:
                estimator_configuration = {
                    "type": (
                        f"{type(estimator_config).__module__}."
                        f"{type(estimator_config).__qualname__}"
                    ),
                    "serialization": "unavailable",
                }

        return {
            "software": software_identity(),
            "estimator": {
                "type": (
                    f"{type(self.estimator).__module__}."
                    f"{type(self.estimator).__qualname__}"
                ),
                "measurement_kinds": list(self.estimator.measurement_kinds),
                "accepted_frames": list(self.estimator.accepted_frames),
                "config": estimator_configuration,
            },
            "health": _jsonable(self.health.configuration()),
            "coverage": _jsonable(self.coverage.configuration()),
            "source_registry": {
                "sha256": self.source_registry.fingerprint(),
                "sources": _jsonable(self.source_registry.configuration()),
            },
            "time_alignment": _jsonable(self.time_aligner.configuration()),
            "integrity_policy": _jsonable(self.integrity.policy),
            "consistency_policy": _jsonable(self.consistency.policy),
            "navigation_policy": _jsonable(self.supervisor.policy),
            "runtime_policy": _jsonable(self.runtime_policy),
        }

    def configuration_fingerprint(self) -> str:
        return canonical_fingerprint(self.configuration_manifest())

    def _require_legacy_direct_updates(self) -> None:
        if not self.runtime_policy.allow_legacy_direct_updates:
            raise RuntimeError(
                "legacy direct measurement updates are disabled by runtime policy; "
                "use ingest_measurement so timing/provenance/dependency checks cannot be bypassed"
            )

    def _finalize_measurement(
        self,
        source: str,
        timestamp_s: float,
        result: MeasurementResult,
    ) -> MeasurementResult:
        self.health.observe(source, timestamp_s, result)
        return result

    def _legacy_update(
        self,
        *,
        timestamp_s: float,
        source: str,
        kind: str,
        values: np.ndarray,
        covariance: np.ndarray,
    ) -> MeasurementResult:
        self._require_legacy_direct_updates()
        result = self.estimator.update_measurement(
            kind,
            values,
            covariance,
            frame="local_ENU",
            source=source,
            allow_fusion=self.health.may_fuse(source),
        )
        return self._finalize_measurement(source, timestamp_s, result)

    def update_position(
        self,
        *,
        timestamp_s: float,
        source: str,
        E: float,
        N: float,
        sigma: float,
    ) -> MeasurementResult:
        return self._legacy_update(
            timestamp_s=timestamp_s,
            source=source,
            kind="position",
            values=np.array([E, N], dtype=float),
            covariance=np.eye(2) * float(sigma) ** 2,
        )

    def update_water_velocity(
        self,
        *,
        timestamp_s: float,
        source: str,
        Vw_E: float,
        Vw_N: float,
        sigma: float,
    ) -> MeasurementResult:
        return self._legacy_update(
            timestamp_s=timestamp_s,
            source=source,
            kind="water_velocity",
            values=np.array([Vw_E, Vw_N], dtype=float),
            covariance=np.eye(2) * float(sigma) ** 2,
        )

    def update_ground_velocity(
        self,
        *,
        timestamp_s: float,
        source: str,
        Vg_E: float,
        Vg_N: float,
        sigma: float,
    ) -> MeasurementResult:
        return self._legacy_update(
            timestamp_s=timestamp_s,
            source=source,
            kind="ground_velocity",
            values=np.array([Vg_E, Vg_N], dtype=float),
            covariance=np.eye(2) * float(sigma) ** 2,
        )

    def update_current_prior(
        self,
        *,
        timestamp_s: float,
        source: str,
        C_E: float,
        C_N: float,
        sigma: float,
    ) -> MeasurementResult:
        return self._legacy_update(
            timestamp_s=timestamp_s,
            source=source,
            kind="current_prior",
            values=np.array([C_E, C_N], dtype=float),
            covariance=np.eye(2) * float(sigma) ** 2,
        )

    def update_heading(
        self,
        *,
        timestamp_s: float,
        source: str,
        psi: float,
        sigma: float,
    ) -> MeasurementResult:
        return self._legacy_update(
            timestamp_s=timestamp_s,
            source=source,
            kind="heading",
            values=np.array([psi], dtype=float),
            covariance=np.array([[float(sigma) ** 2]]),
        )

    def _source_contract_error(
        self,
        envelope: MeasurementEnvelope,
        timestamp_uncertainty_s: float,
    ) -> str | None:
        descriptor = self.source_registry.descriptor(envelope.source)
        if descriptor is None:
            if self.runtime_policy.require_registered_sources:
                return "unregistered_source_descriptor"
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
        """Align, validate, cross-check, backend-update, and account a measurement."""
        alignment = self.time_aligner.align(envelope, now_s=now_s, commit=False)
        if not alignment.accepted or alignment.measurement is None:
            return IngestResult(False, alignment.reason, alignment, None)

        aligned = alignment.measurement
        if envelope.kind not in self.estimator.measurement_kinds:
            rejected = TimeAlignmentResult(False, "unsupported_measurement_kind", aligned)
            return IngestResult(False, "unsupported_measurement_kind", rejected, None)
        if envelope.frame not in self.estimator.accepted_frames:
            rejected = TimeAlignmentResult(False, "unsupported_frame", aligned)
            return IngestResult(False, "unsupported_frame", rejected, None)

        source_contract_error = self._source_contract_error(
            envelope, aligned.timestamp_uncertainty_s
        )
        if source_contract_error is not None:
            rejected = TimeAlignmentResult(False, source_contract_error, aligned)
            return IngestResult(False, source_contract_error, rejected, None)

        consistency_report = None
        if envelope.kind == "position":
            consistency_report = self.consistency.assess_position(
                aligned, self.source_registry
            )
            if not consistency_report.consistent:
                rejected = TimeAlignmentResult(
                    False, "cross_source_consistency_conflict", aligned
                )
                return IngestResult(
                    False,
                    "cross_source_consistency_conflict",
                    rejected,
                    None,
                )

        try:
            allow_fusion = self.health.may_fuse(envelope.source)
            result = self.estimator.update_measurement(
                envelope.kind,
                np.asarray(envelope.values, dtype=float),
                np.asarray(envelope.covariance, dtype=float),
                frame=envelope.frame,
                source=envelope.source,
                metadata=envelope.metadata,
                allow_fusion=allow_fusion,
            )
            self._finalize_measurement(envelope.source, aligned.timestamp_s, result)
            self.time_aligner.commit(aligned)
            if envelope.kind == "position" and result.accepted and result.fused:
                self.consistency.commit_position(
                    aligned,
                    self.source_registry,
                    report=consistency_report,
                )
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
        snapshot = self.estimator.snapshot()
        return NavigationStatus(
            timestamp_s=timestamp,
            mode=mode,
            east_m=snapshot.east_m,
            north_m=snapshot.north_m,
            ground_velocity_e_mps=snapshot.ground_velocity_e_mps,
            ground_velocity_n_mps=snapshot.ground_velocity_n_mps,
            heading_rad=snapshot.heading_rad,
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
        snapshot = self.estimator.snapshot()
        covariance = tuple(
            tuple(float(value) for value in row)
            for row in np.asarray(snapshot.covariance, dtype=float)
        )
        if status.timestamp_s is None:
            source_age_s = {name: None for name in self.health.states()}
        else:
            source_age_s = self.health.source_ages(status.timestamp_s)

        estimator_config = getattr(self.estimator, "config", None)
        probability = getattr(estimator_config, "containment_probability", None)
        containment_probability = None if probability is None else float(probability)

        return PNTSolution(
            timestamp_s=status.timestamp_s,
            mode=status.mode,
            frame=snapshot.frame,
            east_m=status.east_m,
            north_m=status.north_m,
            ground_velocity_e_mps=status.ground_velocity_e_mps,
            ground_velocity_n_mps=status.ground_velocity_n_mps,
            water_velocity_e_mps=snapshot.water_velocity_e_mps,
            water_velocity_n_mps=snapshot.water_velocity_n_mps,
            current_e_mps=snapshot.current_e_mps,
            current_n_mps=snapshot.current_n_mps,
            heading_rad=status.heading_rad,
            covariance=covariance,
            state_schema_id=snapshot.state_schema_id,
            covariance_labels=snapshot.covariance_labels,
            containment_probability=containment_probability,
            horizontal_containment_proxy_m=status.containment_proxy_m,
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
