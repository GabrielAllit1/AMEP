# 04 — Estimation, Integrity, and Authority

AMEP separates three questions that are often conflated:

1. **What is the best current state estimate?** Estimation.
2. **What evidence exists that the estimate is trustworthy enough for a given mode?** Integrity.
3. **What navigation/autonomy authority is permitted now?** Authority.

That separation is central to the architecture.

## Reference estimator state

The published AMEP-1 maritime state is:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

with ground velocity:

```text
Vg_E = Vw_E + C_E
Vg_N = Vw_N + C_N
```

`E,N` are local east/north position, `Vw` is water-relative velocity, `C` is surface current, and `psi` is heading.

The current implementation rotates leveled, gravity-compensated forward/starboard acceleration into the local horizontal frame and propagates position, water-relative velocity, current, and heading. It is not a complete inertial mechanization.

## Measurement update discipline

For a measurement model `z = Hx + v`, AMEP uses the standard innovation concepts:

```text
r = z - Hx-
S = H P- H^T + R
```

and normalized innovation squared:

```text
d^2 = r^T S^-1 r
```

A configured chi-square gate can reject statistically incompatible measurements. Accepted updates use a Joseph-form covariance update. The implementation also uses finite-value checks, Cholesky solves, and positive-semidefinite covariance repair.

The engineering interpretation is important: **an innovation rejection means the measurement is inconsistent with the current model and covariance at the configured threshold. It does not identify spoofing, jamming, malicious intent, or a particular failed component.**

## Health is not integrity

`SensorHealthManager` tracks source condition using evidence such as freshness and rejection history. Typical states are `UNKNOWN`, `ONLINE`, `DEGRADED`, `ISOLATED`, and `STALE`.

A source can be healthy yet wrong in a way that is consistent with other biased sources. Therefore health status alone cannot authorize resilient navigation.

## Constraint coverage is not observability proof

`ConstraintCoverage` asks whether declared healthy sources locally constrain the estimator state under the configured simplified information model. The implementation supports configurable state dimension; the maritime profile uses seven.

A rank value is a useful supervisory heuristic, not a proof of nonlinear observability, detectability of bias states, or global correctness over a trajectory.

## Cross-source consistency

Before an absolute-position candidate mutates estimator state, `CrossSourceConsistencyMonitor` can compare it with near-synchronous, same-frame observations from dependency-disjoint source chains.

If two supposedly independent chains disagree beyond the configured statistical threshold:

- the disputed candidate is prevented from mutating the estimator;
- integrity is latched to `ALERT`;
- the architecture does not automatically declare either source the culprit.

Fault attribution requires more evidence than disagreement between two sources.

## Dependency-aware integrity

`IntegrityEngine` combines:

- source health;
- constraint coverage;
- source-registry dependency evidence;
- cross-source contradictions;
- hard runtime faults.

The resulting `IntegrityReport` can be `MONITORING`, `DEGRADED`, `UNAVAILABLE`, or `ALERT` and can explicitly veto resilient navigation.

The reference integrity policy requires at least two ONLINE non-GNSS absolute sources with safety credit whose declared integrity-dependency sets are pairwise disjoint before non-GNSS navigation can receive resilient authorization.

This does not prove those sources are statistically independent. It is a conservative software rule that depends on a reviewed platform dependency model.

## Navigation modes and authority

`NavigationSupervisor` maps the current evidence into explicit mode.

| Mode | Reference condition | Meaning |
| --- | --- | --- |
| `NOMINAL` | full local coverage + healthy GNSS + no integrity veto | normal reference navigation information is available |
| `GPS_DENIED_RESILIENT` | full non-GNSS coverage + explicit integrity permission | resilient non-GNSS navigation is authorized by the current research policy |
| `DEGRADED_DEAD_RECKONING` | partial coverage, or full non-GNSS coverage without enough integrity evidence | position uncertainty / risk is expected to grow; resilient authority is not granted |
| `SAFE_HOLD` | insufficient constraints, integrity veto, or latched hard fault | request safety authority; no normal autonomous helm command |

The mode names describe software policy, not certified safety states.

## Why the common-mode result matters

AMEP-1 Version 1.0 intentionally tested a correlated common-mode position bias. The result was a material failure: the estimator could follow mutually consistent but wrong absolute sources while its covariance remained much too small. The nominal 95% covariance-derived containment proxy contained truth only about 8.7% of the outage in that stress case.

That result drives several current design choices:

- source independence is never inferred from source count;
- safety credit is explicit and conservative;
- pre-fusion consistency is separated from estimator innovation checks;
- navigation authority depends on integrity evidence, not just state rank;
- covariance is not presented as a protection level.

## Protection-bound boundary

Current `PNTSolution` semantics intentionally include:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

The solution may expose a covariance-derived horizontal containment proxy at a configured probability. That value is a diagnostic under the estimator's covariance assumptions. It is not an integrity protection bound.

A future protection bound would require, at minimum:

- an explicit integrity-risk allocation;
- architecture-derived fault hypotheses;
- common-cause assumptions;
- FDE / solution-separation or equivalent mechanisms appropriate to the platform;
- false-alert, missed-detection, and time-to-alert characterization;
- independent truth;
- empirical validation over declared operational conditions.

## Estimator portability

AMEP does not require future platforms to use the seven-state reference estimator. `EstimatorBackend` allows a platform to supply another estimator while retaining the surrounding assurance path.

A production-facing maritime inertial backend would normally include position, velocity, attitude, gyro bias, and accelerometer bias at minimum, along with explicit Earth/gravity/frame conventions and calibration. That backend would need its own verification evidence.

## Engineering rule

Do not use estimator sophistication as a substitute for an integrity argument. A larger filter, smoother, factor graph, learned model, or multi-sensor stack can still fail confidently when its assumptions share the same wrong information.
