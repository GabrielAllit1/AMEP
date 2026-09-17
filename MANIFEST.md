# Repository Manifest

This manifest maps the authoritative source, tests, examples, validation records, and repository-support files in the current AMEP research implementation.

## Root

| Path | Function |
| --- | --- |
| `README.md` | Mission, architecture, maturity, verification commands, integrity boundary, and remaining evidence gates. |
| `MANIFEST.md` | This file-by-file repository map. |
| `pyproject.toml` | Python build metadata, runtime/test/QA dependencies, package discovery, pytest, Ruff, and mypy configuration. |
| `.gitignore` | Generated/build/editor exclusions. |
| `CONTRIBUTING.md` | Engineering workflow, verification requirements, and change-quality expectations. |
| `SECURITY.md` | Security/safety reporting guidance and operational-use warning. |
| `CITATION.cff` | Machine-readable citation metadata for the AMEP-1 research release. |

## `src/amep1/`

| Path | Function |
| --- | --- |
| `src/amep1/__init__.py` | Public package exports for estimator, backend, timing, dependency, integrity, FDE, calibration, adapters, replay, evidence, supervision, solution, and profile contracts. |
| `src/amep1/backend.py` | Replaceable `EstimatorBackend`, schema-labeled `EstimatorSnapshot`, and delayed-measurement backend protocol. |
| `src/amep1/estimator.py` | Current seven-state maritime EKF backend with heading-sensitive propagation Jacobian, NIS gating, Cholesky solves, Joseph covariance update, PSD repair, semantic observation dispatch, and explicit covariance schema. |
| `src/amep1/inertial.py` | Local-ENU strapdown INS / 15-error-state ESKF reference backend with attitude, accelerometer/gyro bias states, WGS-84 gravity, Earth-rate/Coriolis terms, covariance propagation, Joseph updates, and explicit SIL-only claim boundary. |
| `src/amep1/fde.py` | Dependency-derived fault hypotheses, explicit integrity-risk bookkeeping, estimator-independent horizontal solution separation, and false-alert/missed-detection/time-to-alert campaign metrics. |
| `src/amep1/installation.py` | Lever-arm, boresight, latency, calibration provenance/covariance contracts plus rigid-body velocity correction and first-order uncertainty propagation. |
| `src/amep1/nmea0183.py` | Checksum-validating selected NMEA 0183 parsing, bounded byte-stream framing, and normalization to `MeasurementEnvelope`; no IEC 61162/electrical-conformance claim. |
| `src/amep1/config.py` | Estimator/process-noise/source policies plus runtime policy for legacy-update and source-registration enforcement. |
| `src/amep1/math_utils.py` | Angle wrapping, covariance symmetrization, nearest-PSD projection, and finite-value validation. |
| `src/amep1/types.py` | Core prediction/result/status contracts including the current preprocessed horizontal IMU input. |
| `src/amep1/enums.py` | Navigation mode, sensor health, and command-authority enumerations. |
| `src/amep1/time_alignment.py` | `MeasurementEnvelope`, clock-domain declaration, timestamp uncertainty, source/receive time preservation, latency/age/future-skew checks, out-of-order handling, configuration export, and two-phase align/commit semantics. |
| `src/amep1/source_registry.py` | Source roles, failure domains, shared dependencies, conservative safety-credit contract, clock/provenance expectations, dependency-disjoint counting, and deterministic registry fingerprint. |
| `src/amep1/consistency.py` | Pre-fusion same-frame absolute-position consistency checks across dependency-disjoint safety-credit source chains. |
| `src/amep1/health.py` | Freshness, innovation rejection history, isolation, probe-only recovery, fusion eligibility, source age, and health-policy configuration export. |
| `src/amep1/constraints.py` | Configurable-state-dimension local constraint-coverage/information-rank heuristic; not formal nonlinear observability. |
| `src/amep1/integrity.py` | Integrity state, navigation permission, dependency-disjoint non-GNSS resilience credit, contradiction handling, and explicit absence of a validated protection level. |
| `src/amep1/authority.py` | Integrity-aware navigation-mode supervision. Non-GNSS resilient mode fails conservative when an integrity report is absent. |
| `src/amep1/solution.py` | Frame/schema-explicit `PNTSolution` with ordered covariance labels, containment probability, health/age, integrity state, and nullable backend-specific maritime quantities. |
| `src/amep1/replay.py` | Deterministic receive-time replay through the online runtime with separate contract/estimator/fusion accounting and platform-neutral prediction events. |
| `src/amep1/evidence.py` | Canonical SHA-256 hash-chained evidence records, deterministic configuration fingerprints, software-tree identity, dependency-version identity, verification, and JSONL round-trip. |
| `src/amep1/comms.py` | Link-priority/freshness support with finite, monotonic, and future-heartbeat rejection. |
| `src/amep1/profile.py` | Seven-state research health/coverage profile, conservative source registry with zero unverified safety credit, and normalized research reference runtime. |
| `src/amep1/runtime.py` | Orchestration façade binding time alignment, source contracts, consistency, estimator, health, coverage, integrity, navigation mode, configuration fingerprinting, and PNT output. |
| `src/amep1/timing.py` | Host-SIL deadline observer with finite/non-monotonic/deadline checks; does not establish target WCET or scheduling determinism. |

