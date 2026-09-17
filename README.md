# AMEP-1 — Adaptive Maritime Estimation and PNT

**Resilient multisensor navigation and autonomy-authority research for GNSS-degraded and GNSS-denied operation.**

AMEP-1 combines a seven-state maritime reference estimator with explicit contracts for measurement timing, source dependencies, health, integrity, deterministic degradation, replay, and PNT output. The estimator interface is replaceable; the current maritime dynamics are not presented as universal vehicle dynamics.

> **Maturity:** Research software / software-in-the-loop (SIL) prototype. This repository is not a certified PNT, integrity, collision-avoidance, flight-control, vessel-control, or safety-of-life product.

**Project:** SALT19  
**Full-stack architect:** Gabriel V. Allit  
**AMEP-1 researcher / Version 1.0 author:** Gabriel V. Allit  
**Research DOI:** [10.5281/zenodo.22561851](https://doi.org/10.5281/zenodo.22561851)  
**Engineering wiki:** [`docs/wiki/README.md`](docs/wiki/README.md) — multidisciplinary system documentation for mechanical, electrical, navigation/PNT, communications/RF, embedded/real-time, controls/autonomy, software, verification, and safety engineers.

## Mission

GNSS denial is treated as a navigation-information and integrity problem rather than a single-sensor replacement problem. AMEP preserves source identity, timing, covariance, provenance, declared dependencies, health, integrity state, and navigation authority through the fusion path.

```text
PLATFORM-SPECIFIC SENSOR / BUS ADAPTERS
GNSS | IMU/INS | radar | vision/LiDAR | DVL/STW | alt-PNT | timing/RF health
                         |
                         v
                 MeasurementEnvelope
 source + values + covariance + frame + provenance
 source time + receive time + clock domain + uncertainty
                         |
                         v
                     TimeAligner
                         |
                         v
                    SourceRegistry
 role + failure domain + shared dependencies + safety-credit contract
             |                           |
             v                           v
 CrossSourceConsistency           EstimatorBackend
 pre-fusion contradiction         AMEPFilter today;
 evidence                         platform-specific backend later
             |                           |
             +-------------+-------------+
                           v
                  SensorHealthManager
                           |
                  ConstraintCoverage
                           |
                    IntegrityEngine
 health + rank + dependency diversity + conflicts + hard faults
                           |
                 NavigationSupervisor
 NOMINAL / GPS_DENIED_RESILIENT / DEGRADED_DEAD_RECKONING / SAFE_HOLD
                           |
                           v
                      PNTSolution
 frame + state schema + covariance labels + health + integrity + age

Delayed/asynchronous extension:
MeasurementEnvelope -> DelayedMeasurementBackend -> fixed-lag/FGO backend

Verification:
recorded events -> DeterministicReplay -> configuration-bound EvidenceLog
```

## Current maritime estimator

The reference state is:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

`AMEPFilter` implements nonlinear propagation, the heading-sensitive Jacobian, chi-square NIS screening, Cholesky solves, Joseph-form covariance updates, and PSD covariance repair. It is intentionally auditable and **is not a full strapdown INS**. `HorizontalIMUInput` accepts only leveled, gravity-compensated horizontal acceleration plus yaw rate; raw specific force belongs in a calibrated INS/ESKF front end.

`EstimatorBackend` is the portability seam. A replacement backend declares accepted measurement kinds and frames, owns its dynamics/state/observation models, accepts its own prediction-input type, and publishes an `EstimatorSnapshot` containing an explicit `state_schema_id` and ordered covariance labels.

`ConstraintCoverage` is state-dimension configurable. The maritime reference profile explicitly uses seven states; other platform integrations must supply their own state dimension and source-to-state constraint model.

## Time and measurement contract

`MeasurementEnvelope` preserves source identity, measurement kind, values, full covariance, frame, source timestamp, receive timestamp, clock domain, sequence, provenance, metadata, and timestamp uncertainty.

`TimeAligner` normalizes declared clock domains and rejects unknown clocks, excessive latency/age, excessive future skew, and out-of-order data. Runtime ingestion uses a two-phase align/commit path so rejected contracts cannot advance a source ordering watermark.

The conservative research reference runtime requires registered sources and disables legacy direct measurement helpers. Its normalized input path consumes local-ENU position, water velocity, ground velocity, current prior, and heading observations. Real GNSS, radar, camera/LiDAR, DVL/STW, RF-health, timing, and vehicle-bus adapters remain integration work.

## Dependency-aware integrity

AMEP v1.0 showed why estimator consistency alone is insufficient: mutually consistent biased absolute sources can remain plausible while the state is wrong and covariance is overconfident. The current architecture therefore separates **health** from **independence**.

`SourceRegistry` declares source role, primary failure domain, optional shared dependency tokens, clock expectations, provenance requirements, timestamp-uncertainty limits, and whether the integration grants safety credit.

Safety credit is opt-in. A safety-credit source must require provenance and declare a finite timestamp-uncertainty limit. The bundled research reference profile intentionally grants no source safety credit because no vehicle-specific dependency analysis, adapter provenance contract, or timing budget has been validated in this repository.

`CrossSourceConsistencyMonitor` checks near-synchronous same-frame absolute observations from dependency-disjoint source chains before fusion. A contradiction prevents the disputed candidate from mutating the estimator and latches integrity to `ALERT`. Two-source disagreement is not automatically attributed to either source.

`NavigationSupervisor` cannot grant `GPS_DENIED_RESILIENT` from full state rank alone. The supplied `IntegrityReport` must explicitly permit resilient navigation. Under the default integrity policy, that permission requires at least two ONLINE non-GNSS absolute sources with safety credit whose declared integrity-dependency sets are pairwise disjoint.

Full non-GNSS state coverage without sufficient integrity evidence remains `DEGRADED_DEAD_RECKONING`.

## Protection-bound boundary

The current PNT solution deliberately reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

It also exposes `containment_probability` and `horizontal_containment_proxy_m`. The proxy is a covariance-derived diagnostic quantity whose probability is explicit and configurable; it is not a protection level. The archived v1.0 correlated-common-bias experiment showed nominal 95% containment collapsing to roughly 8.7%, so covariance is not renamed as integrity.

## Deterministic replay and evidence

Measurement replay is ordered by recorded receive time plus explicit sequence, not raw source timestamp. Source timestamps remain inside each envelope and are normalized by the same `TimeAligner` used online, which avoids incorrect global ordering across different clock domains.

Replay reports contract rejection, ingest acceptance, estimator acceptance, estimator rejection, and actual fusion separately.

`EvidenceLog` creates a canonical SHA-256 hash chain. Replay configuration is bound to behavior-affecting runtime configuration, source declarations, estimator configuration, time/health/integrity/navigation policies, software-tree identity, Python runtime, and key dependency versions.

This is deterministic software tamper-evidence, not a digital signature, trusted clock, secure logger, or certification artifact.

## Core modules

| Module | Responsibility |
| --- | --- |
| `backend.py` | Replaceable real-time estimator protocol, schema-labeled snapshot, delayed-measurement seam |
| `time_alignment.py` | Measurement envelope, clock domains, source/receive time, uncertainty, latency/age/order checks |
| `source_registry.py` | Source roles, failure domains, shared dependencies, conservative safety-credit contract |
| `consistency.py` | Pre-fusion cross-source absolute-position consistency checks |
| `estimator.py` | Current seven-state maritime EKF backend |
| `health.py` | Freshness, rejection history, isolation, probe-only recovery, age-of-data |
| `constraints.py` | Configurable-dimension local information-rank heuristic; not formal observability |
| `integrity.py` | Dependency-aware integrity state and resilient-navigation permission; no validated protection level |
| `authority.py` | Integrity-aware navigation modes and operator/autonomy/safety authority policy |
| `solution.py` | Frame/schema-explicit PNT output with covariance labels, health/age, and integrity state |
| `replay.py` | Receive-order deterministic replay through the online runtime |
| `evidence.py` | Canonical hash-chained software evidence and configuration fingerprints |
| `runtime.py` | Integration façade binding alignment, source contracts, consistency, estimator, health, coverage, integrity, and output |
| `comms.py` | Link-priority/freshness support with invalid/future-time rejection |
| `profile.py` | Research source policies, conservative dependency declarations, and normalized reference runtime |
| `timing.py` | Host-SIL deadline observer with invalid-time rejection |

## Install and verify

```bash
python -m pip install -e '.[test,qa]'
python -m compileall -q src tests examples
python -m ruff check src tests examples
python -m mypy src/amep1
python -m bandit -q -r src/amep1
python -m pytest --cov=amep1 --cov-report=term-missing --cov-fail-under=75
```

CI runs on the repository-specific self-hosted Windows runner and also audits direct runtime dependencies and generates a CycloneDX SBOM artifact. A passing CI run is software evidence only; it is not field or safety evidence.

## Production-hardening gates

The engineering baseline and remaining gates are documented in [`docs/PRODUCTION_HARDENING_2026.md`](docs/PRODUCTION_HARDENING_2026.md). Major unresolved gates include:

- recorded real multisensor replay with independent truth and frozen fault/outage windows;
- calibrated strapdown INS/ESKF with inertial bias states and explicit frame/gravity conventions;
- measured clock synchronization, latency, lever-arm, boresight, datum, and calibration uncertainty;
- real radar/bathymetry/vision/LiDAR/DVL/GNSS-RF-health and bus adapters;
- architecture-derived fault hypotheses, FDE/solution separation, and empirical integrity-risk characterization;
- target-hardware WCET/jitter/overload/watchdog evidence;
- HIL fault injection and controlled water trials;
- reproducible dependency locking, signed releases, and independent replay of material findings.

A fixed-lag smoother or factor graph is an optional delayed/asynchronous backend, not a reason to remove the deterministic real-time estimator.

## Research release

AMEP-1 Version 1.0 research report: **Gabriel V. Allit, SALT19**  
Zenodo DOI: **10.5281/zenodo.22561851**

The paper's negative findings remain part of the design contract: clean-condition superiority was not demonstrated, common-mode position bias defeated the original integrity assumptions, and the covariance-derived radius is not a certified protection level. Current implementation work does not rewrite the historical evidence.

## Rights and use boundary

Copyright © 2026 Gabriel V. Allit. All rights reserved. No license to deploy this software in safety-critical or operational navigation is granted by this repository. This architecture work is limited to navigation, estimation, integrity, timing, modular interfaces, replay, degradation, and assurance; it does not implement autonomous targeting or weapon-employment functions.
