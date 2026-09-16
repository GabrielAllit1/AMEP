# AMEP-1 — Adaptive Maritime Estimation and PNT

**Resilient multisensor navigation and autonomy-authority research for GNSS-degraded and GNSS-denied operation.**

AMEP-1 is a maritime research implementation plus a growing set of portable PNT/integrity contracts. The current estimator is a seven-state USV-oriented horizontal EKF; the surrounding measurement, timing, source-dependency, integrity, replay, authority and output interfaces are being designed so platform-specific estimators and adapters can replace the maritime kernel without duplicating the assurance stack.

> **Maturity:** Research software / software-in-the-loop (SIL) prototype. This repository is not a certified PNT, integrity, collision-avoidance, flight-control, vessel-control, or safety-of-life product.

## Mission

GNSS denial should be treated as a navigation-information and integrity problem, not as a single-sensor replacement problem. AMEP combines dissimilar information while preserving source identity, timing, covariance, provenance, declared dependencies, health, integrity state, and navigation authority.

```text
PLATFORM-SPECIFIC ADAPTERS
GNSS | IMU/INS | radar | vision/LiDAR | DVL/STW | alt-PNT | time/RF health
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
 role + primary failure domain + shared dependencies + safety credit
             |                           |
             v                           v
 CrossSourceConsistency           EstimatorBackend
 independent absolute             AMEPFilter today
 evidence before fusion           platform-specific later
             |                           |
             +-------------+-------------+
                           v
                  SensorHealthManager
                           |
                  ConstraintCoverage
                           |
                    IntegrityEngine
 dependency diversity + conflicts + health + rank + evidence boundary
                           |
                 NavigationSupervisor
 NOMINAL / GPS_DENIED_RESILIENT / DEGRADED_DEAD_RECKONING / SAFE_HOLD
                           |
                           v
                      PNTSolution

Parallel future path:
MeasurementEnvelope -> DelayedMeasurementBackend -> fixed-lag/FGO corrections

Verification path:
ReplayEvent -> DeterministicReplay -> hash-chained EvidenceLog
```

## Current maritime estimator

The reference state remains:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

`AMEPFilter` implements nonlinear propagation, the heading-sensitive Jacobian, chi-square NIS screening, Cholesky solves, Joseph-form covariance updates, and PSD covariance repair. It is intentionally auditable and **is not a full strapdown INS**. `HorizontalIMUInput` accepts only leveled, gravity-compensated horizontal acceleration plus yaw rate; raw specific force belongs in a calibrated INS/ESKF front end.

`EstimatorBackend` is the portability seam. A future USV ESKF, UUV estimator, UAV navigation filter, UGV estimator, or invariant formulation must satisfy the runtime contract and earn its own replay/HIL/field evidence. The present water-current state model is not relabeled as universal vehicle dynamics.

## Time and measurement contract

`MeasurementEnvelope` preserves source identity, measurement kind, values, full covariance, frame, source timestamp, receive timestamp, clock domain, sequence, provenance, metadata, and timestamp uncertainty.

`TimeAligner` normalizes declared clock domains and rejects unknown clocks, excessive latency/age, future skew, and out-of-order data. Runtime ingestion uses a two-phase align/commit path so rejected packets cannot poison the ordering watermark. The deterministic real-time estimator intentionally does not rewind; delayed measurements have a separate `DelayedMeasurementBackend` seam for future fixed-lag/factor-graph processing.

The assured normalized path currently consumes local-ENU position, water velocity, ground velocity, current priors, and heading. Real GNSS, radar, camera/LiDAR, DVL/STW, RF-health, timing and vehicle-bus adapters remain integration work.

## Dependency-aware integrity

AMEP v1.0 showed why estimator consistency alone is insufficient: mutually consistent biased absolute sources can remain plausible while the state is wrong and covariance is overconfident. The current architecture therefore separates **health** from **independence**.

`SourceRegistry` declares a source's role, primary failure domain, optional shared dependency tokens, clock expectations, provenance requirements and whether the source receives safety credit. Shared dependencies can represent common clocks, maps, preprocessing services, receiver chains or other common causes. These declarations prevent differently named sensors from automatically receiving independent-source credit.

`CrossSourceConsistencyMonitor` compares near-synchronous absolute position fixes from declared dependency-disjoint source chains before fusion. A contradiction is rejected before estimator mutation and latches integrity to `ALERT`; two-source disagreement is not automatically attributed to either source because fault attribution is underdetermined.

