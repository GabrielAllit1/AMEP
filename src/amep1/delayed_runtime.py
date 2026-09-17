from __future__ import annotations

import numpy as np

from .fixed_lag import DelayedMeasurement, FixedLagBackendAdapter, FixedLagWindowError
from .runtime import AMEPRuntime
from .time_alignment import IngestResult, MeasurementEnvelope, TimeAlignmentResult


def ingest_delayed_measurement(
    runtime: AMEPRuntime,
    envelope: MeasurementEnvelope,
    *,
    now_s: float | None = None,
) -> IngestResult:
    """Validate and fuse one out-of-sequence measurement through fixed-lag replay.

    This is the explicit delayed-data companion to ``AMEPRuntime.ingest_measurement``.
    It preserves the same envelope, clock-domain, latency/age, source-contract,
    cross-source-consistency, innovation-gating, health-accounting, and ordering
    contracts. The only relaxed rule is per-source timestamp ordering, and that is
    permitted only when the runtime estimator is ``FixedLagBackendAdapter``.

    The delayed sample is optimized immediately so its estimator result can be
    accounted by the runtime health/integrity path. Applications should not queue
    delayed work directly on the adapter while also using this helper.
    """
    if not isinstance(runtime.estimator, FixedLagBackendAdapter):
        rejected = TimeAlignmentResult(False, "delayed_backend_not_configured")
        return IngestResult(False, rejected.reason, rejected, None)

    alignment = runtime.time_aligner.align(
        envelope,
        now_s=now_s,
        commit=False,
        allow_out_of_order=True,
    )
    if not alignment.accepted or alignment.measurement is None:
        return IngestResult(False, alignment.reason, alignment, None)

    aligned = alignment.measurement
    if envelope.kind not in runtime.estimator.measurement_kinds:
        rejected = TimeAlignmentResult(False, "unsupported_measurement_kind", aligned)
        return IngestResult(False, rejected.reason, rejected, None)
    if envelope.frame not in runtime.estimator.accepted_frames:
        rejected = TimeAlignmentResult(False, "unsupported_frame", aligned)
        return IngestResult(False, rejected.reason, rejected, None)

    source_contract_error = runtime._source_contract_error(  # noqa: SLF001
        envelope, aligned.timestamp_uncertainty_s
    )
    if source_contract_error is not None:
        rejected = TimeAlignmentResult(False, source_contract_error, aligned)
        return IngestResult(False, rejected.reason, rejected, None)

    consistency_report = None
    if envelope.kind == "position":
        consistency_report = runtime.consistency.assess_position(
            aligned, runtime.source_registry
        )
        if not consistency_report.consistent:
            rejected = TimeAlignmentResult(
                False, "cross_source_consistency_conflict", aligned
            )
            return IngestResult(False, rejected.reason, rejected, None)

    effective_now = (
        float(envelope.receive_timestamp_s) if now_s is None else float(now_s)
    )
    metadata = dict(envelope.metadata)
    metadata[FixedLagBackendAdapter.timestamp_metadata_key] = aligned.timestamp_s
    delayed = DelayedMeasurement(
        kind=envelope.kind,
        values=tuple(float(value) for value in envelope.values),
        covariance=tuple(
            tuple(float(value) for value in row) for row in envelope.covariance
        ),
        frame=envelope.frame,
        source=envelope.source,
        metadata=metadata,
        allow_fusion=runtime.health.may_fuse(envelope.source),
    )

    try:
        # Keep this runtime path single-transactional: flush no work that was
        # queued outside the runtime and require exactly one result for this call.
        preexisting = runtime.estimator.optimize(now_s=effective_now)
        if preexisting.applied_delayed_measurements != 0:
            rejected = TimeAlignmentResult(
                False, "delayed_backend_had_external_pending_work", aligned
            )
            return IngestResult(False, rejected.reason, rejected, None)

        runtime.estimator.ingest_delayed(
            source=envelope.source,
            timestamp_s=aligned.timestamp_s,
            payload=delayed,
        )
        outcome = runtime.estimator.optimize(now_s=effective_now)
        if outcome.applied_delayed_measurements != 1 or len(outcome.delayed_results) != 1:
            raise RuntimeError("delayed optimization did not return exactly one result")
        result = outcome.delayed_results[0]
    except (FixedLagWindowError, KeyError, TypeError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        reason = f"delayed_measurement_contract_rejected:{exc}"
        rejected = TimeAlignmentResult(False, reason, aligned)
        return IngestResult(False, reason, rejected, None)

    runtime.health.observe(
        envelope.source,
        aligned.timestamp_s,
        result,
        allow_out_of_order=True,
    )
    runtime.time_aligner.commit(aligned)
    if envelope.kind == "position" and result.accepted and result.fused:
        runtime.consistency.commit_position(
            aligned,
            runtime.source_registry,
            report=consistency_report,
        )

    return IngestResult(True, f"delayed_{result.reason}", alignment, result)
