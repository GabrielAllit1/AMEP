# Repository Manifest

This manifest describes the authoritative source, test, example, validation, and project-support files in the normalized AMEP repository after the September 2026 PNT-backbone and production-hardening tranches.

## Root

| Path | Function |
| --- | --- |
| `README.md` | Mission, architecture, maturity, install/test instructions, integrity boundary, and production-hardening direction. |
| `MANIFEST.md` | This file-by-file repository map. |
| `pyproject.toml` | Python build metadata, package discovery, dependencies, test extras, and pytest configuration. |
| `.gitignore` | Generated/build/editor exclusions. |
| `CONTRIBUTING.md` | Engineering workflow and PR quality expectations. |
| `SECURITY.md` | Security/safety reporting guidance and operational-use warning. |
| `CITATION.cff` | Machine-readable citation metadata for the archived AMEP-1 research release. |

## `src/amep1/` — importable package

| Path | Function |
| --- | --- |
| `src/amep1/__init__.py` | Public package surface for estimator, backend, timing, dependency, integrity, replay, evidence, supervision, solution and profile contracts. |
| `src/amep1/backend.py` | State-dimension-agnostic `EstimatorBackend`, portable `EstimatorSnapshot`, and optional `DelayedMeasurementBackend`. Backends own accepted measurement kinds, coordinate frames, state layout, dynamics and observation models. |
| `src/amep1/estimator.py` | Current seven-state maritime EKF backend. Propagates `[E,N,Vw_E,Vw_N,C_E,C_N,psi]`, includes the heading-sensitive Jacobian, NIS gating, Cholesky solves, Joseph covariance update, PSD repair, semantic measurement dispatch, capability declaration and portable snapshots. |
| `src/amep1/config.py` | Estimator/process-noise/source policy plus `RuntimePolicy`; assured profiles can disable legacy direct measurement updates so normalization/integrity cannot be bypassed. |
| `src/amep1/math_utils.py` | Angle wrapping, covariance symmetrization, nearest-PSD projection and finite-value validation. |
| `src/amep1/types.py` | Core typed input/result/status contracts including the current preprocessed horizontal IMU input. |
| `src/amep1/enums.py` | Navigation mode, sensor health and command-authority enumerations. |
| `src/amep1/time_alignment.py` | `MeasurementEnvelope`, clock-domain declaration, timestamp uncertainty, source/receive time preservation, latency/age checks, future-skew rejection, out-of-order handling, and two-phase align/commit semantics. |
| `src/amep1/source_registry.py` | Source roles, primary failure domains, shared integrity dependencies, safety-credit declarations, clock/provenance expectations, dependency-disjoint source counting, and deterministic configuration fingerprinting. |
| `src/amep1/consistency.py` | Pre-fusion near-synchronous absolute-position consistency checks across same-frame, dependency-disjoint sources. Contradictions can be latched without auto-attributing a culprit. |
| `src/amep1/health.py` | Source freshness, innovation rejection history, isolation, probe-only recovery, fusion eligibility and age-of-data. |
| `src/amep1/constraints.py` | Deliberately limited local constraint-coverage/information-rank heuristic; not formal nonlinear observability. |
| `src/amep1/integrity.py` | Integrity state, navigation permission, dependency-disjoint non-GNSS resilience credit, conflict handling and explicit absence of a validated protection level. |
| `src/amep1/authority.py` | Integrity-aware navigation-mode supervision and operator/autonomy/safety command-authority policy. |
| `src/amep1/solution.py` | Portable frame-explicit `PNTSolution` containing covariance, source health/age, integrity state and nullable backend-specific maritime fields. |
| `src/amep1/replay.py` | Deterministic `(timestamp, sequence)` replay through the online runtime; binds evidence to the source-registry fingerprint. |
| `src/amep1/evidence.py` | Canonical SHA-256 hash-chained software evidence log with verification and JSONL round-trip. Tamper-evident, not a digital signature or trusted logger. |
| `src/amep1/comms.py` | Deterministic command/telemetry-link priority and heartbeat freshness selection. |
| `src/amep1/profile.py` | Reference health/coverage policies, reference source-dependency registry, and an assured reference runtime with legacy measurement bypass disabled. |
| `src/amep1/runtime.py` | Orchestration façade: time alignment, backend capability checks, source contracts, pre-fusion consistency, semantic backend updates, health, coverage, integrity, mode supervision and PNT output. Runtime no longer constructs seven-state observation matrices. |
| `src/amep1/timing.py` | Host-SIL deadline watchdog. Does not establish target-hardware WCET or real-time determinism. |

## `tests/` — software contracts

| Path | Function |
| --- | --- |
| `tests/test_estimator.py` | Published water/current semantics, finite-difference heading Jacobian, preprocessed-IMU contract, timebase bounds, covariance reduction, outlier rejection, measurement models and PSD preservation. |
| `tests/test_supervision.py` | Isolation/recovery, freshness, degraded/full-rank modes, SAFE_HOLD and probe-only behavior. |
| `tests/test_operations.py` | Communications failover, watchdog behavior, reference profile contents and runtime hard-fault latching. |
| `tests/test_pnt_backbone.py` | Clock normalization, timestamp uncertainty, ordering, unknown clocks, rejected-contract watermark safety, full-covariance ingestion, integrity veto, nominal operation and rich PNT output. |
| `tests/test_production_hardening.py` | Backend portability, assured-path enforcement, primary/shared dependency handling, dependency-disjoint resilience credit, pre-fusion independent-source contradiction handling, registry fingerprints, evidence-log tamper detection and deterministic replay. |

## `examples/`

| Path | Function |
| --- | --- |
| `examples/runtime_example.py` | Minimal synthetic runtime example. Inputs are placeholders, not validated adapters. |

## `docs/`

| Path | Function |
| --- | --- |
| `docs/ARCHITECTURE.md` | Core architecture and subsystem contracts. |
| `docs/GNSS_DENIAL.md` | GNSS-denial engineering objective, current behavior, remaining spoof/common-cause limits and staged validation path. |
| `docs/PRODUCTION_HARDENING_2026.md` | Current research/standards deep dive, MOSA-style portable architecture, implemented hardening rules and prioritized P0–P5 production gates. |
| `docs/VALIDATION.md` | Software evidence summary and separation from recorded-data/HIL/field evidence. |
| `docs/validation/TEST_RESULTS.txt` | Historical pre-normalization validation snapshot. |
| `docs/validation/PNT_BACKBONE_TEST_RESULTS.txt` | Previous PNT-backbone validation snapshot and no-runner CI limitation. |

## `.github/workflows/`

| Path | Function |
| --- | --- |
| `.github/workflows/ci.yml` | Clean-checkout Python 3.11 install, compile and pytest workflow. Historical runs have failed before runner assignment; zero-step workflow failures are not treated as code-test evidence. |

## Architectural scope

The current executable reference estimator is maritime. The portable work in this repository is the measurement/time/dependency/integrity/replay/authority contract surrounding it. USV, UUV, UAV and UGV integrations may share those contracts while using different estimator backends, frames, source profiles, observability models and safe-state policies.

The hardening tranche does **not** close the archived v1.0 common-mode-bias failure, create certified FDE/RAIM, create a protection level, validate a strapdown INS, validate real sensor/bus adapters, establish target-hardware timing, or provide HIL/controlled-field evidence. Those remain explicit production gates.
