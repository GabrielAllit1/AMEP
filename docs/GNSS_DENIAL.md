# GNSS-Denial Engineering Objective

AMEP-1 is being developed toward resilient maritime navigation through environments where GPS/GNSS is intentionally denied, jammed, unreliable, or potentially deceptive. This document defines what that objective means for the current stack and what evidence is still required.

## Threat classes

### 1. GNSS outage or jamming

The receiver produces no usable position solution, becomes stale, reports loss of lock, or otherwise stops contributing valid observations.

This is the cleanest GNSS-denial case for the current architecture. AMEP can continue propagating its EKF state from leveled inertial motion, water-relative velocity, estimated current, and heading. Non-GNSS absolute fixes can bound drift when available.

### 2. Grossly inconsistent GNSS

A received position is far enough from the predicted distribution that its normalized innovation squared exceeds the configured chi-square gate.

The current estimator can reject the measurement, and repeated rejections can isolate the source. This is useful fault screening, but a large innovation does not identify the cause as jamming or spoofing.

### 3. Plausible spoofing or slow bias

A false GNSS solution moves gradually or remains statistically plausible relative to the estimator. A conventional innovation gate can accept this class of fault.

The current AMEP kernel does not claim robust detection of sophisticated spoofing.

### 4. Correlated/common-mode deception

Multiple absolute sources agree with the same wrong answer because they share a map, clock, environmental model, upstream dependency, or injected bias.

This is a critical integrity problem. The AMEP v1.0 research release demonstrated severe covariance overconfidence under a correlated common-mode position-bias stress case. EKF covariance and NIS gating alone are insufficient.

## Current denial-zone mechanism

The current runtime uses three distinct layers:

1. **Estimate:** the seven-state EKF propagates position, water-relative velocity, current, and heading and fuses available aiding measurements.
2. **Assess:** source health tracks freshness and innovation behavior; constraint coverage evaluates which state dimensions remain constrained.
3. **Authorize:** navigation mode determines whether autonomy is permitted, degraded, or forced into `SAFE_HOLD`.

The intended state transition during a GNSS jammer encounter is therefore not “ignore GPS and hope.” It is:

```text
NOMINAL
  │
  │ GNSS stale / rejected / unavailable
  v
recompute healthy constraints
  │
  ├─ full state + non-GNSS absolute fix ──> GPS_DENIED_RESILIENT
  │
  ├─ partial constraints ─────────────────> DEGRADED_DEAD_RECKONING
  │
  └─ insufficient constraints ────────────> SAFE_HOLD
```

## Sensors that can contribute during GNSS denial

The reference profile already provides integration seams for:

- radar-derived map fixes;
- bathymetric map fixes;
- visual map fixes;
- water-relative velocity from a speed log or appropriate DVL mode;
- ground-velocity measurements where independently available;
- surface-current priors;
- gyrocompass/heading;
- leveled, gravity-compensated horizontal inertial acceleration.

The repository does not yet implement the raw sensor-processing pipelines that create radar, bathymetric, or visual map fixes. Those are adapter/localization workstreams, not measurements the EKF can manufacture internally.

## Why an EKF remains useful

An EKF is valuable in GNSS-denied navigation because it provides a principled way to propagate a nonlinear motion model, carry uncertainty forward, and fuse asynchronous measurements with different observation models. In AMEP it also provides the innovation statistics used by the health layer.

However, an EKF is not an anti-jamming radio, a spoofing detector, or an integrity guarantee. Its usefulness depends on model quality, calibration, timing, sensor independence, and the availability of sufficiently informative non-GNSS constraints.

## Production-facing roadmap

### Gate A — calibrated inertial front end

Add a validated attitude/INS preprocessing path with explicit coordinate frames, gravity removal, bias handling, clock provenance, lever arms, and boresight calibration. Consider expanding the state to include inertial bias terms once the sensor model and observability requirements are defined.

### Gate B — real non-GNSS aiding

Implement thin adapters for real radar/coastline localization, bathymetric terrain-aided navigation, and/or other independently justified absolute or relative navigation aids. Each adapter must provide timestamps, frames, uncertainty, provenance, and failure status.

### Gate C — fault-hypothesis integrity

Add mechanisms that do not assume every source is independent or unbiased. Candidate research directions include solution separation, explicit bias states, interacting/multiple-model hypotheses, source-dependence graphs, innovation whiteness monitoring, covariance inflation under model mismatch, and integrity tests that compare dissimilar physical observables.

### Gate D — recorded denial replay

Freeze outage/jamming/spoofing intervals and evaluation metrics before testing. Compare against strong same-sensor conventional EKF/UKF baselines and report both accuracy and consistency: RMSE, P95/P99, NIS, NEES, empirical containment, false isolation, missed isolation, and reacquisition behavior.

### Gate E — HIL and target compute

Validate timestamp handling, sensor dropouts, delayed packets, clock jumps, CPU overload, deadline misses, watchdog behavior, communications loss, and actuator-command gating on the actual compute and representative buses.

### Gate F — controlled water trials

Progress from benign GNSS-outage trials to controlled denial testing only with independent truth, safety observers, abort criteria, complete logs, and a separately reviewed vessel-safety case.

## Claim boundary

A defensible current statement is:

> AMEP-1 is an EKF-centered resilient multisensor navigation architecture designed to continue estimating and to manage autonomy authority when GNSS is unavailable or inconsistent, with an explicit engineering objective of operating through active GNSS-denial zones using dissimilar non-GNSS aiding.

A statement that is not yet supported is:

> AMEP-1 has been proven to navigate real vessels safely through active GNSS jamming or sophisticated spoofing.

That claim requires the evidence gates above.
