from dataclasses import replace

import numpy as np
import pytest

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    DeterministicReplay,
    EstimatorBackend,
    EvidenceLog,
    HorizontalIMUInput,
    IntegrityStatus,
    MeasurementEnvelope,
    NavMode,
    ReplayIMUEvent,
    ReplayMeasurementEvent,
    SourceClass,
    SourceDescriptor,
    SourceRegistry,
    build_reference_health_and_constraints,
    build_reference_runtime,
    build_reference_source_registry,
)


def envelope(source, kind, t, values, variance=0.25):
    n = len(values)
    covariance = tuple(
        tuple(float(variance) if i == j else 0.0 for j in range(n))
        for i in range(n)
    )
    return MeasurementEnvelope(
        source=source,
        kind=kind,
        source_timestamp_s=t,
        receive_timestamp_s=t + 0.01,
        values=tuple(float(v) for v in values),
        covariance=covariance,
    )


def seed_non_gnss_full_rank(rt, *, include_visual=False):
    assert rt.ingest_measurement(envelope("radar_map_fix", "position", 1.00, (0.0, 0.0))).accepted
    if include_visual:
        assert rt.ingest_measurement(envelope("visual_map_fix", "position", 1.00, (0.0, 0.0))).accepted
    assert rt.ingest_measurement(envelope("speed_log", "water_velocity", 1.01, (0.0, 0.0))).accepted
    assert rt.ingest_measurement(envelope("current_prior", "current_prior", 1.02, (0.0, 0.0))).accepted
    assert rt.ingest_measurement(envelope("gyrocompass", "heading", 1.03, (0.0,), 0.01)).accepted


def test_amep_filter_satisfies_backend_portability_contract():
    assert isinstance(AMEPFilter(), EstimatorBackend)


def test_assured_reference_runtime_blocks_legacy_measurement_bypass():
    rt = build_reference_runtime()
    with pytest.raises(RuntimeError, match="legacy direct measurement updates are disabled"):
        rt.update_position(timestamp_s=1.0, source="gnss", E=0.0, N=0.0, sigma=1.0)

    health, coverage = build_reference_health_and_constraints()
    compatibility = AMEPRuntime(AMEPFilter(), health, coverage)
    assert compatibility.update_position(
        timestamp_s=1.0, source="gnss", E=0.0, N=0.0, sigma=1.0
    ).accepted


def test_failure_domains_do_not_double_count_shared_primary_chain():
    registry = SourceRegistry()
    registry.register(SourceDescriptor("a", SourceClass.ABSOLUTE_POSITION, "shared", absolute_position=True))
    registry.register(SourceDescriptor("b", SourceClass.ABSOLUTE_POSITION, "shared", absolute_position=True))
    assert registry.failure_domains(("a", "b"), absolute_only=True) == ("shared",)
    assert registry.maximum_independent_count(("a", "b"), absolute_only=True) == 1


def test_shared_secondary_dependency_prevents_false_independence_credit():
    registry = SourceRegistry()
    registry.register(
        SourceDescriptor(
            "radar",
            SourceClass.ABSOLUTE_POSITION,
            "radar_chain",
            absolute_position=True,
            dependencies=("shared_clock",),
        )
    )
    registry.register(
        SourceDescriptor(
            "vision",
            SourceClass.ABSOLUTE_POSITION,
            "vision_chain",
            absolute_position=True,
            dependencies=("shared_clock",),
        )
    )
    assert set(registry.failure_domains(("radar", "vision"), absolute_only=True)) == {
        "radar_chain",
        "vision_chain",
    }
    assert registry.maximum_independent_count(("radar", "vision"), absolute_only=True) == 1


