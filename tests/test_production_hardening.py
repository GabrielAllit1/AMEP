from dataclasses import replace

import numpy as np
import pytest

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    DeterministicReplay,
    EstimatorBackend,
    EstimatorConfig,
    EvidenceLog,
    HorizontalIMUInput,
    IntegrityStatus,
    MeasurementEnvelope,
    NavMode,
    ReplayIMUEvent,
    ReplayMeasurementEvent,
    RuntimePolicy,
    SourceClass,
    SourceDescriptor,
    SourceRegistry,
    build_reference_health_and_constraints,
    build_research_reference_runtime,
    build_research_reference_source_registry,
)


def envelope(
    source,
    kind,
    timestamp,
    values,
    variance=0.25,
    *,
    receive_timestamp=None,
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
        receive_timestamp_s=(
            timestamp + 0.01 if receive_timestamp is None else receive_timestamp
        ),
        values=tuple(float(value) for value in values),
        covariance=covariance,
        clock_domain=clock_domain,
        provenance="test.fixture",
        timestamp_uncertainty_s=0.001,
    )


def safety_credit_absolute(
    name,
    failure_domain,
    *,
    dependencies=(),
):
    return SourceDescriptor(
        name,
        SourceClass.ABSOLUTE_POSITION,
        failure_domain,
        absolute_position=True,
        safety_credit=True,
        provenance_required=True,
        max_timestamp_uncertainty_s=0.05,
        dependencies=dependencies,
    )


def build_verified_non_gnss_runtime(*, shared_dependency=False):
    health, coverage = build_reference_health_and_constraints()
    registry = SourceRegistry()
    shared = ("shared_clock",) if shared_dependency else ()
    descriptors = (
        SourceDescriptor(
            "gnss",
            SourceClass.ABSOLUTE_POSITION,
            "gnss_chain",
            absolute_position=True,
            gnss=True,
        ),
        safety_credit_absolute(
            "radar_map_fix",
            "radar_chain",
            dependencies=shared,
        ),
        SourceDescriptor(
            "bathy_map_fix",
            SourceClass.ABSOLUTE_POSITION,
            "bathy_chain",
            absolute_position=True,
        ),
        safety_credit_absolute(
            "visual_map_fix",
            "vision_chain",
            dependencies=shared,
        ),
        SourceDescriptor(
            "speed_log",
            SourceClass.WATER_VELOCITY,
            "speed_chain",
        ),
        SourceDescriptor(
            "ground_velocity",
            SourceClass.GROUND_VELOCITY,
            "ground_velocity_chain",
        ),
        SourceDescriptor(
            "current_prior",
            SourceClass.CURRENT_PRIOR,
            "current_chain",
        ),
        SourceDescriptor(
            "gyrocompass",
            SourceClass.HEADING,
            "heading_chain",
        ),
    )
    for descriptor in descriptors:
        registry.register(descriptor)
    return AMEPRuntime(
        AMEPFilter(),
        health,
        coverage,
        source_registry=registry,
        runtime_policy=RuntimePolicy(
            allow_legacy_direct_updates=False,
            require_registered_sources=True,
        ),
    )


def seed_non_gnss_full_rank(runtime, *, include_visual=False):
    assert runtime.ingest_measurement(
        envelope("radar_map_fix", "position", 1.00, (0.0, 0.0))
    ).accepted
    if include_visual:
        assert runtime.ingest_measurement(
            envelope("visual_map_fix", "position", 1.00, (0.0, 0.0))
        ).accepted
    assert runtime.ingest_measurement(
        envelope("speed_log", "water_velocity", 1.01, (0.0, 0.0))
    ).accepted
    assert runtime.ingest_measurement(
        envelope("current_prior", "current_prior", 1.02, (0.0, 0.0))
    ).accepted
    assert runtime.ingest_measurement(
        envelope("gyrocompass", "heading", 1.03, (0.0,), 0.01)
    ).accepted


def test_amep_filter_satisfies_backend_portability_contract():
    assert isinstance(AMEPFilter(), EstimatorBackend)


def test_research_reference_runtime_blocks_legacy_measurement_bypass():
    runtime = build_research_reference_runtime()
    with pytest.raises(
        RuntimeError,
        match="legacy direct measurement updates are disabled",
    ):
        runtime.update_position(
            timestamp_s=1.0,
            source="gnss",
            E=0.0,
            N=0.0,
            sigma=1.0,
        )

    health, coverage = build_reference_health_and_constraints()
    compatibility = AMEPRuntime(AMEPFilter(), health, coverage)
    assert compatibility.update_position(
        timestamp_s=1.0,
        source="gnss",
        E=0.0,
        N=0.0,
        sigma=1.0,
    ).accepted


def test_research_reference_registry_grants_no_unverified_safety_credit():
    registry = build_research_reference_source_registry()
    assert registry.descriptors()
    assert all(not descriptor.safety_credit for descriptor in registry.descriptors())


