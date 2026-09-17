# GNSS-Denial Engineering Objective

AMEP-1 is being developed toward resilient maritime navigation in environments where GPS/GNSS is unavailable, jammed, unreliable, or potentially deceptive. This document defines the current software behavior and the evidence still required before any operational denial-zone claim.

## Threat classes

### 1. GNSS outage or jamming

The receiver produces no usable position solution, becomes stale, reports loss of lock, or otherwise stops contributing valid observations.

The current maritime estimator can continue propagating from leveled inertial motion, water-relative velocity, estimated current, and heading. Non-GNSS absolute observations can bound drift when available, but their presence alone does not establish resilient-navigation integrity.

### 2. Grossly inconsistent GNSS

A received position may be far enough from the predicted distribution that its normalized innovation squared exceeds the configured chi-square gate. The estimator can reject the observation and repeated rejections can isolate the source.

A large innovation is fault evidence, not proof that the cause is jamming or spoofing.

### 3. Plausible spoofing or slow bias

A false GNSS solution may move gradually or remain statistically plausible relative to the estimator. A conventional innovation gate can accept this class of fault.

The current AMEP software does not claim robust detection of sophisticated spoofing.

### 4. Correlated/common-mode error

Multiple absolute sources can agree with the same wrong answer because they share a map, clock, calibration, preprocessing service, compute process, RF environment, power domain, or another upstream dependency.

AMEP v1.0 demonstrated severe covariance overconfidence under a correlated common-mode position-bias stress case. EKF covariance and source-local NIS screening are therefore insufficient as an integrity argument.

## Current denial-zone decision path

The hardened runtime separates five concerns:

1. **Normalize:** preserve and validate source time, receive time, frame, covariance, provenance, and timestamp uncertainty.
2. **Estimate:** propagate the active estimator backend and evaluate/fuse semantic observations.
3. **Assess health:** track freshness and innovation behavior for each source.
4. **Assess integrity:** evaluate local constraint coverage, declared source dependencies, cross-source contradictions, and latched faults.
5. **Authorize:** select a navigation mode only after integrity evidence is available.

The GNSS-loss transition is therefore:

```text
NOMINAL
  |
  | GNSS stale / rejected / unavailable
  v
recompute health + constraint coverage + integrity
  |
  |-- full state + non-GNSS absolute aiding
  |      + explicit resilient-navigation permission
  |      + sufficient dependency-disjoint safety-credit sources
  |          -> GPS_DENIED_RESILIENT
  |
  |-- full/partial constraints without sufficient integrity evidence
  |          -> DEGRADED_DEAD_RECKONING
  |
  `-- insufficient constraints or integrity veto
             -> SAFE_HOLD
```

The default integrity policy requires at least two ONLINE non-GNSS absolute sources that have been explicitly granted safety credit and whose declared integrity-dependency sets are pairwise disjoint. Calling `NavigationSupervisor` without an `IntegrityReport` cannot grant `GPS_DENIED_RESILIENT`.

The bundled research reference profile deliberately grants no source safety credit because it contains no validated vehicle-specific dependency analysis, adapter provenance contract, or timing budget. A platform integration must supply those declarations explicitly.

## Sensors that can contribute during GNSS denial

The reference source profile has integration seams for:

- radar-derived map fixes;
- bathymetric map fixes;
- visual map fixes;
- water-relative velocity from a speed log or appropriate DVL mode;
- independently available ground-velocity measurements;
- surface-current priors;
- gyrocompass/heading;
- leveled, gravity-compensated horizontal inertial acceleration.

The repository does not implement raw radar, bathymetric, visual, LiDAR, DVL, or GNSS RF-processing pipelines that create these normalized observations. Those are adapter/localization workstreams with their own calibration and validation requirements.

## Cross-source contradiction handling

For near-synchronous same-frame absolute-position observations with dependency-disjoint declared source chains, `CrossSourceConsistencyMonitor` evaluates the difference using the combined measurement covariance before the candidate is fused.

A contradiction prevents the disputed candidate from changing the estimator and latches integrity to `ALERT`. Two-source disagreement does not establish which source is wrong. The current software therefore blocks rather than inventing fault attribution.

## Why an EKF remains useful

An EKF provides nonlinear state propagation, uncertainty propagation, semantic measurement fusion, and innovation statistics used by the health layer. Those are useful under GNSS denial.

An EKF is not an anti-jamming radio, spoof detector, RAIM implementation, or integrity guarantee. Its usefulness depends on model quality, calibration, timing, source dependence, and available non-GNSS constraints.

## Evidence gates

### Gate A — calibrated inertial front end

Add a validated attitude/INS preprocessing path with explicit coordinate frames, gravity removal, sensor-bias handling, clock provenance, lever arms, boresight calibration, and quantified uncertainty. A production-facing backend should evaluate an expanded inertial state such as position, velocity, attitude, gyro bias, and accelerometer bias rather than feeding raw specific force into the current seven-state filter.

### Gate B — real non-GNSS aiding

Implement and validate real radar/coastline localization, bathymetric terrain-aided navigation, visual/LiDAR localization, DVL/STW, or other justified navigation aids. Each adapter must produce timestamps, frame/datum, uncertainty, provenance, calibration identity, and failure status.

### Gate C — fault-hypothesis integrity

Extend the current dependency model and pre-fusion contradiction checks with architecture-derived fault hypotheses, solution separation or equivalent FDE, explicit common-cause cases, non-Gaussian sensitivity, false-alert probability, missed-detection probability, and time-to-alert metrics.

### Gate D — recorded denial replay

Freeze outage/jamming/spoofing intervals and metrics before evaluation. Compare AMEP against strong same-sensor EKF/ESKF/UKF baselines using independently referenced truth and report accuracy and consistency metrics such as RMSE, P95/P99, NIS, NEES, empirical containment, false isolation, missed isolation, and reacquisition behavior.

### Gate E — HIL and target compute

Validate source timing, delayed packets, frozen data, clock jumps, frame mistakes, process overload, deadline misses, watchdog response, communications loss, and command gating on representative buses and target compute. Record WCET/jitter and resource saturation behavior.

### Gate F — controlled water trials

Progress from benign GNSS-outage trials to controlled denial testing only with independent truth, safety observers, abort criteria, complete logs, and a separately reviewed vessel-safety case.

## Claim boundary

A defensible current statement is:

> AMEP-1 is a maritime resilient-PNT research architecture that preserves timing, source identity, dependency assumptions, estimator uncertainty, source health, integrity state, and navigation authority while evaluating GNSS-degraded and GNSS-denied operation.

A statement not supported by the repository is:

> AMEP-1 has been proven to navigate real vessels safely through active GNSS jamming or sophisticated spoofing.

That claim requires the evidence gates above.