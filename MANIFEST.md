# Repository Manifest

This manifest describes every authoritative source, test, example, and project-support file in the AMEP repository after the September 2026 repository normalization and PNT-backbone integration.

## Root

| Path | Function |
| --- | --- |
| `README.md` | Project information page: mission, EKF architecture, GNSS-denial objective, maturity, install/test instructions, and evidence boundary. |
| `MANIFEST.md` | This file-by-file repository map. |
| `pyproject.toml` | Python build metadata, package discovery, dependencies, optional test dependencies, and pytest configuration. |
| `.gitignore` | Excludes Python bytecode, pytest caches, virtual environments, build output, coverage output, editor state, and OS-generated files. |
| `CONTRIBUTING.md` | Engineering workflow and pull-request quality expectations. |
| `SECURITY.md` | Security/safety reporting guidance and operational-use warning. |
| `CITATION.cff` | Machine-readable citation metadata for the AMEP-1 research release. |

## `src/amep1/` — importable package

| Path | Function |
| --- | --- |
| `src/amep1/__init__.py` | Public package surface. Re-exports estimator, timing/alignment, integrity, supervision, solution, policy, watchdog, and reference-profile contracts. |
| `src/amep1/estimator.py` | Core seven-state Extended Kalman Filter. Propagates `[E,N,Vw_E,Vw_N,C_E,C_N,psi]`, rotates leveled body acceleration into the local frame, propagates the heading-sensitive Jacobian, applies chi-square NIS gates, computes Kalman gain by Cholesky solve, performs Joseph-form covariance updates, enforces PSD covariance, and exposes typed measurement helpers. |
| `src/amep1/config.py` | Immutable estimator and source-policy configuration. Defines process-noise coefficients, gate/containment probabilities, prediction time-step limits, covariance floor, freshness, isolation, rejection-window, and recovery thresholds. |
| `src/amep1/math_utils.py` | Numerical safety helpers: angle wrapping, covariance symmetrization, nearest-positive-semidefinite projection, and finite-value validation. |
| `src/amep1/types.py` | Core dataclass contracts shared across legacy/current modules: validated horizontal IMU input, measurement results, constraint-coverage results, authority decisions, and structured navigation status. |
| `src/amep1/enums.py` | Enumerations for navigation mode, sensor health state, and command-authority source. |
| `src/amep1/time_alignment.py` | Normalized `MeasurementEnvelope`, clock-domain declaration, timestamp uncertainty, source/receive time preservation, transport-latency/age checks, out-of-order rejection, and typed ingest/alignment results. The current policy rejects delayed measurements that the real-time EKF cannot rewind for. |
| `src/amep1/health.py` | Per-source health state machine. Tracks freshness, repeated innovation rejection, sliding rejection fraction, manual isolation, probe-only recovery, fusion eligibility, and source age-of-data. |
| `src/amep1/constraints.py` | Implements AMEP's deliberately limited local constraint-coverage heuristic. Maps healthy sensor classes to observed state indices and computes information rank/conditioning plus GNSS/non-GNSS absolute-source availability. It is not a formal nonlinear-observability proof. |
| `src/amep1/integrity.py` | Explicit integrity contract between estimation/health and mode authority. Produces `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT`, can veto navigation authority, and explicitly leaves the protection bound unavailable/unvalidated. This is not certified RAIM/FDE. |
| `src/amep1/authority.py` | Navigation and command-authority supervisor. Applies an integrity veto before converting constraint coverage into `NOMINAL`, `GPS_DENIED_RESILIENT`, `DEGRADED_DEAD_RECKONING`, or `SAFE_HOLD`, then enforces operator > autonomy > safety authority rules. |
| `src/amep1/solution.py` | Rich `PNTSolution` output contract: horizontal state, water/ground velocity, current, heading, full state covariance, containment proxy, integrity report/status, source health/age, active constraints, mode, and explicit unsupported protection/attitude/time fields. |
| `src/amep1/comms.py` | Communications supervision. Registers command/telemetry links with priority and heartbeat-age policies and chooses the highest-priority healthy link deterministically. |
| `src/amep1/profile.py` | Builds the generic reference source profile used by examples/tests: GNSS, radar map fix, bathymetric map fix, visual map fix, speed log, ground velocity, current prior, and gyrocompass. Values are integration examples, not vessel-calibrated limits. |
| `src/amep1/runtime.py` | High-level integration façade. Preserves the existing `predict`/`update_*`/`status` APIs and adds normalized measurement ingestion, time alignment, full-covariance fusion, health accounting, integrity reporting, integrity-aware mode supervision, and rich PNT solution output. |
| `src/amep1/timing.py` | Host-SIL deadline watchdog for monotonic timestamps and missed-deadline detection. It does not establish target-hardware real-time guarantees. |

