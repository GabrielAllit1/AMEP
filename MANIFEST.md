# Repository Manifest

This manifest describes every authoritative source, test, example, and project-support file in the AMEP repository after the September 2026 repository normalization.

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
| `src/amep1/__init__.py` | Public package surface. Re-exports the estimator, supervisors, policies, result types, watchdog, and reference-profile builder. |
| `src/amep1/estimator.py` | Core seven-state Extended Kalman Filter. Propagates `[E,N,Vw_E,Vw_N,C_E,C_N,psi]`, rotates leveled body acceleration into the local frame, propagates the full heading-sensitive Jacobian, applies chi-square NIS gates, computes Kalman gain by Cholesky solve, performs Joseph-form covariance updates, enforces PSD covariance, and exposes typed measurement helpers. |
| `src/amep1/config.py` | Immutable estimator and source-policy configuration. Defines process-noise coefficients, gate/containment probabilities, prediction time-step limits, covariance floor, freshness, isolation, rejection-window, and recovery thresholds. |
| `src/amep1/math_utils.py` | Numerical safety helpers: angle wrapping, covariance symmetrization, nearest-positive-semidefinite projection, and finite-value validation. |
| `src/amep1/types.py` | Dataclass contracts shared across modules. Defines validated horizontal IMU input, measurement results, constraint-coverage results, authority decisions, and structured navigation status. |
| `src/amep1/enums.py` | Enumerations for navigation mode, sensor health state, and command-authority source. |
| `src/amep1/health.py` | Per-source health state machine. Tracks freshness, repeated innovation rejection, sliding rejection fraction, manual isolation, probe-only recovery, and whether a source may currently fuse into the EKF. |
| `src/amep1/constraints.py` | Implements AMEP's deliberately limited local constraint-coverage heuristic. Maps healthy sensor classes to observed state indices and computes information rank/conditioning plus GNSS/non-GNSS absolute-source availability. It is not a formal nonlinear-observability proof. |
| `src/amep1/authority.py` | Navigation and command-authority supervisor. Converts constraint coverage into `NOMINAL`, `GPS_DENIED_RESILIENT`, `DEGRADED_DEAD_RECKONING`, or `SAFE_HOLD`, then enforces operator > autonomy > safety authority rules. |
| `src/amep1/comms.py` | Communications supervision. Registers command/telemetry links with priority and heartbeat-age policies and chooses the highest-priority healthy link deterministically. |
| `src/amep1/profile.py` | Builds the generic reference source profile used by examples/tests: GNSS, radar map fix, bathymetric map fix, visual map fix, speed log, ground velocity, current prior, and gyrocompass. Values are integration examples, not vessel-calibrated limits. |
| `src/amep1/runtime.py` | High-level integration façade. Couples EKF updates to source-health decisions, refreshes coverage, latches prediction/timebase faults into `SAFE_HOLD`, and returns structured navigation status. |
| `src/amep1/timing.py` | Host-SIL deadline watchdog for monotonic timestamps and missed-deadline detection. It does not establish target-hardware real-time guarantees. |

## `tests/` — software contracts

| Path | Function |
| --- | --- |
| `tests/test_estimator.py` | Verifies water/current ground-velocity semantics, finite-difference heading Jacobian terms, gravity-compensated IMU contract, monotonic time, maximum prediction gap, covariance reduction, outlier rejection, velocity/current/heading updates, and PSD covariance preservation. |
| `tests/test_supervision.py` | Verifies source isolation and recovery, stale transitions, reachable degraded mode, GNSS and non-GNSS full-rank navigation modes, low-rank `SAFE_HOLD`, and probe-only handling of isolated sources. |
| `tests/test_operations.py` | Verifies communications failover, deadline-watchdog behavior, generic reference-profile contents, and runtime hard-fault latching to `SAFE_HOLD`. |

## `examples/`

| Path | Function |
| --- | --- |
| `examples/runtime_example.py` | Minimal executable integration example showing timebase initialization, 100 Hz preprocessed IMU prediction, asynchronous aiding updates, communications heartbeat selection, navigation status, and authority decision. Synthetic values are placeholders for validated adapters. |

## `docs/`

| Path | Function |
| --- | --- |
| `docs/ARCHITECTURE.md` | Technical subsystem architecture and data/control flow, including estimator, integrity supervision, constraint coverage, navigation modes, communications, and authority. |
| `docs/GNSS_DENIAL.md` | Defines the active GNSS-denial engineering objective, how the current EKF stack behaves through outage/jamming, what it can reject, what spoofing/common-mode failures remain, and the staged validation path. |
| `docs/VALIDATION.md` | Summarizes current software evidence and explicitly separates software tests from recorded-data/HIL/water-trial evidence. |
| `docs/validation/TEST_RESULTS.txt` | Preserved validation snapshot from the pre-normalization package: 21 software tests passed and source/tests compiled. Historical software evidence only. |

## `.github/workflows/`

| Path | Function |
| --- | --- |
| `.github/workflows/ci.yml` | Clean-checkout CI: installs the package with test extras, compiles source/tests/examples, and runs pytest across supported Python versions. |

## Files intentionally removed during normalization

The uploaded repository had been flattened and accidentally included pytest cache state and Python bytecode. The following are generated/non-source artifacts and are intentionally not part of the normalized tree: root `*.pyc` files, `CACHEDIR.TAG`, `nodeids`, `lastfailed`, and `download`. `README (1).md` was folded into the authoritative root `README.md`; the prior root `README.md` was itself pytest cache documentation and was replaced.

## Architectural scope

AMEP's current executable stack is the EKF/supervision kernel above. The broader v1.0 research publication also discusses geometry verification, replay, radar/bathymetry topology operators, environmental route research, NMEA reference parsing, and adversarial benchmark artifacts. Those publication artifacts are not present in this GitHub repository at this commit and therefore are not represented here as implemented modules.
