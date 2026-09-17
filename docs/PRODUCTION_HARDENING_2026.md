# AMEP Production-Hardening Baseline — September 2026

This document records the engineering rationale, implemented hardening contracts, and remaining evidence gates for AMEP-1. The executable reference estimator remains a horizontal maritime research model. The surrounding timing, source-dependency, integrity, replay, and output interfaces are intended to support replacement estimator backends without asserting that one vehicle dynamics model is universal.

## 1. Scope and evidence boundary

AMEP currently addresses:

- navigation estimation;
- measurement and time provenance;
- source health and dependency declarations;
- cross-source consistency;
- navigation-integrity state;
- deterministic degradation and authority gating;
- replay and software evidence;
- replaceable estimator interfaces.

It does not establish certified PNT integrity, validated protection levels, operational vessel safety, collision avoidance, target-hardware real-time guarantees, or field performance under active jamming/spoofing.

The current reference estimator is:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

That state definition is maritime and horizontal. `EstimatorBackend` is the portability boundary; a replacement backend owns its state dimension, prediction input, observation models, accepted frames, covariance schema, and estimator-specific validation evidence.

## 2. Engineering rationale

### 2.1 Integrity is separate from estimation accuracy

Robust navigation requires both a state estimate and evidence about whether that estimate can be trusted for the intended mode. NIS, covariance, source freshness, and estimator convergence are useful inputs but are not by themselves an integrity argument.

AMEP therefore keeps source health, source dependency assumptions, pre-fusion consistency, integrity state, and navigation authority outside the estimator implementation.

### 2.2 Common-cause faults invalidate naive sensor counting

AMEP v1.0 demonstrated severe covariance overconfidence under correlated common-mode absolute-position bias. Multiple named sources can share a receiver chain, RF environment, clock, map, calibration, preprocessing service, compute process, network, or power domain.

The hardened source model therefore includes:

- a primary failure domain;
- optional shared dependency tokens;
- clock-domain expectations;
- provenance requirements;
- timestamp-uncertainty limits;
- explicit opt-in safety credit.

Two sources are not treated as independent merely because they have different names.

### 2.3 Timing must survive interface boundaries

`MeasurementEnvelope` preserves source time, receive time, clock domain, timestamp uncertainty, sequence, provenance, frame, covariance, and metadata. `TimeAligner` validates and normalizes timing before estimator fusion.

Replay reproduces measurement processing in recorded receive-time order. Source timestamps are normalized by the same online time-alignment path rather than being used directly as a global ordering key.

### 2.4 Portable interfaces must not expose one estimator's state layout

Runtime consumes semantic measurements and `EstimatorSnapshot`; it does not build seven-state observation matrices. `ConstraintCoverage` accepts a configurable state dimension, and estimator snapshots publish a `state_schema_id` plus ordered covariance labels.

This supports alternate backends without implying that the current USV state model is suitable for UUV, UAV, UGV, or other platforms.

### 2.5 Software evidence must bind behavior-affecting configuration

Replay evidence is tied to a deterministic configuration fingerprint that includes:

- software-tree identity;
- Python and key dependency versions;
- estimator type and estimator configuration;
- health policies;
- constraint-coverage configuration;
- source-registry declarations and fingerprint;
- time-alignment policy and clock domains;
- integrity policy;
- cross-source consistency policy;
- navigation policy;
- runtime policy.

The evidence log is hash chained for deterministic tamper evidence. It is not a digital signature, secure logger, trusted clock, or certification artifact.

## 3. Current hardened architecture

