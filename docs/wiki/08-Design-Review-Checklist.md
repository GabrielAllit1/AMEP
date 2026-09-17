# 08 — Design Review Checklist

Use this checklist for multidisciplinary design reviews. The purpose is to force assumptions into visible engineering artifacts before they become hidden dependencies inside code.

## A. System definition

- [ ] Mission and operating environment are defined.
- [ ] Navigation performance requirements are stated in measurable units.
- [ ] Required degraded modes are defined.
- [ ] `SAFE_HOLD` has a physical vessel-level meaning, not only a software enum.
- [ ] Operator, autonomy, and safety authority are explicitly prioritized.
- [ ] The target compute, OS/runtime, and deployment topology are identified.
- [ ] The system boundary distinguishes AMEP from guidance, collision avoidance, propulsion, and communications transport.

## B. Mechanical / naval

- [ ] Vessel navigation reference point is defined.
- [ ] Every navigation sensor has measured mounting coordinates.
- [ ] Lever arms are documented with uncertainty.
- [ ] Boresight / alignment conventions and tolerances are documented.
- [ ] Expected structural flex and vibration are reviewed.
- [ ] Sensor environmental exposure is within declared limits.
- [ ] Physical safe-state behavior is verified with controls/safety engineering.

## C. Electrical / electronics

- [ ] Sensor and compute power domains are mapped.
- [ ] Shared rails/converters are represented in source dependencies.
- [ ] Grounding/bonding and EMC/EMI risks are reviewed.
- [ ] Clock-distribution topology is documented.
- [ ] Network switches/concentrators are represented as shared dependencies where applicable.
- [ ] Brownout/restart behavior is tested.
- [ ] Frozen-data behavior after interface failure is tested.

## D. Sensor / navigation interface

For every source:

- [ ] transport and message framing are documented;
- [ ] units and scale are documented;
- [ ] frame/datum are documented;
- [ ] calibration identity is traceable;
- [ ] source timestamp semantics are documented;
- [ ] receive timestamp location is documented;
- [ ] clock domain is declared;
- [ ] timestamp uncertainty is quantified;
- [ ] measurement covariance construction is justified;
- [ ] provenance is available;
- [ ] disconnect/reconnect is tested;
- [ ] stale/frozen/corrupt input is tested;
- [ ] shared dependencies are declared;
- [ ] safety credit is explicitly yes/no with rationale.

## E. Estimation

- [ ] Estimator state schema is explicitly identified.
- [ ] State covariance labels are ordered and published.
- [ ] Prediction-input contract matches the physical sensor preprocessing.
- [ ] Process model assumptions are documented.
- [ ] Process-noise tuning basis is documented.
- [ ] Observation models match adapter semantics.
- [ ] Innovation thresholds and probabilities are explicit.
- [ ] Numerical stability / PSD behavior is tested.
- [ ] Initialization and reacquisition behavior is tested.
- [ ] Delayed-measurement behavior is explicit.
- [ ] Raw IMU specific force is not fed into the seven-state reference backend as though it were leveled acceleration.

## F. Dependency and integrity

- [ ] A source-dependency/common-cause graph exists.
- [ ] Different source names are not assumed independent by default.
- [ ] Shared map dependencies are represented.
- [ ] Shared clock dependencies are represented.
- [ ] Shared compute/network/power dependencies are represented.
- [ ] Cross-source contradiction behavior is tested.
- [ ] Two-source disagreement does not auto-assign fault without evidence.
- [ ] Safety-credit decisions have a reviewed engineering basis.
- [ ] Fault hypotheses are derived from actual architecture.
- [ ] Common-mode bias is included in test campaigns.

## G. Navigation authority

- [ ] `NOMINAL` entry/exit behavior is tested.
- [ ] `GPS_DENIED_RESILIENT` cannot be reached by rank alone.
- [ ] `DEGRADED_DEAD_RECKONING` behavior is understood by autonomy consumers.
- [ ] `SAFE_HOLD` is triggered for declared hard-fault and integrity-veto cases.
- [ ] Mode transitions are logged with reason.
- [ ] Consumer behavior for stale PNT solution is explicit.
- [ ] Operator command priority and communications prerequisites are explicit.

## H. Communications / RF

- [ ] Link priorities are defined.
- [ ] Heartbeat timestamp semantics are known.
- [ ] Future-dated and stale heartbeat behavior is tested.
- [ ] Primary/secondary link failover is tested.
- [ ] RF-health observables are defined if used.
- [ ] Jamming, spoof-like bias, and simple GNSS outage are treated as different fault hypotheses.
- [ ] Transport security requirements are handled outside AMEP or by an explicitly integrated security subsystem.

## I. Timing / real-time

- [ ] Every source clock domain is known.
- [ ] Synchronization mechanism is documented.
- [ ] Offset/drift/uncertainty are measured.
- [ ] Timestamp jumps/resets are tested.
- [ ] Latency and jitter budgets are measured.
- [ ] Out-of-order and duplicate records are tested.
- [ ] Target-compute execution time is measured.
- [ ] CPU/memory saturation is tested.
- [ ] Watchdog/deadline behavior is tested on the target.

## J. Verification and evidence

- [ ] Requirements map to verification methods.
- [ ] Clean-checkout CI passes.
- [ ] Unit/integration failures are not waived without rationale.
- [ ] Deterministic replay reproduces the same configuration behavior.
- [ ] Recorded-data evaluation uses independent truth.
- [ ] Fault/outage windows are frozen before evaluation.
- [ ] Same-sensor comparators are used where performance comparisons are claimed.
- [ ] NIS/NEES/containment are reported where truth exists.
- [ ] HIL faults are injected at realistic interfaces.
- [ ] Water trials have abort criteria and safety oversight.
- [ ] Negative results and anomalies are retained.
- [ ] Evidence package identifies exact software and configuration hashes.

## K. Claim review

Before any external statement, ask:

- Is this a software-contract claim, synthetic/SIL claim, recorded-data claim, HIL claim, or field claim?
- Does the evidence come from the same layer and configuration?
- Is the population/time period stated?
- Is a covariance diagnostic being mislabeled as integrity?
- Is a reference parser being mislabeled as bus conformance?
- Is workstation timing being mislabeled as target real-time evidence?
- Is `SAFE_HOLD` being described as physical station keeping without vessel validation?
- Is a different sensor name being mislabeled as an independent failure chain?

## Review ownership matrix

| Review area | Lead discipline | Mandatory cross-review |
| --- | --- | --- |
| reference frames / lever arms | mechanical + PNT | software, test |
| sensor electrical interface | electrical | embedded, systems |
| time synchronization | embedded / comms | PNT, test |
| estimator model | PNT / controls | software, systems |
| source dependency graph | systems / safety | electrical, comms, PNT, software |
| integrity policy | PNT / safety | systems, controls, test |
| authority / safe state | controls / safety | software, mechanical, operations |
| target-compute timing | embedded / software | test, systems |
| HIL campaign | V&V | all affected disciplines |
| water-trial release | chief engineer / safety authority | all disciplines |

## Exit criteria for an engineering review

A review is not closed because the meeting ended. It is closed when:

1. open assumptions have named owners;
2. interface definitions are versioned;
3. unresolved risks are visible in the gate register;
4. verification method and pass/fail criteria are assigned;
5. no unsupported claim is being used to justify a downstream safety or authority decision.
