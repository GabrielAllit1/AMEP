# 02 — Discipline Views

AMEP is a multidisciplinary navigation-assurance architecture. This page translates the same system into the questions each engineering discipline is expected to ask.

## Mechanical / naval architecture

### What AMEP needs from this discipline

- a defined vessel reference point for navigation state;
- sensor mounting coordinates and lever arms relative to that reference;
- boresight / alignment definitions and tolerances;
- expected rigid-body motion, vibration, shock, flex, and thermal effects;
- any hydrodynamic assumptions that affect water-relative velocity, current estimation, or maneuvering;
- a physical definition of what the platform must do when AMEP requests `SAFE_HOLD`.

### Why it matters

A mathematically correct estimator can still be wrong if a GNSS antenna, IMU, radar, DVL, or camera is represented at the wrong physical point or with the wrong orientation. Lever-arm error becomes position/velocity error during rotation. Structural flex can invalidate a fixed boresight assumption. Vibration and shock can contaminate inertial measurements.

### What AMEP currently provides

AMEP preserves coordinate-frame identity and expects calibrated, estimator-ready observations. It does not currently contain a vessel-specific lever-arm or boresight calibration subsystem, full six-degree-of-freedom vessel model, or validated physical `SAFE_HOLD` behavior.

### Evidence required for operational integration

- controlled survey of sensor locations;
- documented frame tree and sign conventions;
- alignment/boresight calibration procedure and uncertainty;
- vibration/environmental test evidence where relevant;
- water-trial verification that platform motion and mounting assumptions do not invalidate navigation outputs.

## Electrical / electronics / power

### What AMEP needs from this discipline

- sensor and compute power topology;
- grounding/bonding architecture;
- connector and bus definitions;
- clock distribution / synchronization hardware path;
- fault isolation boundaries;
- EMC/EMI risk characterization;
- restart/brownout behavior;
- identification of shared power or compute dependencies between nominally separate navigation sources.

### Why it matters

Two sensors that share the same power converter, clock, switch, compute module, or interface concentrator can fail together. AMEP's source-dependency model is only as credible as the physical architecture behind it.

### What AMEP currently provides

`SourceRegistry` can declare primary failure domains and shared dependency tokens. Those declarations are software representations of engineering facts; AMEP does not discover wiring topology automatically and does not prove independence.

### Evidence required for operational integration

- electrical block diagram and power-domain map;
- failure-mode review for shared rails, converters, switches, and clocks;
- brownout/restart/frozen-data tests;
- timestamp continuity tests across resets;
- EMC/EMI test evidence appropriate to the intended vessel environment.

## Navigation / PNT / sensor fusion

### What AMEP needs from this discipline

- estimator state definition and frame conventions;
- process model and process-noise assumptions;
- observation models and full measurement covariance;
- calibrated timing uncertainty;
- source-dependency / common-cause assumptions;
- fault hypotheses and integrity-risk model;
- truth reference and predeclared metrics for validation.

### What AMEP currently provides

The reference estimator is a seven-state horizontal maritime EKF-like backend with explicit water-relative velocity and surface current, NIS screening, Cholesky solves, Joseph-form covariance updates, and covariance repair. AMEP separates this estimator from health, dependency-aware integrity, cross-source consistency, authority, and replay.

### Key warning

The Version 1.0 correlated-common-bias experiment is a design constraint: mutually consistent absolute sources can pull the solution to the wrong location while covariance remains too small. Estimator consistency is therefore not equivalent to integrity.

## Communications / RF

### What AMEP needs from this discipline

- RF/link architecture and priority;
- heartbeat source and timestamp semantics;
- expected latency and dropout distributions;
- GNSS interference/jamming/spoofing observables available from receiver or RF monitor;
- shared antenna, receiver, network, clock, or power dependencies;
- authenticated transport / cybersecurity design if required by the platform.

### What AMEP currently provides

`CommunicationsSupervisor` performs deterministic link-priority and heartbeat-freshness selection with rejection of invalid and future-dated time values. Timing/RF-health information can be represented as source evidence.

### What AMEP does not provide

- modem control;
- RF waveform processing;
- link encryption/authentication;
- network intrusion detection;
- jamming geolocation;
- a validated spoofing detector;
- transport reliability guarantees.

