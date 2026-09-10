# AMEP-1 — Adaptive Maritime Estimation and PNT

**Resilient multisensor navigation and autonomy-authority research for GNSS-degraded and GNSS-denied maritime operation.**

AMEP-1 is a platform-neutral research stack for uncrewed surface-vessel navigation when GNSS cannot be treated as continuously available or trustworthy. The implementation centers on a hardened seven-state Extended Kalman Filter (EKF), explicit measurement-consistency screening, sensor-health supervision, local constraint-coverage checks, navigation-mode degradation, and operator/autonomy/safety authority gating.

> **Maturity:** Research software / software-in-the-loop (SIL) prototype. AMEP is being engineered toward operation through active GNSS-denial zones, but this repository is not a certified PNT, integrity, collision-avoidance, or vessel-control product.

## Mission

GNSS denial should be treated as a navigation-information problem, not as a single-sensor replacement problem. AMEP is designed to keep an estimate alive when GNSS is absent or rejected by combining the information that remains available: preprocessed inertial motion, water-relative velocity, estimated surface current, heading, ground-velocity aids, and non-GNSS absolute fixes such as radar-, bathymetry-, or vision-derived map fixes.

The target architecture is:

```text
        GNSS ───────────────┐
        radar map fix ──────┤
        bathymetry fix ─────┤
        visual map fix ─────┤
        speed log / DVL ────┤
        current prior ──────┤──> EKF + innovation screening
        gyro / heading ─────┤          │
        leveled IMU ────────┘          v
                                  sensor health
                                       │
                                       v
                              constraint coverage
                                       │
                                       v
                         navigation mode / SAFE_HOLD
                                       │
                                       v
                       operator > autonomy > safety
```

## Estimator

The reference state is

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

where `E,N` are local horizontal position, `Vw` is water-relative velocity, `C` is estimated surface current, `psi` is heading, and ground velocity is `Vg = Vw + C`.

`AMEPFilter` uses nonlinear state propagation with the full heading Jacobian terms for the published horizontal acceleration rotation, covariance propagation, chi-square normalized-innovation gating, Cholesky-based solves, Joseph-form covariance updates, and positive-semidefinite covariance repair. The current implementation is intentionally compact and auditable; it is not a full strapdown INS mechanization.

The IMU contract is strict: `HorizontalIMUInput` accepts only leveled, gravity-compensated horizontal translational acceleration plus yaw rate. Raw accelerometer specific force must be processed by a calibrated attitude/INS front end before entering AMEP.

## GNSS-denial behavior

AMEP distinguishes availability loss from integrity failure.

**Jamming / outage:** when GNSS becomes stale or unavailable, the estimator continues propagation and can remain in `GPS_DENIED_RESILIENT` if the healthy non-GNSS constraint set still spans the reference state and includes a non-GNSS absolute-position source. With only partial constraints it degrades to `DEGRADED_DEAD_RECKONING`; insufficient coverage forces `SAFE_HOLD`.

**Grossly inconsistent measurements:** chi-square innovation screening can reject outliers and the health manager can isolate repeatedly inconsistent sources. Isolated sources are probe-only until recovery criteria are satisfied.

**Plausible spoofing / common-mode error:** this is not solved by an EKF alone. Mutually consistent biased sources can pass innovation checks. The published v1.0 evidence explicitly demonstrates this failure mode, so future denial-zone work must add source-dependence modeling, bias/fault hypotheses, independent cross-checks, and recorded-data validation rather than overclaiming the current gate.

See [`docs/GNSS_DENIAL.md`](docs/GNSS_DENIAL.md) for the engineering objective and evidence gates.

## Repository layout

```text
.
├── src/amep1/              # importable AMEP package
├── tests/                  # unit and integration contracts
├── examples/               # minimal integration examples
├── docs/                   # architecture, validation, denial-zone notes
├── .github/workflows/      # CI
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
| `estimator.py` | Seven-state EKF predict/update, NIS gating, Joseph covariance update, containment proxy |
| `health.py` | Freshness, rejection history, isolation, probe-only recovery |
| `constraints.py` | Local information-rank/constraint-coverage heuristic |
| `authority.py` | Navigation modes and operator/autonomy/safety authority policy |
| `comms.py` | Deterministic communications-link priority and freshness failover |
| `runtime.py` | Integration façade binding estimator, health, coverage, and supervisor |
| `profile.py` | Generic reference sensor policies and state constraints |
| `timing.py` | Host-SIL deadline watchdog |
| `types.py` | Typed input/result/status contracts |
| `config.py` | Estimator/process-noise/source policy configuration |

## Install and verify

```bash
python -m pip install -e '.[test]'
python -m compileall -q src tests examples
pytest
```

CI runs the package on supported Python versions from a clean checkout.

## Current evidence boundary

The software baseline has unit/integration coverage for EKF propagation and updates, covariance stability, gross-outlier rejection, source isolation/recovery, freshness, constraint-rank modes, communications failover, watchdog behavior, and fail-closed runtime behavior. The archived validation snapshot is under `docs/validation/`.

The following remain open before AMEP can legitimately be called deployable GNSS-denial navigation:

- recorded maritime replay with independently referenced truth;
- same-sensor conventional EKF/UKF comparisons under predeclared outage intervals;
- calibrated INS preprocessing, bias states, lever arms, boresight, datum and timing provenance;
- real radar/bathymetry/vision aiding adapters and vessel-bus validation;
- explicit spoofing/common-cause integrity architecture;
- target-hardware WCET, jitter, overload and watchdog evidence;
- HIL fault-injection campaigns and controlled water trials;
- cybersecurity, software-supply-chain assurance, and independent replication.

## Research release

AMEP-1 Version 1.0 research report: **Gabriel V. Allit, SALT19**  
Zenodo DOI: **10.5281/zenodo.22561851**

The paper's negative findings are part of the design contract: clean-condition superiority was not demonstrated, common-mode position bias defeated the current integrity assumptions, and the covariance-derived radius is not a certified protection level.

## Rights

Copyright © 2026 Gabriel V. Allit. All rights reserved. No license to deploy this software in safety-critical or operational navigation is granted by this repository.
