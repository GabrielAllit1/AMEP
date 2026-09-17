import numpy as np

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    IntegrityStatus,
    MeasurementEnvelope,
    NavMode,
    RuntimePolicy,
    TimeAligner,
    build_reference_health_and_constraints,
)


def envelope(
    source,
    kind,
    timestamp,
    values,
    variance,
    *,
    clock_domain="navigation",
):
    dimension = len(values)
    covariance = tuple(
        tuple(float(variance) if row == column else 0.0 for column in range(dimension))
        for row in range(dimension)
    )
    return MeasurementEnvelope(
        source=source,
        kind=kind,
        source_timestamp_s=timestamp,
        receive_timestamp_s=timestamp + 0.05,
        values=tuple(float(value) for value in values),
        covariance=covariance,
        clock_domain=clock_domain,
    )


def compatibility_runtime(*, covariance=None):
    health, coverage = build_reference_health_and_constraints()
    estimator = AMEPFilter() if covariance is None else AMEPFilter(P=covariance)
    return AMEPRuntime(
        estimator,
        health,
        coverage,
        runtime_policy=RuntimePolicy.compatibility(),
    )


def test_time_alignment_normalizes_clock_domain_and_rejects_out_of_order():
    aligner = TimeAligner()
    aligner.register_clock_domain(
        "sensor_clock",
        offset_to_navigation_s=1.0,
        uncertainty_s=0.01,
    )
    first = MeasurementEnvelope(
        source="gnss",
        kind="position",
        source_timestamp_s=9.0,
        receive_timestamp_s=10.05,
        values=(0.0, 0.0),
        covariance=((1.0, 0.0), (0.0, 1.0)),
        clock_domain="sensor_clock",
        timestamp_uncertainty_s=0.02,
    )
    aligned = aligner.align(first, now_s=10.05)
    assert aligned.accepted
    assert aligned.measurement is not None
    assert aligned.measurement.timestamp_s == 10.0
    assert np.isclose(aligned.measurement.timestamp_uncertainty_s, 0.03)

    older = MeasurementEnvelope(
        source="gnss",
        kind="position",
        source_timestamp_s=8.9,
        receive_timestamp_s=10.10,
        values=(0.0, 0.0),
        covariance=((1.0, 0.0), (0.0, 1.0)),
        clock_domain="sensor_clock",
    )
    rejected = aligner.align(older, now_s=10.10)
    assert not rejected.accepted
    assert rejected.reason == "out_of_order_measurement"


def test_unknown_clock_domain_fails_closed_before_fusion():
    runtime = compatibility_runtime()
    result = runtime.ingest_measurement(
        envelope(
            "gnss",
            "position",
            1.0,
            (0.0, 0.0),
            1.0,
            clock_domain="unknown",
        )
    )
    assert not result.accepted
    assert result.reason == "unknown_clock_domain"
    assert result.measurement_result is None


def test_rejected_contract_does_not_advance_source_time_watermark():
    runtime = compatibility_runtime(covariance=np.eye(7))

    malformed = envelope(
        "gnss",
        "not_a_measurement_kind",
        2.0,
        (0.0, 0.0),
        1.0,
    )
    rejected = runtime.ingest_measurement(malformed)
    assert not rejected.accepted
    assert rejected.reason == "unsupported_measurement_kind"

    valid_older = envelope("gnss", "position", 1.9, (0.0, 0.0), 1.0)
    accepted = runtime.ingest_measurement(valid_older)
    assert accepted.accepted
    assert accepted.measurement_result is not None


def test_normalized_measurements_drive_nominal_mode_and_rich_pnt_solution():
    runtime = compatibility_runtime(covariance=np.eye(7))

    assert runtime.ingest_measurement(
        envelope("gnss", "position", 1.00, (0.0, 0.0), 1.0)
    ).accepted
    assert runtime.ingest_measurement(
        envelope("speed_log", "water_velocity", 1.01, (0.0, 0.0), 0.25)
    ).accepted
    assert runtime.ingest_measurement(
        envelope("current_prior", "current_prior", 1.02, (0.0, 0.0), 0.25)
    ).accepted
    assert runtime.ingest_measurement(
        envelope("gyrocompass", "heading", 1.03, (0.0,), 0.01)
    ).accepted

    solution = runtime.pnt_solution(now_s=1.10)
    assert solution.mode == NavMode.NOMINAL
    assert solution.information_rank == 7
    assert solution.integrity_status == IntegrityStatus.MONITORING
    assert solution.integrity.navigation_permitted
    assert not solution.protection_bound_validated
    assert solution.horizontal_protection_bound_m is None
    assert solution.horizontal_containment_proxy_m > 0
    assert solution.containment_probability == 0.95
    assert solution.state_schema_id == "amep1.horizontal.v1"
    assert len(solution.covariance) == 7
    assert all(len(row) == 7 for row in solution.covariance)
    assert len(solution.covariance_labels) == 7
    assert solution.source_age_s["gnss"] is not None
    assert solution.attitude_available is False
    assert solution.navigation_time_validated is False


def test_integrity_blocks_navigation_when_constraint_rank_is_insufficient():
    runtime = compatibility_runtime()
    report = runtime.integrity_report(now_s=0.0)
    status = runtime.status(now_s=0.0)
    assert report.status == IntegrityStatus.UNAVAILABLE
    assert not report.navigation_permitted
    assert status.mode == NavMode.SAFE_HOLD
    assert status.reason.startswith("integrity_blocked:")


def test_full_covariance_measurement_contract_is_used_by_runtime():
    runtime = compatibility_runtime(covariance=np.eye(7))
    measurement = MeasurementEnvelope(
        source="gnss",
        kind="position",
        source_timestamp_s=2.0,
        receive_timestamp_s=2.02,
        values=(0.1, -0.1),
        covariance=((1.0, 0.2), (0.2, 2.0)),
    )
    result = runtime.ingest_measurement(measurement)
    assert result.accepted
    assert result.measurement_result is not None
    assert result.measurement_result.accepted
    assert result.measurement_result.fused