def test_safety_credit_requires_provenance_and_timestamp_budget():
    with pytest.raises(ValueError, match="require provenance"):
        SourceDescriptor(
            "radar",
            SourceClass.ABSOLUTE_POSITION,
            "radar_chain",
            absolute_position=True,
            safety_credit=True,
            max_timestamp_uncertainty_s=0.05,
        )

    with pytest.raises(ValueError, match="max_timestamp_uncertainty_s"):
        SourceDescriptor(
            "radar",
            SourceClass.ABSOLUTE_POSITION,
            "radar_chain",
            absolute_position=True,
            safety_credit=True,
            provenance_required=True,
        )


def test_failure_domains_do_not_double_count_shared_primary_chain():
    registry = SourceRegistry()
    registry.register(safety_credit_absolute("a", "shared"))
    registry.register(safety_credit_absolute("b", "shared"))
    assert registry.failure_domains(("a", "b"), absolute_only=True) == ("shared",)
    assert registry.maximum_independent_count(("a", "b"), absolute_only=True) == 1


def test_shared_secondary_dependency_prevents_false_independence_credit():
    registry = SourceRegistry()
    registry.register(
        safety_credit_absolute(
            "radar",
            "radar_chain",
            dependencies=("shared_clock",),
        )
    )
    registry.register(
        safety_credit_absolute(
            "vision",
            "vision_chain",
            dependencies=("shared_clock",),
        )
    )
    assert set(registry.failure_domains(("radar", "vision"), absolute_only=True)) == {
        "radar_chain",
        "vision_chain",
    }
    assert registry.maximum_independent_count(
        ("radar", "vision"), absolute_only=True
    ) == 1


def test_single_verified_non_gnss_absolute_source_cannot_claim_resilient_mode():
    runtime = build_verified_non_gnss_runtime()
    seed_non_gnss_full_rank(runtime, include_visual=False)
    solution = runtime.pnt_solution(now_s=1.10)
    assert solution.information_rank == 7
    assert solution.mode == NavMode.DEGRADED_DEAD_RECKONING
    assert not solution.integrity.resilient_navigation_permitted
    assert solution.integrity.independent_non_gnss_absolute_sources == 1
    assert (
        "insufficient_dependency_disjoint_non_gnss_absolute_sources"
        in solution.integrity.reasons
    )


def test_two_verified_dependency_disjoint_sources_enable_resilient_mode():
    runtime = build_verified_non_gnss_runtime()
    seed_non_gnss_full_rank(runtime, include_visual=True)
    solution = runtime.pnt_solution(now_s=1.10)
    assert solution.information_rank == 7
    assert solution.mode == NavMode.GPS_DENIED_RESILIENT
    assert solution.integrity.resilient_navigation_permitted
    assert solution.integrity.independent_non_gnss_absolute_sources == 2
    assert len(solution.integrity.declared_non_gnss_absolute_failure_domains) == 2


def test_shared_dependency_prevents_resilient_mode_even_with_two_sources():
    runtime = build_verified_non_gnss_runtime(shared_dependency=True)
    seed_non_gnss_full_rank(runtime, include_visual=True)
    solution = runtime.pnt_solution(now_s=1.10)
    assert solution.mode == NavMode.DEGRADED_DEAD_RECKONING
    assert solution.integrity.independent_non_gnss_absolute_sources == 1


def test_independent_absolute_conflict_is_blocked_before_fusion_and_alerts():
    runtime = build_verified_non_gnss_runtime()
    first = runtime.ingest_measurement(
        envelope("radar_map_fix", "position", 1.0, (0.0, 0.0), 1.0)
    )
    assert first.accepted
    before = runtime.estimator.x.copy()
    conflict = runtime.ingest_measurement(
        envelope("visual_map_fix", "position", 1.0, (100.0, -100.0), 1.0)
    )
    assert not conflict.accepted
    assert conflict.reason == "cross_source_consistency_conflict"
    assert np.allclose(runtime.estimator.x, before)
    report = runtime.integrity_report(now_s=1.01)
    assert report.status == IntegrityStatus.ALERT
    assert not report.navigation_permitted
    assert report.cross_source_conflicts == 1
    assert runtime.status(now_s=1.01).mode == NavMode.SAFE_HOLD


def test_reference_registry_documents_domains_without_safety_credit():
    registry = build_research_reference_source_registry()
    sources = ("gnss", "radar_map_fix", "bathy_map_fix", "visual_map_fix")
    domains = registry.failure_domains(
        sources,
        absolute_only=True,
        safety_credit_only=False,
    )
    assert len(domains) == 4
    assert (
        registry.maximum_independent_count(
            sources,
            absolute_only=True,
            safety_credit_only=False,
        )
        == 4
    )
    assert registry.maximum_independent_count(sources, absolute_only=True) == 0
    assert len(registry.fingerprint()) == 64


