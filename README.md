# AMEP-1 — Adaptive Maritime Estimation and PNT

**Resilient multisensor navigation and autonomy-authority research for GNSS-degraded and GNSS-denied maritime operation.**

AMEP-1 is a platform-neutral research stack for uncrewed surface-vessel navigation when GNSS cannot be treated as continuously available or trustworthy. The implementation centers on a hardened seven-state Extended Kalman Filter (EKF), explicit measurement/time contracts, innovation-consistency screening, sensor-health supervision, local constraint-coverage checks, an integrity contract, navigation-mode degradation, and operator/autonomy/safety authority gating.

> **Maturity:** Research software / software-in-the-loop (SIL) prototype. AMEP is being engineered toward operation through active GNSS-denial zones, but this repository is not a certified PNT, integrity, collision-avoidance, or vessel-control product.

## Mission

GNSS denial should be treated as a navigation-information problem, not as a single-sensor replacement problem. AMEP is designed to keep an estimate alive when GNSS is absent or rejected by combining the information that remains available: preprocessed inertial motion, water-relative velocity, estimated surface current, heading, ground-velocity aids, and non-GNSS absolute fixes such as radar-, bathymetry-, or vision-derived map fixes.

The current target architecture is:

```text
GNSS / GPS ─┐
IMU ────────┤
Radar ──────┤
DVL / STW ──┤
Vision/LiDAR┤
Alt-PNT ────┘
      │
      v
MeasurementEnvelope
source + values + covariance + frame
source/receive timestamps + clock domain
provenance + timestamp uncertainty
      │
      v
TimeAligner
clock normalization / latency / age / order
      │
      v
AMEPFilter (EKF)
      │
innovation / NIS / acceptance
      │
      v
SensorHealthManager + ConstraintCoverage
      │
      v
IntegrityEngine
      │
      v
NavigationSupervisor
NOMINAL / GPS_DENIED_RESILIENT /
DEGRADED_DEAD_RECKONING / SAFE_HOLD
      │
      v
PNTSolution
position + velocity + heading + covariance
source health + age + integrity state
containment proxy + protection-bound availability
```

## Estimator

The reference state is

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

where `E,N` are local horizontal position, `Vw` is water-relative velocity, `C` is estimated surface current, `psi` is heading, and ground velocity is `Vg = Vw + C`.

`AMEPFilter` uses nonlinear state propagation with the full heading Jacobian terms for the published horizontal acceleration rotation, covariance propagation, chi-square normalized-innovation gating, Cholesky-based solves, Joseph-form covariance updates, and positive-semidefinite covariance repair. The current implementation is intentionally compact and auditable; it is not a full strapdown INS mechanization.

The IMU contract is strict: `HorizontalIMUInput` accepts only leveled, gravity-compensated horizontal translational acceleration plus yaw rate. Raw accelerometer specific force must be processed by a calibrated attitude/INS front end before entering AMEP.

## Measurement and time contract

`MeasurementEnvelope` is the normalized boundary between sensor adapters and estimator fusion. It preserves source identity, measurement kind, values, full measurement covariance, coordinate frame, source timestamp, receive timestamp, clock domain, provenance, and timestamp uncertainty.

`TimeAligner` currently performs explicit clock-domain normalization and rejects unknown clock domains, excessive latency/age, future-dated measurements beyond tolerance, and out-of-order measurements. Runtime ingestion uses a two-phase align/commit path so a malformed frame or measurement contract cannot poison the source-ordering watermark. The current real-time EKF does not rewind for delayed measurements; a future fixed-lag smoother or factor graph can consume the same envelope without silently changing the real-time estimator contract.

The normalized runtime currently accepts local-ENU position, water velocity, ground velocity, current prior, and heading measurements. Raw GNSS, radar, camera/LiDAR, DVL/STW, RF-health, and vessel-bus interfaces still require real calibrated adapters.

## Integrity and GNSS-denial behavior

AMEP distinguishes availability loss from integrity failure.

**Jamming / outage:** when GNSS becomes stale or unavailable, the estimator continues propagation and can remain in `GPS_DENIED_RESILIENT` if the healthy non-GNSS constraint set still spans the reference state and includes a non-GNSS absolute-position source. With only partial constraints it degrades to `DEGRADED_DEAD_RECKONING`; insufficient coverage forces `SAFE_HOLD`.

**Grossly inconsistent measurements:** chi-square innovation screening can reject outliers and the health manager can isolate repeatedly inconsistent sources. Isolated sources are probe-only until recovery criteria are satisfied.

**Plausible spoofing / common-mode error:** this is not solved by an EKF or NIS gate alone. Mutually consistent biased sources can pass innovation checks. The published v1.0 evidence explicitly demonstrates this failure mode.

