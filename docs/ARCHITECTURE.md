# Architecture

AMEP-1 is organized as a small, auditable navigation-estimation kernel with explicit supervision around the estimator. The design goal is not to hide uncertainty inside a monolithic autonomy stack; each layer has a narrow contract and a fail-closed relationship to the next layer.

## Data flow

```text
preprocessed IMU / heading / velocity / absolute fixes
                    │
                    v
             AMEPFilter (EKF)
                    │
          innovation / acceptance
                    │
                    v
          SensorHealthManager
                    │
          healthy/degraded sources
                    │
                    v
          ConstraintCoverage
                    │
          information-rank result
                    │
                    v
          NavigationSupervisor
                    │
      navigation mode + authority gate
                    │
                    v
      operator / autonomy / SAFE_HOLD
```

Communications supervision is intentionally orthogonal: `CommunicationsSupervisor` determines which command/telemetry link is healthy, and the authority layer uses link availability when deciding whether an operator command is actionable.

## 1. Extended Kalman Filter

`src/amep1/estimator.py` contains the reference seven-state horizontal EKF:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

The deterministic propagation uses water-relative velocity plus estimated surface current for position propagation and rotates leveled forward/starboard acceleration into the local east/north plane. Because that rotation is nonlinear in heading, the covariance transition includes the heading derivatives of the acceleration terms.

The current model deliberately stops short of a full strapdown marine INS. It has no roll/pitch states, accelerometer/gyro bias states, vertical channel, lever-arm states, clock states, or hydrodynamic model. Those belong in a calibrated front end or a future expanded state model.

Measurement families are represented with explicit observation matrices:

- absolute local position: `E,N`;
- water-relative velocity: `Vw_E,Vw_N`;
- ground velocity: `Vw + C`;
- current prior: `C_E,C_N`;
- heading: `psi`, with wrapped angular residual.

For each observation the estimator computes the innovation, innovation covariance, and normalized innovation squared (NIS). Measurements outside the configured chi-square gate are rejected. Accepted measurements use a Cholesky solve for the Kalman gain and a Joseph-form covariance update. Covariance is symmetrized and projected to a configured positive eigenvalue floor.

## 2. Sensor integrity and health

`src/amep1/health.py` tracks per-source state as `UNKNOWN`, `ONLINE`, `DEGRADED`, `ISOLATED`, or `STALE`.

The current policy uses four mechanisms:

1. source freshness;
2. consecutive innovation rejection;
3. sliding rejection fraction;
4. explicit manual isolation.

An isolated source is not immediately trusted again. It can be evaluated in probe-only mode, where measurements are tested against the EKF but not fused. A configured sequence of accepted probes moves the source back toward usable status.

This is fault supervision, not a complete spoofing classifier. NIS consistency is only consistency with the current state/covariance model.

## 3. Constraint coverage

`src/amep1/constraints.py` implements the local information-rank heuristic described by the AMEP research contract. Each registered source declares which state indices it constrains and an information weight. Healthy or degraded sources contribute to a diagonalized information approximation.

The result reports:

- number of locally constrained state dimensions;
- a simple conditioning metric;
- healthy source names;
- active absolute-position sources;
- whether healthy GNSS is present;
- whether a healthy non-GNSS absolute source is present.

This mechanism is deliberately not called nonlinear observability. A full observability analysis would require the actual nonlinear dynamics and measurement Jacobians over a trajectory, including any future bias states.

## 4. Navigation modes

`src/amep1/authority.py` maps the coverage result into deterministic modes:

- `NOMINAL`: full reference-state coverage with healthy GNSS;
- `GPS_DENIED_RESILIENT`: full reference-state coverage with a healthy non-GNSS absolute-position source;
- `DEGRADED_DEAD_RECKONING`: partial but nontrivial constraint coverage;
- `SAFE_HOLD`: insufficient navigation constraints or a latched hard runtime fault.

The default thresholds are policy, not certification limits.

## 5. Command authority

AMEP separates navigation confidence from command authority. The supervisor applies the following ordering:

1. valid operator command over a healthy command link;
2. autonomy command only when navigation mode is `NOMINAL` or `GPS_DENIED_RESILIENT`;
3. otherwise safety authority with no autonomous helm command.

`SAFE_HOLD` is a supervisory contract only. It does not itself implement station keeping, propulsion shutdown, collision avoidance, or a vessel-specific safe maneuver.

## 6. Runtime integration

`src/amep1/runtime.py` is the façade intended for an adapter/integration layer. It owns no hardware transport. It performs three important orchestration functions:

- routes each accepted/rejected measurement result into source health;
- recomputes constraint coverage and navigation mode for status reporting;
- latches invalid IMU/timebase prediction failures into `SAFE_HOLD` until explicitly cleared after the root cause is corrected.

## 7. Communications and timing

`src/amep1/comms.py` implements deterministic priority/freshness selection among generic links. It does not implement RF, networking, cryptography, modem control, or transport protocols.

`src/amep1/timing.py` implements a host-SIL deadline observer. It detects non-monotonic time and periods longer than a declared deadline, but it is not evidence of worst-case execution time or scheduling determinism on target hardware.

## 8. Intended denial-zone evolution

The current architecture provides the correct seams for a more complete GNSS-denial stack without forcing those concerns into one estimator class. Likely production-facing additions include:

- calibrated INS/attitude mechanization and inertial bias states;
- radar/coastline or radar-SLAM absolute/relative aiding;
- bathymetric terrain-aided navigation;
- visual map localization where environmental conditions permit;
- explicit clock, latency, lever-arm, boresight, and datum handling;
- source-dependence/common-cause models and solution-separation or multi-hypothesis integrity logic;
- replay adapters, vessel-bus adapters, HIL interfaces, and target-hardware watchdog integration.

Each addition should preserve the current rule: estimation, health, integrity assumptions, navigation authority, and actuator behavior remain separately testable.