def test_single_non_gnss_absolute_source_cannot_claim_resilient_mode():
    rt = build_reference_runtime()
    seed_non_gnss_full_rank(rt, include_visual=False)
    solution = rt.pnt_solution(now_s=1.10)
    assert solution.information_rank == 7
    assert solution.mode == NavMode.DEGRADED_DEAD_RECKONING
    assert not solution.integrity.resilient_navigation_permitted
    assert solution.integrity.independent_non_gnss_absolute_sources == 1
    assert "insufficient_dependency_disjoint_non_gnss_absolute_sources" in solution.integrity.reasons


def test_two_dependency_disjoint_non_gnss_sources_enable_resilient_mode():
    rt = build_reference_runtime()
    seed_non_gnss_full_rank(rt, include_visual=True)
    solution = rt.pnt_solution(now_s=1.10)
    assert solution.information_rank == 7
    assert solution.mode == NavMode.GPS_DENIED_RESILIENT
    assert solution.integrity.resilient_navigation_permitted
    assert solution.integrity.independent_non_gnss_absolute_sources == 2
    assert len(solution.integrity.declared_non_gnss_absolute_failure_domains) == 2


def test_independent_absolute_conflict_is_blocked_before_fusion_and_alerts():
    rt = build_reference_runtime()
    first = rt.ingest_measurement(envelope("radar_map_fix", "position", 1.0, (0.0, 0.0), 1.0))
    assert first.accepted
    before = rt.estimator.x.copy()
    conflict = rt.ingest_measurement(envelope("visual_map_fix", "position", 1.0, (100.0, -100.0), 1.0))
    assert not conflict.accepted
    assert conflict.reason == "cross_source_consistency_conflict"
    assert np.allclose(rt.estimator.x, before)
    report = rt.integrity_report(now_s=1.01)
    assert report.status == IntegrityStatus.ALERT
    assert not report.navigation_permitted
    assert report.cross_source_conflicts == 1
    assert rt.status(now_s=1.01).mode == NavMode.SAFE_HOLD


def test_reference_registry_declares_distinct_absolute_failure_domains():
    registry = build_reference_source_registry()
    sources = ("gnss", "radar_map_fix", "bathy_map_fix", "visual_map_fix")
    domains = registry.failure_domains(sources, absolute_only=True)
    assert len(domains) == 4
    assert registry.maximum_independent_count(sources, absolute_only=True) == 4
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
    log.append("measurement", timestamp_s=1.0, payload={"source": "gnss", "accepted": True})
    text = log.to_jsonl()
    restored = EvidenceLog.from_jsonl(text)
    assert restored.to_jsonl() == text
    assert EvidenceLog.verify(restored.records()).valid


def test_deterministic_replay_reproduces_solution_and_evidence():
    events = (
        ReplayIMUEvent(0, HorizontalIMUInput(0.0, 0.0, 0.0, 0.0)),
        ReplayIMUEvent(1, HorizontalIMUInput(0.1, 0.0, 0.0, 0.0)),
        ReplayMeasurementEvent(2, envelope("gnss", "position", 0.10, (0.0, 0.0), 1.0)),
        ReplayMeasurementEvent(3, envelope("speed_log", "water_velocity", 0.11, (0.0, 0.0))),
        ReplayMeasurementEvent(4, envelope("current_prior", "current_prior", 0.12, (0.0, 0.0))),
        ReplayMeasurementEvent(5, envelope("gyrocompass", "heading", 0.13, (0.0,), 0.01)),
    )
    run_a = DeterministicReplay().run(build_reference_runtime(), events, final_now_s=0.20)
    run_b = DeterministicReplay().run(build_reference_runtime(), events, final_now_s=0.20)
    assert run_a.events_processed == run_b.events_processed == len(events)
    assert run_a.final_solution.mode == run_b.final_solution.mode == NavMode.NOMINAL
    assert run_a.final_solution.east_m == run_b.final_solution.east_m
    assert run_a.final_solution.north_m == run_b.final_solution.north_m
    assert [r.record_hash for r in run_a.evidence] == [r.record_hash for r in run_b.evidence]