`IntegrityEngine` now gives this concern an explicit runtime contract. It can report `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT` and can veto normal navigation authority. It is not certified RAIM/FDE and does not claim a validated protection level.

The current PNT solution deliberately reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

The covariance-derived containment proxy remains a diagnostic only because the v1.0 correlated-common-bias experiment showed that it can be severely overconfident.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detailed subsystem contracts and [`docs/GNSS_DENIAL.md`](docs/GNSS_DENIAL.md) for the engineering objective and evidence gates.

## Repository layout

```text
.
├── src/amep1/              # importable AMEP package
├── tests/                  # unit and integration contracts
├── examples/               # minimal integration examples
├── docs/                   # architecture, validation, denial-zone notes
├── .github/workflows/      # CI definition
├── MANIFEST.md             # file-by-file repository map
├── pyproject.toml          # package/build/test metadata
├── CONTRIBUTING.md         # engineering workflow
├── SECURITY.md             # security and safety reporting
└── CITATION.cff            # research citation metadata
```

The complete file-by-file description is in [`MANIFEST.md`](MANIFEST.md).

## Core modules

| Module | Responsibility |
| --- | --- |
| `time_alignment.py` | Measurement envelope, source/receive timestamps, clock domains, timestamp uncertainty, latency/age/order checks |
| `estimator.py` | Seven-state EKF predict/update, NIS gating, Joseph covariance update, containment proxy |
| `health.py` | Freshness, rejection history, isolation, probe-only recovery, source age |
| `constraints.py` | Local information-rank/constraint-coverage heuristic |
| `integrity.py` | Explicit integrity status, navigation permission, and protection-bound availability contract |
| `authority.py` | Integrity-aware navigation modes and operator/autonomy/safety authority policy |
| `solution.py` | Rich PNT output with state covariance, source health/age, integrity state, and evidence-bounded unsupported fields |
| `runtime.py` | Integration façade binding alignment, estimator, health, coverage, integrity, mode supervision, and PNT output |
| `comms.py` | Deterministic communications-link priority and freshness failover |
| `profile.py` | Generic reference sensor policies and state constraints |
| `timing.py` | Host-SIL deadline watchdog |
| `types.py` | Shared typed input/result/status contracts |
| `config.py` | Estimator/process-noise/source policy configuration |

## Install and verify

```bash
python -m pip install -e '.[test]'
python -m compileall -q src tests examples
pytest
```

The repository includes a GitHub Actions definition for Python 3.11. At the time of the PNT-backbone integration, GitHub jobs were failing before runner assignment, so those workflow failures are infrastructure state rather than executed test failures. The branch was separately reconstructed in a scratch Python environment and the source compiled with the full repository test inventory passing 27/27; this is software validation only, not operational PNT evidence.

## Current evidence boundary

The software baseline has unit/integration coverage for EKF propagation and updates, covariance stability, gross-outlier rejection, source isolation/recovery, freshness, constraint-rank modes, communications failover, watchdog behavior, fail-closed runtime behavior, clock-domain normalization, out-of-order rejection, two-phase source-time watermarking, full-covariance normalized measurement ingestion, explicit integrity veto, and rich PNT output semantics.

The following remain open before AMEP can legitimately be called deployable GNSS-denial navigation:

- recorded maritime replay with independently referenced truth;
- same-sensor conventional EKF/UKF comparisons under predeclared outage intervals;
- calibrated strapdown INS/ESKF preprocessing, bias states, lever arms, boresight, datum and measured timing provenance;
- real radar/bathymetry/vision/LiDAR/DVL/GNSS-RF-health aiding adapters and vessel-bus validation;
- explicit common-cause source-dependence modeling, fault detection/exclusion, and defensible protection/integrity bounds;
- target-hardware WCET, jitter, overload and watchdog evidence;
- HIL fault-injection campaigns and controlled water trials;
- cybersecurity, software-supply-chain assurance, and independent replication.

A factor graph or fixed-lag smoother is an optional future asynchronous/replay/calibration backend, not a reason to replace the deterministic real-time EKF by default.

## Research release

AMEP-1 Version 1.0 research report: **Gabriel V. Allit, SALT19**  
Zenodo DOI: **10.5281/zenodo.22561851**

The paper's negative findings remain part of the design contract: clean-condition superiority was not demonstrated, common-mode position bias defeated the current integrity assumptions, and the covariance-derived radius is not a certified protection level. The current GitHub code may evolve beyond individual implementation limitations documented in the archived v1.0 release; the historical release and its evidence are not rewritten retroactively.

## Rights

Copyright © 2026 Gabriel V. Allit. All rights reserved. No license to deploy this software in safety-critical or operational navigation is granted by this repository.