## `tests/` — software contracts

| Path | Function |
| --- | --- |
| `tests/test_estimator.py` | Verifies water/current ground-velocity semantics, finite-difference heading Jacobian terms, gravity-compensated IMU contract, monotonic time, maximum prediction gap, covariance reduction, outlier rejection, velocity/current/heading updates, and PSD covariance preservation. |
| `tests/test_supervision.py` | Verifies source isolation and recovery, stale transitions, reachable degraded mode, GNSS and non-GNSS full-rank navigation modes, low-rank `SAFE_HOLD`, and probe-only handling of isolated sources. |
| `tests/test_operations.py` | Verifies communications failover, deadline-watchdog behavior, generic reference-profile contents, and runtime hard-fault latching to `SAFE_HOLD`. |
| `tests/test_pnt_backbone.py` | Verifies clock-domain normalization, timestamp uncertainty propagation, out-of-order rejection, unknown-clock fail-closed behavior, rejected-contract watermark safety, full-covariance normalized fusion, integrity veto behavior, full-rank nominal supervision, rich PNT output fields, and explicit absence of a validated protection bound. |

## `examples/`

| Path | Function |
| --- | --- |
| `examples/runtime_example.py` | Minimal executable integration example showing timebase initialization, 100 Hz preprocessed IMU prediction, asynchronous aiding updates, communications heartbeat selection, navigation status, and authority decision. Synthetic values are placeholders for validated adapters. |

## `docs/`

| Path | Function |
| --- | --- |
| `docs/ARCHITECTURE.md` | Technical subsystem architecture and data/control flow: sensor normalization, time alignment, estimator, source health/constraint coverage, integrity contract, mode supervision, PNT output, communications, and next ESKF/factor-graph/integrity gates. |
| `docs/GNSS_DENIAL.md` | Defines the active GNSS-denial engineering objective, how the current EKF stack behaves through outage/jamming, what it can reject, what spoofing/common-mode failures remain, and the staged validation path. |
| `docs/VALIDATION.md` | Summarizes current software evidence and explicitly separates software tests from recorded-data/HIL/water-trial evidence. |
| `docs/validation/TEST_RESULTS.txt` | Preserved validation snapshot from the pre-normalization package: 21 software tests passed and source/tests compiled. Historical software evidence only. |
| `docs/validation/PNT_BACKBONE_TEST_RESULTS.txt` | PNT-backbone scratch-validation snapshot: source/tests compiled and the 27-test repository inventory passed; records the no-runner GitHub Actions limitation and the software-only evidence boundary. |

## `.github/workflows/`

| Path | Function |
| --- | --- |
| `.github/workflows/ci.yml` | Clean-checkout CI definition: installs the package with test extras, compiles source/tests/examples, and runs pytest on Python 3.11. At the time of the PNT-backbone PR, GitHub jobs were failing before runner assignment, so the workflow status was not treated as code-test evidence. |

## Files intentionally removed during normalization

The uploaded repository had been flattened and accidentally included pytest cache state and Python bytecode. The following are generated/non-source artifacts and are intentionally not part of the normalized tree: root `*.pyc` files, `CACHEDIR.TAG`, `nodeids`, `lastfailed`, and `download`. `README (1).md` was folded into the authoritative root `README.md`; the prior root `README.md` was itself pytest cache documentation and was replaced.

## Architectural scope

AMEP's executable GitHub stack is the EKF-centered real-time navigation/supervision kernel plus the normalized time-alignment, integrity, and PNT-solution contracts listed above. The broader v1.0 research publication also discusses geometry verification, replay, radar/bathymetry topology operators, environmental route research, NMEA reference parsing, and adversarial benchmark artifacts. Those publication artifacts are not present in this GitHub repository at this commit and therefore are not represented here as implemented modules.

The new integrity layer does not close the published common-mode-bias failure or create a protection level. The next evidence gates remain calibrated INS preprocessing, real sensor/bus adapters, measured clock/frame calibration, explicit common-cause/FDE integrity logic, recorded-data replay, target-hardware timing, HIL, and controlled water trials.
