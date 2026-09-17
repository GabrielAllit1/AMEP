# Architecture

AMEP-1 is organized as a small navigation-estimation kernel with explicit contracts around measurement timing, source dependencies, estimator behavior, integrity, navigation mode, and output evidence. The executable reference estimator remains maritime and horizontal; the surrounding interfaces are designed so a different estimator backend can be integrated without duplicating the assurance path.

## Data flow

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
 clock normalization / latency / age / ordering checks
                         |
                         v
                    SourceRegistry
 role / failure domain / shared dependencies / safety-credit contract
               |                              |
               v                              v
 CrossSourceConsistency                 EstimatorBackend
 dependency-aware pre-fusion            backend owns state layout,
 absolute-position checks               frames and measurement models
               |                              |
               +---------------+--------------+
                               v
                      SensorHealthManager
                               |
                      ConstraintCoverage
                               |
                        IntegrityEngine
 health + constraint rank + dependency diversity + conflicts
                               |
                      NavigationSupervisor
 NOMINAL / GPS_DENIED_RESILIENT / DEGRADED_DEAD_RECKONING / SAFE_HOLD
                               |
                               v
                          PNTSolution
 frame + state schema + covariance labels + health + integrity + age

Delayed/asynchronous extension seam:
MeasurementEnvelope -> DelayedMeasurementBackend -> fixed-lag/FGO backend