## Embedded / real-time computing

### What AMEP needs from this discipline

- declared target compute and operating environment;
- monotonic clock source;
- scheduling model;
- CPU/memory budget;
- maximum permitted end-to-end measurement latency;
- worst-case execution-time and jitter characterization;
- watchdog / process-supervision behavior;
- restart and failover design.

### What AMEP currently provides

The repository contains host-SIL timing observation and rejects non-finite/non-monotonic timing. GitHub CI on the dedicated AMEP Windows runner validates software behavior, not target-hardware real-time behavior.

### Evidence required before deployment claims

- WCET and tail-latency measurements under representative load;
- CPU/memory saturation tests;
- overload and queue-growth behavior;
- deadline-miss injection;
- watchdog response on the actual target;
- restart/recovery timing and state continuity evidence.

## Controls / autonomy

### What AMEP needs from this discipline

- explicit contract for how navigation mode affects guidance/control authority;
- autonomy behavior allowed in each mode;
- platform-specific safe state;
- command arbitration with operator and safety authority;
- actuator and vehicle-dynamics limitations.

### What AMEP currently provides

AMEP produces explicit navigation modes and an integrity-aware authority decision. Autonomy is not supposed to treat a position estimate as sufficient evidence by itself.

The critical modes are:

| Mode | Meaning to autonomy |
| --- | --- |
| `NOMINAL` | full reference coverage with healthy GNSS and no integrity veto |
| `GPS_DENIED_RESILIENT` | non-GNSS navigation only when integrity explicitly permits it |
| `DEGRADED_DEAD_RECKONING` | reduced navigation confidence; normal resilient authority is not granted |
| `SAFE_HOLD` | AMEP requests safety authority / no normal autonomous helm command |

AMEP does not define the vehicle controller, PID gains, MPC law, collision avoidance, or physical station keeping.

## Software / platform engineering

### What AMEP needs from this discipline

- thin adapters that convert raw platform data into semantic measurements;
- strict frame, covariance, timestamp, and provenance handling;
- configuration management;
- deterministic logging and replay;
- dependency and software identity;
- failure behavior that preserves fail-closed semantics.

### What AMEP currently provides

The software is divided into explicit modules for timing, source registry, consistency, estimation, health, coverage, integrity, authority, solution output, replay, evidence, communications support, and runtime orchestration. `EstimatorBackend` is the principal estimator portability seam.

A platform adapter must not bypass the normalized runtime simply because a direct call is easier.

## Verification / test engineering

### What AMEP needs from this discipline

- requirements traced to tests;
- deterministic synthetic cases;
- recorded replay with frozen fault windows;
- independent truth;
- HIL campaigns;
- target-compute timing tests;
- controlled water trials;
- retention of negative findings.

### What AMEP currently provides

The repository has unit/integration testing, deterministic replay architecture, configuration-bound evidence logging, and explicit production gates. Software tests establish software contracts only.

Test count is not treated as system maturity.

## Safety / systems assurance

### What AMEP needs from this discipline

- hazard analysis;
- fault tree / FMEA / FMECA as appropriate;
- definition of safety-significant navigation outputs;
- source-dependency/common-cause review;
- risk allocation for integrity if a protection bound is eventually claimed;
- explicit safe-state behavior at the vessel level;
- independent review of assumptions and failure containment.

### What AMEP currently provides

AMEP makes uncertainty and authority explicit and refuses to expose the covariance-derived containment radius as a validated protection level. Current output states:

```text
horizontal_protection_bound_m = None
protection_bound_validated = False
```

That is the correct behavior until an integrity-risk model and empirical validation justify something stronger.

## Human factors / operations

AMEP's software can prioritize operator authority when the command path is healthy, but it does not define operator displays, alarm philosophy, remote-control ergonomics, bridge procedures, watchstanding, or training. Those are integration concerns and must be designed around the reasons AMEP provides for mode transitions and integrity vetoes.

## Cross-discipline rule

No discipline should hand another discipline an undocumented assumption. If an assumption affects navigation accuracy, integrity, timing, failure independence, or authority, it belongs in the platform profile and the verification evidence package.
