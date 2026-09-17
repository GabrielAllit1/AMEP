# 07 — Integration and Production Gates

This page describes how AMEP should be integrated into a real maritime platform without converting research assumptions into operational claims by accident.

## Integration objective

A platform integration is complete only when the physical vessel, sensors, clocks, buses, estimator, integrity policy, authority behavior, compute target, and verification evidence are bound into one reviewed configuration.

The goal is not merely "get data into the filter." The goal is to preserve traceable uncertainty and authority across every interface.

## Platform profile

Every vessel / target should have a versioned platform profile that binds:

- vessel reference point and coordinate frames;
- estimator backend and state schema;
- prediction-input contract;
- source registry and dependency model;
- source safety-credit decisions;
- sensor and bus adapters;
- calibration identities;
- clock domains and synchronization policy;
- measurement latency/age limits;
- source health policy;
- constraint / observability model;
- integrity policy;
- navigation-authority policy;
- communications-link policy;
- target compute and runtime environment;
- physical safe-state behavior;
- verification requirements and evidence references.

A profile is a configuration-controlled engineering artifact, not a tuning file.

## Stage 0 — system definition

Before code integration, freeze the system context:

- intended mission and operating environment;
- navigation performance requirements;
- allowable degraded modes;
- required availability and alerting behavior;
- command/authority model;
- target compute;
- sensor suite;
- physical safe state;
- regulatory / customer constraints applicable to the actual program.

AMEP cannot derive these requirements from software.

## Stage 1 — physical and electrical integration

Close the physical facts first:

- sensor mounting coordinates;
- lever arms;
- boresights / alignment;
- cable and bus topology;
- power domains;
- grounding/bonding;
- clock distribution;
- network topology;
- environmental limits;
- restart/brownout behavior.

These facts feed directly into coordinate transforms and failure-domain assumptions.

## Stage 2 — sensor and bus adapters

Each adapter must be tested at the real interface for:

- framing / parsing;
- checksums or transport integrity where applicable;
- units;
- scale factors;
- calibration;
- frame conversion;
- datum conversion;
- timestamp extraction;
- source and receive time;
- disconnect/reconnect;
- stale/frozen data;
- restart behavior;
- corrupt or malformed messages;
- latency and queueing;
- provenance identity.

Do not credit a reference parser or simulated driver as real bus validation.

## Stage 3 — calibrated inertial mechanization

The current seven-state estimator is not a full strapdown INS. A production-facing maritime inertial implementation would normally add a dedicated INS/ESKF or equivalent backend with explicit:

- attitude representation;
- gyro and accelerometer bias states;
- Earth rotation / gravity conventions as appropriate;
- IMU calibration;
- sensor-to-body alignment;
- lever-arm compensation;
- covariance initialization;
- coning/sculling / integration approach appropriate to the rate and sensor class;
- observability and tuning evidence.

That backend should implement `EstimatorBackend` rather than pushing raw specific force into the reference horizontal filter.

## Stage 4 — source dependency and common-cause review

Create a reviewed dependency graph for all sources considered in integrity policy.

Include at least:

- antennae;
- receivers;
- RF environment;
- maps / environmental products;
- clocks;
- network paths;
- switches;
- power rails/converters;
- compute hosts/processes;
- calibration files;
- shared algorithms or preprocessing;
- operator-provided inputs.

Only after this review should any source receive safety credit.

## Stage 5 — FDE and integrity model

Operational integrity claims require architecture-derived fault hypotheses rather than generic sensor voting.

Potential work includes:

- solution separation;
- multiple-model / multiple-hypothesis testing;
- bias-state or fault-state estimation;
- explicit common-cause hypotheses;
- false-alert and missed-detection analysis;
- time-to-alert characterization;
- heavy-tail / non-Gaussian sensitivity;
- integrity-risk allocation;
- empirically validated protection bounds.

The specific method should be justified by the actual platform architecture and required risk level.

## Stage 6 — target-compute qualification

Run the exact integrated software on the declared target compute. Measure:

- execution time and jitter;
- CPU/memory margins;
- queueing and end-to-end latency;
- overload behavior;
- temperature / throttling if relevant;
- watchdog behavior;
- process restart;
- file/log storage exhaustion;
- startup and reacquisition time;
- behavior under representative concurrent workloads.

Self-hosted CI execution on an engineering workstation is not target-compute qualification, even when the CI host is fully controlled by SALT19.

## Stage 7 — recorded-data campaign

Before HIL or water trials, replay real recorded multisensor data with independently referenced truth and frozen evaluation windows.

Requirements should include:

- data and config hashes;
- frozen preprocessing;
- same-sensor comparator where performance advantage is claimed;
- predeclared outage/fault intervals;
- NIS/NEES and empirical containment;
- mode-transition evidence;
- failure-analysis retention.

## Stage 8 — HIL fault campaign

Inject interface-realistic failures, not just synthetic values inside the estimator.

Expected outputs include:

- source health transition;
- consistency result;
- integrity state;
- estimator behavior;
- navigation mode;
- authority decision;
- alert latency;
- recovery behavior.

## Stage 9 — controlled water trials

Begin with benign validation of installation, timing, and estimation before progressing to staged degraded-navigation scenarios. Trials require independent truth, safety oversight, abort criteria, and synchronized complete logging.

## Gate register

| Gate | Current repository status | Closure evidence |
| --- | --- | --- |
| Real/recorded sensor evidence | open | frozen recorded-data replay with independent truth |
| Real vessel-bus adapters | open | interface-level validation on vessel-representative hardware |
| Calibrated inertial mechanization | open | verified INS/ESKF or equivalent backend + calibration evidence |
| Time synchronization / provenance | open | measured clock/latency uncertainty and fault tests |
| Dependency / common-cause model | architecture present, vehicle evidence open | reviewed platform dependency graph |
| Integrity / protection bound | open | risk model, FDE, empirical validation |
| Target-hardware timing | open | WCET/jitter/resource/overload evidence |
| HIL fault injection | open | archived deterministic campaign |
| Physical `SAFE_HOLD` behavior | open | vessel-level control/safety verification |
| Controlled water trials | open | independent-truth trial evidence |
| Independent replication | open | second-party replay/reimplementation |

## Production terminology rule

The repository may contain **production-hardening work** and **production-quality documentation** without being **production-grade navigation software**.

The correct maturity label remains research software / SIL prototype until the relevant real-data, real-interface, target-hardware, HIL, and water-trial gates are closed.

## Change-control rule

Any change to a behavior-affecting platform item should trigger review of downstream evidence. Examples include:

- sensor firmware;
- mounting location;
- calibration;
- clock source;
- network path;
- power architecture;
- estimator state/model;
- source dependency declaration;
- safety-credit decision;
- integrity threshold;
- navigation-mode policy;
- target hardware;
- compiler/runtime/dependency stack.

Evidence is configuration-specific. Do not reuse it after the assumptions that produced it have changed.
