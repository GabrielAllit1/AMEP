# Architecture

AMEP-1 is organized as a small, auditable navigation-estimation kernel with explicit contracts around the estimator. The design goal is not to hide uncertainty inside a monolithic autonomy stack; each layer has a narrow contract and a fail-closed relationship to the next layer.

## Data flow

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
source / kind / values / covariance / frame
source timestamp / receive timestamp / clock domain
provenance / timestamp uncertainty / metadata
      │
      v
TimeAligner
clock normalization / latency / age / order checks
      │
      v
AMEPFilter (EKF)
      │
innovation / NIS / accepted-fused result
      │
      v
SensorHealthManager + ConstraintCoverage
      │
      v
IntegrityEngine
      │
IntegrityReport
      │
      v
NavigationSupervisor
NOMINAL / GPS_DENIED_RESILIENT /
DEGRADED_DEAD_RECKONING / SAFE_HOLD
      │
      v
PNTSolution
position / velocity / heading / covariance
source health / source age / integrity status
containment proxy / protection-bound availability
```

Communications supervision is intentionally orthogonal: `CommunicationsSupervisor` determines which command/telemetry link is healthy, and the authority layer uses link availability when deciding whether an operator command is actionable.

## 1. Sensor and measurement contract

`src/amep1/time_alignment.py` defines `MeasurementEnvelope`. It is the normalized boundary between real sensor adapters and the estimation kernel. The envelope preserves source identity, measurement family, values, full measurement covariance, coordinate frame, source timestamp, receive timestamp, clock domain, sequence/provenance metadata, and timestamp uncertainty.

The current runtime accepts normalized local-ENU measurement products for absolute position, water-relative velocity, ground velocity, current prior, and heading. It does not pretend that raw GNSS messages, radar detections, camera/LiDAR observations, DVL packets, or raw accelerometer data are already estimator-ready. Those require explicit front-end adapters and calibration.

## 2. Time alignment

`TimeAligner` maps declared source clock domains into the navigation clock domain. The initial implementation rejects unknown clocks, excessive transport latency, excessive age, measurements from the future beyond tolerance, and out-of-order measurements.

This is deliberately conservative. The current real-time EKF does not rewind state for delayed measurements. A future fixed-lag smoother, delayed-state filter, or factor-graph backend can relax that rule without changing the measurement envelope.

Clock offsets in the current software are configured values, not a validated synchronization system. Production work still requires measured timestamp provenance, synchronization uncertainty, transport latency budgets, discontinuity handling, and target-interface evidence.

## 3. Extended Kalman Filter

`src/amep1/estimator.py` contains the reference seven-state horizontal EKF:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

The deterministic propagation uses water-relative velocity plus estimated surface current for position propagation and rotates leveled forward/starboard acceleration into the local east/north plane. Because that rotation is nonlinear in heading, the covariance transition includes the heading derivatives of the acceleration terms.

The current model deliberately stops short of a full strapdown marine INS. It has no roll/pitch states, accelerometer/gyro bias states, vertical channel, lever-arm states, clock states, or hydrodynamic model. Raw IMU specific force must therefore pass through a calibrated attitude/INS front end before entering the existing `HorizontalIMUInput` contract.

For each observation the estimator computes the innovation, innovation covariance, and normalized innovation squared (NIS). Measurements outside the configured chi-square gate are rejected. Accepted measurements use a Cholesky solve for the Kalman gain and a Joseph-form covariance update. Covariance is symmetrized and projected to a configured positive eigenvalue floor.

The normalized runtime path passes the envelope's full measurement covariance into this update rather than reducing every observation to a scalar sigma.

## 4. Sensor health and local constraint coverage

`src/amep1/health.py` tracks per-source state as `UNKNOWN`, `ONLINE`, `DEGRADED`, `ISOLATED`, or `STALE`. Current health mechanisms are freshness, consecutive innovation rejection, sliding rejection fraction, manual isolation, and probe-only recovery. It also exposes source age-of-data for the PNT output contract.

`src/amep1/constraints.py` implements the local information-rank heuristic described by the AMEP research contract. Each registered source declares which reference-state indices it constrains. The result reports constrained-state rank, simple conditioning, active sources, and GNSS/non-GNSS absolute-source availability.

Constraint rank is explicitly not nonlinear observability proof.

## 5. Integrity engine

`src/amep1/integrity.py` creates an explicit `IntegrityReport` between estimator/health state and navigation-mode authority. The current engine can declare `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT`, and it can prevent normal navigation authority when a latched runtime fault or insufficient navigation constraint rank exists.

This is an architectural integrity contract, not a certified RAIM/FDE implementation. Production-facing work still requires source-dependence/common-cause assumptions, fault hypotheses, solution separation or equivalent detection/exclusion logic, RF-health correlation where appropriate, false-alarm/missed-detection characterization, and recorded/HIL/field evidence.

Most importantly, the engine deliberately reports:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

AMEP-1 v1.0 demonstrated severe covariance overconfidence under correlated common-mode position bias. The covariance-derived containment proxy therefore remains visible as a diagnostic but is not relabeled as a protection level.

## 6. Navigation modes and command authority

`src/amep1/authority.py` maps constraint coverage into deterministic navigation modes only after the integrity report permits navigation:

- `NOMINAL`: full reference-state coverage with healthy GNSS;
- `GPS_DENIED_RESILIENT`: full reference-state coverage with a healthy non-GNSS absolute-position source;
- `DEGRADED_DEAD_RECKONING`: partial but nontrivial constraint coverage;
- `SAFE_HOLD`: integrity veto, insufficient navigation constraints, or a latched hard runtime fault.

The default thresholds are research policy, not certification limits.

Command authority remains separate: valid operator command over a healthy link has priority; autonomy is permitted only in `NOMINAL` or `GPS_DENIED_RESILIENT`; otherwise safety authority returns no autonomous helm command. `SAFE_HOLD` is a supervisory contract, not a validated physical station-keeping or propulsion behavior.

## 7. PNT solution contract

`src/amep1/solution.py` defines `PNTSolution`. It exposes the current horizontal state and supervision evidence without implying unsupported capability:

- position;
- water-relative and ground velocity;
- estimated surface current;
- heading;
- full state covariance;
- covariance-derived 95% containment proxy;
- integrity status/report;
- source health and age-of-data;
- constraint rank and active absolute sources;
- degradation/navigation mode;
- explicit protection-bound availability.

Attitude and validated navigation time are marked unavailable because the current seven-state estimator does not produce them. A future strapdown INS/time solution can extend the contract when those states and their evidence exist.

## 8. Runtime integration

`src/amep1/runtime.py` is the façade intended for an adapter/integration layer. Existing `predict()`, `update_*()`, and `status()` calls remain available. The new `ingest_measurement()` path performs time alignment, frame/kind validation, full-covariance estimator update, innovation screening, source-health accounting, and typed ingest reporting. `integrity_report()` and `pnt_solution()` expose the downstream contracts.

Invalid prediction/timebase inputs still latch a hard fault and force `SAFE_HOLD` until the root cause is corrected and explicitly cleared.

## 9. Communications and deadline timing

`src/amep1/comms.py` implements deterministic priority/freshness selection among generic links. It does not implement RF, networking, cryptography, modem control, or transport protocols.

`src/amep1/timing.py` implements a host-SIL deadline observer. It detects non-monotonic time and periods longer than a declared deadline, but it is not evidence of worst-case execution time or scheduling determinism on target hardware.

## 10. Intended denial-zone evolution

The current architecture now has stable seams for the next production-facing research tranches:

- calibrated strapdown INS/ESKF front end with attitude and inertial bias handling;
- measured clock synchronization, timestamp uncertainty, lever-arm, boresight, frame, and datum calibration;
- real radar/coastline, bathymetric, visual/LiDAR, DVL/STW, and GNSS/RF-health adapters;
- common-cause integrity logic, fault detection/exclusion, and defensible protection/integrity bounds;
- optional factor-graph/fixed-lag smoothing for delayed/asynchronous constraints, replay, and calibration rather than replacing the deterministic real-time filter by default;
- recorded maritime replay against strong same-sensor baselines;
- target-hardware WCET/jitter and watchdog evidence;
- HIL fault injection and controlled water trials.

Each addition must preserve the current rule: sensor preprocessing, time alignment, estimation, integrity assumptions, mode authority, and actuator behavior remain separately testable and negative findings remain part of the evidence record.