## `tests/`

| Path | Function |
| --- | --- |
| `tests/test_estimator.py` | Published water/current semantics, finite-difference heading Jacobian, preprocessed-IMU contract, timebase limits, observation models, outlier rejection, and covariance properties. |
| `tests/test_supervision.py` | Source isolation/recovery, freshness, generic state-dimension coverage, conservative direct-supervisor behavior, nominal GNSS mode, degraded mode, SAFE_HOLD, and probe-only recovery. |
| `tests/test_operations.py` | Communications failover/timestamp validation, watchdog behavior, reference-profile contents, and runtime prediction-fault latching. |
| `tests/test_pnt_backbone.py` | Clock normalization, timestamp uncertainty, ordering, unknown clocks, rejected-contract watermark safety, full-covariance normalized ingestion, integrity veto, nominal operation, and schema-explicit PNT output. |
| `tests/test_production_hardening.py` | Backend portability, normalized-path enforcement, safety-credit prerequisites, shared-dependency handling, resilient-mode permission, pre-fusion contradiction blocking, configuration fingerprints, evidence tamper detection, receive-order replay, and replay acceptance accounting. |
| `tests/test_sil_gap_closure.py` | Strapdown ESKF reference behavior, dependency-derived FDE/risk allocation, detection metrics, installation uncertainty propagation, and NMEA 0183 normalization. |

## `examples/`

| Path | Function |
| --- | --- |
| `examples/runtime_example.py` | Normalized research integration example using `MeasurementEnvelope -> ingest_measurement()` and the conservative reference runtime. Numeric inputs are illustrative software data, not field evidence. |

## `assurance/`

| Path | Function |
| --- | --- |
| `assurance/requirements-to-tests.json` | Executable requirement-to-test traceability, including SIL-only INS, FDE, calibration, and adapter claim boundaries. |

## `docs/`

| Path | Function |
| --- | --- |
| `docs/ARCHITECTURE.md` | Current runtime architecture and subsystem contracts. |
| `docs/GNSS_DENIAL.md` | GNSS-denial objective, current integrity/degradation behavior, source-credit boundary, and staged evidence gates. |
| `docs/PRODUCTION_HARDENING_2026.md` | Engineering rationale, implemented hardening requirements, current architecture, external-review evidence requirements, and P0–P5 remaining gates. |
| `docs/SIL_GAP_CLOSURE_2026.md` | Post-v1.0 SIL increment covering the ESKF, FDE/risk framework, installation-calibration contracts, NMEA normalization, and the evidence gates that remain open. |
| `docs/VALIDATION.md` | Current software-validation status and separation from recorded-data/HIL/field evidence. |
| `docs/validation/TEST_RESULTS.txt` | Historical pre-normalization software validation snapshot. |
| `docs/validation/PNT_BACKBONE_TEST_RESULTS.txt` | Previous PNT-backbone software validation snapshot and historical runner limitation. |
| `docs/validation/PRODUCTION_HARDENING_TEST_RESULTS.txt` | Current production-hardening software-validation snapshot from the dedicated Windows runner. |

## `.github/workflows/`

| Path | Function |
| --- | --- |
| `.github/workflows/ci.yml` | Clean checkout on the dedicated Windows AMEP runner; verifies Python, installs test/QA tooling, compiles, lints, type-checks, performs static security and runtime dependency audits, generates a CycloneDX SBOM, runs coverage-gated pytest, and persists assurance outputs on the self-hosted runner. |

## Architectural scope

The executable seven-state reference estimator is maritime. Portable elements include semantic measurement/time contracts, dependency declarations, configurable state-dimension coverage, estimator backend boundaries, schema-labeled covariance output, integrity/authority behavior, replay, and software evidence. The repository now also includes a local-level 15-state ESKF reference backend and estimator-independent SIL FDE/calibration/adapter components.

A USV, UUV, UAV, UGV, or other integration must still provide and validate its own estimator tuning/dynamics where appropriate, state schema, prediction-input contract, frames/datums, source profile, physical dependency analysis, safety-credit decisions, constraint/observability model, timing profile, installation calibration, hardware adapters, and safe-state behavior.

The current repository does **not** establish certified FDE/RAIM, a validated protection level, calibrated operational INS performance, real sensor/bus validation, target-hardware real-time performance, HIL qualification, or controlled-field/water evidence. Those remain explicit production evidence gates.