`IntegrityEngine` reports `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT`. For the reference policy, full 7/7 non-GNSS state coverage is **not enough** for `GPS_DENIED_RESILIENT`: at least two ONLINE non-GNSS absolute sources must form a pairwise dependency-disjoint set. Otherwise the mode is downgraded to `DEGRADED_DEAD_RECKONING` rather than overstating resilience.

Failure-domain declarations are an engineering model, not proof of independence. A real integration must derive them from its actual RF, clock, map, calibration, power, compute, network and preprocessing architecture.

## Protection-bound boundary

The current PNT solution deliberately reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

The covariance-derived 95% containment proxy remains diagnostic only. The archived v1.0 correlated-common-bias experiment showed nominal 95% containment collapsing to roughly 8.7%, so this repository does not rename covariance as a protection level.

## Deterministic evidence and replay

`DeterministicReplay` orders events by `(timestamp, sequence)` and drives the same runtime used online. `EvidenceLog` creates a canonical SHA-256 hash chain over replay configuration, events and final solution. Replay configuration includes the source-registry fingerprint, binding results to the declared dependency model.

This is deterministic tamper-evidence for software experiments—not a digital signature, trusted clock, secure audit appliance, or operational certification artifact.

## Core modules

| Module | Responsibility |
| --- | --- |
| `backend.py` | Portable real-time estimator protocol plus delayed-measurement backend seam |
| `time_alignment.py` | Measurement envelope, source/receive time, clock domains, uncertainty, latency/age/order checks |
| `source_registry.py` | Source roles, failure domains, shared dependencies, safety credit, deterministic configuration fingerprint |
| `consistency.py` | Pre-fusion cross-source absolute consistency evidence |
| `estimator.py` | Current seven-state maritime EKF |
| `health.py` | Freshness, rejection history, isolation, probe-only recovery, source age |
| `constraints.py` | Local information-rank/constraint-coverage heuristic; not formal observability |
| `integrity.py` | Dependency-aware integrity state and resilient-mode permission; no certified protection level |
| `authority.py` | Integrity-aware navigation modes and operator/autonomy/safety authority policy |
| `solution.py` | PNT output with covariance, health/age, integrity state and explicit unsupported fields |
| `replay.py` | Deterministic event replay through the online runtime |
| `evidence.py` | Canonical hash-chained software evidence records |
| `runtime.py` | Integration façade binding alignment, consistency, estimator, health, coverage, integrity and PNT output |
| `comms.py` | Deterministic communications-link freshness/priority supervision |
| `profile.py` | Reference source policies, dependency declarations and fully wired reference runtime |
| `timing.py` | Host-SIL deadline watchdog |

## Install and verify

```bash
python -m pip install -e '.[test]'
python -m compileall -q src tests examples
pytest
```

The repository's GitHub Actions jobs have previously failed before runner assignment, so a red workflow with zero executed steps is infrastructure state, not test evidence. Validation results for each hardening tranche are recorded separately under `docs/validation/` when executable validation is available.

## Production-hardening plan

The detailed research/standards review and prioritized production gates are in [`docs/PRODUCTION_HARDENING_2026.md`](docs/PRODUCTION_HARDENING_2026.md). The next major technical gates are:

- recorded real multisensor replay with independently referenced truth and frozen fault/outage windows;
- calibrated strapdown INS/ESKF preprocessing with inertial bias states and explicit frame/gravity conventions;
- measured clock synchronization, latency, lever-arm, boresight and datum uncertainty;
- real radar/bathymetry/vision/LiDAR/DVL/GNSS-RF-health and bus adapters;
- dependency-derived multi-hypothesis FDE and empirically calibrated integrity bounds;
- target-hardware WCET/jitter/overload/watchdog evidence;
- HIL fault-injection campaigns and controlled field/water trials;
- secure-development, SBOM, dependency-locking, signed-release and independent-replication evidence.

A factor graph or fixed-lag smoother is a candidate asynchronous/replay/calibration backend, not a reason to remove the deterministic real-time estimator.

## Research release

AMEP-1 Version 1.0 research report: **Gabriel V. Allit, SALT19**  
Zenodo DOI: **10.5281/zenodo.22561851**

The paper's negative findings remain part of the design contract: clean-condition superiority was not demonstrated, common-mode position bias defeated the current integrity assumptions, and the covariance-derived radius is not a certified protection level. Current GitHub work may close implementation gaps, but the historical release and its evidence are not rewritten retroactively.

## Rights and use boundary

Copyright © 2026 Gabriel V. Allit. All rights reserved. No license to deploy this software in safety-critical or operational navigation is granted by this repository. This architecture work is limited to navigation, estimation, integrity, timing, modular interfaces, replay, degradation and assurance; it does not implement autonomous targeting or weapon-employment functions.