def test_evidence_log_hash_chain_detects_tamper():
    log = EvidenceLog()
    first = log.append("a", timestamp_s=1.0, payload={"value": 1})
    second = log.append("b", timestamp_s=2.0, payload={"value": 2})
    assert EvidenceLog.verify(log.records()).valid

    tampered = replace(second, payload={"value": 999})
    result = EvidenceLog.verify((first, tampered))
    assert not result.valid
    assert result.reason == "record_hash_mismatch"


def test_evidence_jsonl_round_trip_is_deterministic():
    log = EvidenceLog()
    log.append(
        "measurement",
        timestamp_s=1.0,
        payload={"source": "gnss", "accepted": True},
    )
    text = log.to_jsonl()
    restored = EvidenceLog.from_jsonl(text)
    assert restored.to_jsonl() == text
    assert EvidenceLog.verify(restored.records()).valid


def test_runtime_configuration_fingerprint_changes_with_estimator_configuration():
    health_a, coverage_a = build_reference_health_and_constraints()
    health_b, coverage_b = build_reference_health_and_constraints()
    runtime_a = AMEPRuntime(
        AMEPFilter(config=EstimatorConfig(gate_probability=0.997)),
        health_a,
        coverage_a,
    )
    runtime_b = AMEPRuntime(
        AMEPFilter(config=EstimatorConfig(gate_probability=0.999)),
        health_b,
        coverage_b,
    )
    assert runtime_a.configuration_fingerprint() != runtime_b.configuration_fingerprint()


def test_deterministic_replay_orders_measurements_by_recorded_arrival_time():
    health, coverage = build_reference_health_and_constraints()
    runtime = AMEPRuntime(AMEPFilter(P=np.eye(7)), health, coverage)
    runtime.time_aligner.register_clock_domain(
        "radar_clock",
        offset_to_navigation_s=-99.0,
    )
    events = (
        ReplayMeasurementEvent(
            10,
            envelope(
                "gnss",
                "position",
                1.1,
                (0.0, 0.0),
                1.0,
                receive_timestamp=2.0,
            ),
        ),
        ReplayMeasurementEvent(
            20,
            envelope(
                "radar_map_fix",
                "position",
                100.0,
                (0.0, 0.0),
                1.0,
                receive_timestamp=1.5,
                clock_domain="radar_clock",
            ),
        ),
    )
    replay = DeterministicReplay().run(runtime, events, final_now_s=2.0)
    sources = [
        record.payload["source"]
        for record in replay.evidence
        if record.event_type == "measurement_ingest"
    ]
    assert sources == ["radar_map_fix", "gnss"]


def test_replay_separates_contract_and_estimator_acceptance():
    health, coverage = build_reference_health_and_constraints()
    runtime = AMEPRuntime(AMEPFilter(P=np.eye(7)), health, coverage)
    events = (
        ReplayMeasurementEvent(
            1,
            envelope("gnss", "position", 0.1, (1e5, -1e5), 1.0),
        ),
    )
    replay = DeterministicReplay().run(runtime, events, final_now_s=0.2)
    assert replay.ingest_accepted_measurements == 1
    assert replay.estimator_accepted_measurements == 0
    assert replay.estimator_rejected_measurements == 1
    assert replay.fused_measurements == 0
    assert replay.contract_rejected_measurements == 0


def test_deterministic_replay_reproduces_solution_and_evidence():
    events = (
        ReplayIMUEvent(0, HorizontalIMUInput(0.0, 0.0, 0.0, 0.0)),
        ReplayIMUEvent(1, HorizontalIMUInput(0.1, 0.0, 0.0, 0.0)),
        ReplayMeasurementEvent(
            2,
            envelope("gnss", "position", 0.10, (0.0, 0.0), 1.0),
        ),
        ReplayMeasurementEvent(
            3,
            envelope("speed_log", "water_velocity", 0.11, (0.0, 0.0)),
        ),
        ReplayMeasurementEvent(
            4,
            envelope("current_prior", "current_prior", 0.12, (0.0, 0.0)),
        ),
        ReplayMeasurementEvent(
            5,
            envelope("gyrocompass", "heading", 0.13, (0.0,), 0.01),
        ),
    )
    run_a = DeterministicReplay().run(
        build_research_reference_runtime(),
        events,
        final_now_s=0.20,
    )
    run_b = DeterministicReplay().run(
        build_research_reference_runtime(),
        events,
        final_now_s=0.20,
    )
    assert run_a.events_processed == run_b.events_processed == len(events)
    assert run_a.prediction_events == run_b.prediction_events == 2
    assert run_a.final_solution.mode == run_b.final_solution.mode == NavMode.NOMINAL
    assert run_a.final_solution.east_m == run_b.final_solution.east_m
    assert run_a.final_solution.north_m == run_b.final_solution.north_m
    assert [record.record_hash for record in run_a.evidence] == [
        record.record_hash for record in run_b.evidence
    ]