Verification path:
recorded events -> DeterministicReplay -> configuration-bound EvidenceLog
```

Communications-link supervision and host timing observation are support utilities. They are not part of the estimator evidence chain and do not implement transport security, RF control, real-time scheduling, or vessel actuation.

## 1. Measurement contract

`src/amep1/time_alignment.py` defines `MeasurementEnvelope`, the normalized boundary between sensor adapters and estimator fusion. It preserves source identity, measurement family, values, full covariance, coordinate frame, source timestamp, receive timestamp, clock domain, provenance, sequence metadata, timestamp uncertainty, and adapter metadata.

The current maritime backend accepts normalized local-ENU position, water-relative velocity, ground velocity, current prior, and heading observations. Raw GNSS messages, radar detections, imagery, LiDAR point clouds, DVL packets, and raw accelerometer specific force are not treated as estimator-ready observations. Those require explicit adapter/localization and calibration layers.

The conservative research runtime requires every source to be registered and disables legacy direct measurement-update helpers. Compatibility construction of `AMEPRuntime` can still enable those helpers for historical tests and migration, but that path is not the reference integration contract.

## 2. Time alignment

`TimeAligner` maps declared source clock domains into the navigation clock domain and rejects unknown clocks, excessive transport latency, excessive age, excessive future skew, and out-of-order samples. Alignment is two-phase: source ordering watermarks advance only after downstream contract validation succeeds.

Configured clock offsets and uncertainty values are software inputs, not a validated time-synchronization system. Operational work still requires measured timestamp provenance, clock discontinuity handling, synchronization uncertainty, transport-latency budgets, and target-interface evidence.

The real-time reference EKF does not rewind for delayed measurements. Delayed-state or factor-graph processing belongs behind the separate delayed-measurement backend seam.

## 3. Source registry and dependency model

`SourceRegistry` separates source identity from integrity assumptions. Each source can declare:

- source class and absolute/GNSS role;
- primary failure domain;
- additional shared dependency tokens;
- clock-domain expectation;
- provenance requirement;
- timestamp-uncertainty budget;
- whether the integration grants that source safety credit.

Safety credit is opt-in. A source cannot receive it unless the descriptor requires provenance and declares a finite timestamp-uncertainty budget. The bundled research reference profile grants no source safety credit because no vehicle-specific dependency analysis, adapter provenance contract, or timing budget has been validated in this repository.

Failure-domain and dependency declarations are engineering assumptions. They do not prove statistical independence.

## 4. Cross-source consistency

`CrossSourceConsistencyMonitor` performs pre-fusion consistency checks on near-synchronous, same-frame absolute-position observations whose declared integrity-dependency sets are disjoint. It uses the difference covariance of the two observations and a chi-square threshold.

A detected contradiction prevents the disputed candidate from mutating the estimator and latches the integrity path to `ALERT`. Two-source disagreement does not identify which source is faulty; culprit attribution requires additional evidence or fault hypotheses.

## 5. Estimator backend

`EstimatorBackend` is the runtime portability seam. A backend declares accepted semantic measurement kinds and coordinate frames, owns its state layout and observation models, processes platform-specific prediction inputs, and returns an `EstimatorSnapshot`.

The current `AMEPFilter` backend implements the published seven-state horizontal maritime model:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

Propagation uses water-relative velocity plus estimated current and rotates leveled forward/starboard acceleration into east/north coordinates. The covariance transition contains the heading derivatives of those acceleration terms. Measurement updates use NIS gating, Cholesky solves, Joseph-form covariance updates, finite-value checks, and positive-semidefinite covariance repair.

This model is not a full strapdown INS. It has no roll/pitch states, gyro or accelerometer bias states, vertical channel, clock states, lever-arm states, or hydrodynamic state model. `HorizontalIMUInput` therefore accepts only leveled, gravity-compensated horizontal acceleration and yaw rate.

`EstimatorSnapshot` publishes a `state_schema_id` and ordered `covariance_labels` alongside covariance so a replacement backend cannot expose an unlabeled matrix.

## 6. Sensor health and constraint coverage

`SensorHealthManager` tracks `UNKNOWN`, `ONLINE`, `DEGRADED`, `ISOLATED`, and `STALE` state using freshness, innovation behavior, manual isolation, and probe-only recovery. It also exposes age-of-data.

`ConstraintCoverage` is a configurable state-dimension local information-rank heuristic. It no longer assumes a seven-state vector in its implementation; the maritime reference profile explicitly instantiates `state_dim=7`. A platform integration must provide its own state dimension and source-to-state constraint model.

Constraint rank is not a proof of nonlinear observability.

## 7. Integrity and navigation modes

`IntegrityEngine` combines health, constraint coverage, source-registry evidence, cross-source consistency, and latched runtime faults into an explicit `IntegrityReport`. It reports `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT` and can veto navigation authority.

The reference integrity policy requires at least two ONLINE, safety-credit, non-GNSS absolute sources whose declared integrity-dependency sets are pairwise disjoint before non-GNSS operation can receive resilient-navigation permission. Full state-rank coverage by itself is insufficient.

`NavigationSupervisor` fails conservative when full non-GNSS coverage exists but no integrity report is supplied. `GPS_DENIED_RESILIENT` is reachable only when the supplied integrity report explicitly permits resilient navigation. This closes the historical path where a caller could bypass dependency-diversity evidence by invoking the supervisor directly.

Mode meanings are:

- `NOMINAL`: full local constraint coverage with healthy GNSS and no integrity veto;
- `GPS_DENIED_RESILIENT`: full local coverage with non-GNSS absolute aiding and explicit resilient-navigation permission from integrity;
- `DEGRADED_DEAD_RECKONING`: partial coverage or full non-GNSS coverage without sufficient integrity evidence;
- `SAFE_HOLD`: integrity veto, insufficient navigation constraints, or a latched hard runtime fault.

These thresholds are research policy, not certification limits. `SAFE_HOLD` is a supervisory state, not a validated physical station-keeping or propulsion behavior.

## 8. PNT solution contract

`PNTSolution` exposes the navigation result without inventing unsupported capability. It includes:

- coordinate frame;
- horizontal position and ground velocity;
- optional backend-specific water velocity and current;
- heading;
- covariance plus `state_schema_id` and ordered `covariance_labels`;
- the configured containment probability and covariance-derived horizontal containment proxy;
- integrity status/report and explicit protection-bound availability;
- source health and age-of-data;
- constraint rank and navigation mode.

The containment proxy field is probability-neutral in its name because the estimator containment probability is configurable. It remains a diagnostic covariance quantity. The repository still reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

AMEP-1 v1.0 demonstrated severe covariance overconfidence under correlated common-mode position bias; covariance is therefore not relabeled as a protection level.

## 9. Replay and evidence

`DeterministicReplay` reproduces online processing order using recorded receive time for measurement events and explicit sequence numbers for equal-time ordering. Source timestamps remain inside each envelope and are normalized by the same `TimeAligner` used online, avoiding incorrect ordering across different source clock domains.

Replay distinguishes:

- contract-rejected measurements;
- ingest-accepted measurements;
- estimator-accepted measurements;
- fused measurements;
- estimator innovation rejections.

`EvidenceLog` provides canonical SHA-256 hash chaining. Replay configuration binds evidence to behavior-affecting runtime configuration, source-registry declarations, estimator configuration, timing/integrity/navigation policies, software-tree identity, Python runtime, and key dependency versions. This provides deterministic software tamper-evidence; it is not a digital signature, secure clock, trusted logger, or certification mechanism.

## 10. Communications and timing support

`CommunicationsSupervisor` performs deterministic link-priority and heartbeat-freshness selection. It rejects non-finite and non-monotonic heartbeat timestamps, rejects non-finite query times, and does not treat future-dated heartbeats as healthy.

`DeadlineWatchdog` rejects non-finite timestamps, detects non-monotonic observations and deadline misses, and keeps a missed/non-monotonic sample from corrupting the last valid timing reference.

These modules remain support utilities. They do not establish RF/link security, network reliability, real-time scheduling guarantees, WCET, or actuator safety.

## 11. Remaining production evidence gates

The architecture has explicit seams for work that is not yet evidenced here:

- calibrated strapdown INS/ESKF with attitude and inertial-bias states;
- measured clock synchronization, timestamp uncertainty, lever-arm, boresight, datum, and frame calibration;
- real GNSS, radar, bathymetry, vision/LiDAR, DVL/STW, RF-health, and vehicle-bus adapters;
- architecture-derived fault hypotheses, FDE/solution separation, false-alert and missed-detection characterization;
- empirically justified integrity/protection bounds;
- recorded maritime replay with independent truth and frozen fault intervals;
- target-hardware WCET/jitter/overload evidence;
- HIL fault injection and controlled water trials.

Each addition must preserve the separation between preprocessing, time alignment, estimation, dependency assumptions, health, integrity, navigation authority, and physical actuator behavior.