```text
PLATFORM-SPECIFIC SENSOR / BUS ADAPTERS
GNSS | IMU/INS | radar | camera/LiDAR | DVL/STW | alt-PNT | timing/RF health
                         |
                         v
                 MeasurementEnvelope
 kind + values + covariance + frame + provenance
 source time + receive time + clock domain + uncertainty
                         |
                         v
                     TimeAligner
                         |
                         v
                    SourceRegistry
 role + failure domain + shared dependencies + safety-credit contract
               |                              |
               v                              v
 CrossSourceConsistency                 EstimatorBackend
 pre-fusion contradiction               backend-owned state,
 evidence                               frames and observation models
               |                              |
               +---------------+--------------+
                               v
                      SensorHealthManager
                               |
                      ConstraintCoverage
                               |
                        IntegrityEngine
 health + rank + dependency diversity + contradictions + hard faults
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

## 4. Implemented hardening requirements

### R1 — normalized ingestion is the research reference path

`build_research_reference_runtime()` disables legacy direct measurement updates and requires registered source descriptors. Measurements must traverse time alignment, source-contract checks, pre-fusion consistency, estimator update, health accounting, integrity evaluation, and mode supervision.

### R2 — safety credit is opt-in

`SourceDescriptor.safety_credit` defaults to `False`. A safety-credit source must require provenance and declare a finite timestamp-uncertainty limit. The bundled research reference profile grants no source safety credit because the repository does not contain a validated vehicle-specific dependency analysis or adapter timing contract.

### R3 — non-GNSS resilient mode requires integrity permission

`NavigationSupervisor` cannot grant `GPS_DENIED_RESILIENT` from full state rank alone. The caller must provide an `IntegrityReport` that explicitly permits resilient navigation. The default integrity policy requires at least two ONLINE non-GNSS absolute sources with safety credit whose declared integrity-dependency sets are pairwise disjoint.

### R4 — cross-source contradiction is evaluated before fusion

Near-synchronous same-frame absolute-position observations from dependency-disjoint source chains are checked before estimator mutation. A contradiction prevents the disputed candidate from being fused and latches integrity to `ALERT`. Two-source disagreement does not auto-identify the faulty source.

### R5 — estimator-local covariance is not a protection level

`PNTSolution` exposes a configurable-probability horizontal containment proxy as a diagnostic quantity. It also explicitly reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

No protection-level claim is made without a declared integrity-risk model and validation evidence.

### R6 — covariance is schema-labeled

Every estimator snapshot carries `state_schema_id` and ordered `covariance_labels`. A replacement backend cannot expose an unlabeled covariance matrix through the portable PNT contract.

### R7 — replay order matches online arrival order

Measurement replay is sorted by recorded receive time plus explicit sequence, not raw source timestamp. Contract rejection, estimator rejection, estimator acceptance, and actual fusion are counted separately.

### R8 — evidence fingerprints behavior-affecting configuration

The replay configuration hash includes estimator, timing, health, coverage, dependency, integrity, consistency, navigation, runtime, software-tree, and dependency-version information rather than only a source-registry hash.

### R9 — communications/timing support rejects invalid time behavior

Communications heartbeat handling rejects non-finite and non-monotonic timestamps, and future-dated heartbeats are not considered healthy. The host deadline observer rejects non-finite/non-monotonic observations and does not let invalid samples corrupt the last valid timing reference.

### R10 — software verification runs on the dedicated self-hosted runner

The AMEP GitHub Actions workflow targets the repository-specific Windows runner and validates a clean PR checkout. The workflow uses the already installed Python runtime on the self-hosted machine rather than attempting hosted-runner tool-cache installation.

## 5. Remaining engineering and evidence gates

### P0 — required before an operational navigation claim

- recorded real multisensor replay with independently referenced truth and predeclared fault/outage intervals;
- measured source timestamp provenance, synchronization uncertainty, and transport latency;
- lever-arm, boresight, datum, frame, and calibration procedures with quantified uncertainty;
- real bus/transport adapters with corruption, disconnect/reconnect, stale/frozen data, restart, and latency testing;
- target-hardware WCET, jitter, CPU/memory saturation, overload, and watchdog-response evidence;
- HIL fault injection for dropout, frozen data, clock skew, frame mistakes, gross faults, slow bias, shared-map faults, and common-cause faults;
- controlled water trials with independent truth, safety observers, abort criteria, and complete logs.

### P1 — calibrated inertial mechanization

Implement and evaluate a separate strapdown INS/ESKF backend rather than feeding raw accelerometer specific force into the seven-state maritime filter. A production-facing inertial state will normally require position, velocity, attitude, gyro bias, and accelerometer bias at minimum, with explicit Earth/gravity/frame conventions and sensor calibration.

Invariant-filter formulations are comparison candidates, not automatic upgrades.

### P2 — architecture-derived FDE and integrity bounds

Required work includes:

- a reviewed source-dependency/common-cause graph;
- fault hypotheses derived from the actual platform architecture;
- solution separation, multi-hypothesis testing, or an equivalent FDE mechanism appropriate to the measurement set;
- false-alert, missed-detection, and time-to-alert metrics;
- non-Gaussian/heavy-tail sensitivity;
- explicit common-cause hypotheses;
- a protection/integrity bound only after a declared risk allocation and empirical validation against independent truth.

### P3 — delayed/asynchronous estimation

Add a fixed-lag or factor-graph backend for delayed radar, vision, bathymetry, calibration, and replay workloads. Keep the deterministic low-latency estimator independently runnable so optimizer latency or failure cannot silently remove real-time navigation.

### P4 — platform profiles

Each platform profile should bind:

- estimator backend and prediction-input contract;
- state schema and covariance labels;
- accepted frame/datum definitions;
- source registry and dependency model;
- source safety-credit decisions;
- clock synchronization profile;
- sensor/bus adapters;
- constraint/observability model;
- integrity/navigation policy;
- performance and integrity requirements;
- safe-state behavior.

USV, UUV, UAV, and UGV integrations may share envelope, timing, dependency, replay, evidence, and authority contracts while using different estimator dynamics and state models.

### P5 — software and supply-chain assurance

The CI baseline should continue to enforce:

- compilation and unit/integration tests;
- coverage threshold;
- linting;
- static type checking;
- static security scanning;
- runtime dependency vulnerability auditing;
- CycloneDX SBOM generation;
- immutable/tagged release evidence when formal releases are produced.

Future work should add reproducible dependency locking, signed releases, NIST SSDF traceability, vulnerability-response procedures, and independent replay of material positive and negative findings.

## 6. External review evidence package

An external engineering review should be based on reproducible artifacts rather than broad capability claims. The minimum useful package is:

1. frozen source/vehicle profile, coordinate frames, calibration identity, and dependency graph;
2. executable code and exact software/configuration fingerprint;
3. deterministic replay with matching event/configuration hashes on a second environment;
4. same-sensor estimator comparisons without privileged preprocessing;
5. common-cause challenges demonstrating that shared dependencies do not receive false independence credit;
6. target-compute timing/resource measurements;
7. HIL and water/field evidence with traceable requirements, failure logs, and abort criteria;
8. PNT output that states supported quantities, unavailable quantities, integrity status, and the reason a navigation mode is or is not authorized.

## 7. Research and standards references

- Stanford NAV Lab, Robust Navigation and Sensor Fusion: https://navlab.stanford.edu/research/robust-sensor-fusion
- Stanford GPS Lab, RAIM: https://gps.stanford.edu/research/early-gpspnt-research/receiver-autonomous-integrity-monitoring-raim
- Stanford GPS Lab, Advanced RAIM: https://gps.stanford.edu/research/current-and-continuing-gpspnt-research/multi-constellation-gnss/advanced-raim
- Stanford GPS Lab publications: https://gps.stanford.edu/all-gps-lab-published-documents
- Indelman et al., Factor Graph Based Incremental Smoothing in Inertial Navigation Systems: https://publications.ri.cmu.edu/factor-graph-based-incremental-smoothing-in-inertial-navigation-systems
- Williams et al., Concurrent Filtering and Smoothing: https://www.cs.cmu.edu/~kaess/pub/Williams14ijrr.html
- Tian et al., IM-GIV integrity monitoring for GNSS/INS/Vision FGO: https://arxiv.org/abs/2410.22672
- Yan et al., non-Gaussian multi-constellation integrity monitoring: https://arxiv.org/abs/2507.04284
- IMO MSC.1/Circ.1575, Guidelines for shipborne PNT data processing: https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/IMO%20Documents%20related%20to/MSC.1-Circ.1575.pdf
- IALA G1180 Resilient PNT: https://www.iala.int/product/g1180-resilient-pnt/
- DoD MOSA: https://www.cto.mil/sea/mosa/
- The Open Group SOSA: https://www.opengroup.org/sosa/approach
- The Open Group FACE documents and tools: https://www.opengroup.org/face/docsandtools
- NIST SP 800-218 SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218 Rev.1 / SSDF 1.2 initial public draft: https://csrc.nist.gov/pubs/sp/800/218/r1/ipd
- IEEE 1588-2019 Precision Time Protocol: https://standards.ieee.org/ieee/1588/6825/
