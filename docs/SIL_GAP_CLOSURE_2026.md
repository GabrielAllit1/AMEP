# AMEP SIL gap-closure increment — 2026-09-17

This document records engineering work added after the frozen AMEP-1 Version 1.0 research deposit. It does **not** amend the published Version 1.0 results, create a Version 2 claim, or convert AMEP into production-grade navigation software.

## Scope

The increment closes or substantially advances gaps that can be addressed in software-in-the-loop (SIL) without inventing physical evidence:

1. replaceable strapdown inertial-estimation reference implementation;
2. dependency-derived fault hypotheses, generic solution-separation/FDE machinery, integrity-risk bookkeeping, and characterization metrics;
3. lever-arm/boresight/calibration-uncertainty contracts;
4. a checksum-validating NMEA 0183 normalization path from bounded byte streams to `MeasurementEnvelope` records.

The repository maturity label remains **research software / SIL prototype**.

## 1. Strapdown INS / ESKF reference backend

`src/amep1/inertial.py` adds `StrapdownESKF`, a local-ENU nominal-state strapdown implementation with a 15-state error covariance:

```text
nominal: position(3), velocity(3), quaternion(4), accel bias(3), gyro bias(3)
error:   dp(3), dv(3), dtheta(3), dba(3), dbg(3)
```

The reference implementation includes:

- raw body-frame specific force and angular-rate input via `StrapdownIMUInput`;
- WGS-84 normal-gravity magnitude as a function of latitude/altitude;
- Earth rotation represented in local ENU and Coriolis acceleration;
- accelerometer and gyroscope bias states;
- first-order error-state covariance propagation driven by declared IMU white-noise and bias-random-walk assumptions;
- quaternion attitude propagation and covariance reset after attitude-error injection;
- covariance-aware position, ground-velocity, and heading updates;
- chi-square innovation screening;
- Joseph-form covariance update;
- a schema-labeled 15-state covariance snapshot through the existing `EstimatorBackend` seam.

This is a **reference mechanization for SIL and integration testing**, not a calibrated production INS. It does not establish coning/sculling adequacy for a particular sample rate, temperature calibration, vibration performance, target-hardware determinism, or vessel accuracy. The default noise values are explicit research assumptions and must be replaced by measured IMU characterization before operational use.

## 2. Fault hypotheses, FDE, and integrity-risk bookkeeping

`src/amep1/fde.py` adds estimator-independent integrity research primitives:

- `derive_fault_hypotheses(...)` creates deterministic single-source and shared-dependency/common-cause hypotheses from `SourceRegistry` declarations;
- `RiskAllocation` makes total and per-hypothesis integrity-risk bookkeeping explicit rather than implicit;
- `SolutionSeparationMonitor` compares a primary horizontal solution with hypothesis-excluded alternatives using their covariances and chi-square separation tests;
- `DetectionTrial` / `DetectionMetrics` report false-alert rate, missed-detection rate, and mean/P95 time-to-alert for declared SIL campaigns.

The solution-separation layer intentionally consumes precomputed alternative solutions. A platform can generate those alternatives with the seven-state filter, the new ESKF, a UKF, a fixed-lag smoother, or a factor graph without changing the FDE decision contract.

This closes the generic **software framework** gap. It does not close the operational integrity gap. A real platform still needs a reviewed physical/electrical/software dependency graph, platform-derived fault probabilities or allocations, frozen alert limits, non-Gaussian/common-cause sensitivity analysis, and empirical validation against independent truth. `IntegrityEngine` therefore continues to report no validated horizontal protection bound.

## 3. Installation calibration and uncertainty

`src/amep1/installation.py` adds `SensorInstallation`, which records:

- sensor and body frame identities;
- three-axis lever arm;
- sensor-to-body boresight roll/pitch/yaw;
- a 6 x 6 calibration covariance over lever arm and boresight;
- calibration identity and provenance;
- whether the values are measured;
- clock domain, nominal latency, and latency uncertainty.

The module implements rigid-body velocity translation from a displaced sensor to the body origin and first-order covariance propagation from measurement, lever-arm/boresight, and optional angular-rate uncertainty.

This closes the **data-model and propagation** gap. The repository still does not contain measured vessel installation values, survey evidence, temperature dependence, alignment-repeatability data, or an accepted calibration procedure for a specific platform.

## 4. NMEA 0183 reference adapter

`src/amep1/nmea0183.py` adds:

- checksum validation;
- selected GGA, RMC, HDT, and VHW parsing;
- explicit WGS-84-to-local projection ownership for GGA position;
- ENU ground-velocity construction from RMC speed/course;
- heading normalization from HDT;
- water-relative velocity construction from VHW;
- bounded CR/LF byte-stream framing;
- conversion to timestamped, provenance-bearing, covariance-bearing `MeasurementEnvelope` records.

This is a real sentence/byte normalization path, but it does not open or configure a serial port and it is not IEC 61162/NMEA conformance evidence. Electrical interfaces, vendor-specific messages, device configuration, bus loading, failover, and actual vessel integration remain platform work.

## Verification and traceability

`tests/test_sil_gap_closure.py` exercises the new implementations. The executable assurance matrix now traces:

- `AMEP-INS-001` — strapdown ESKF reference behavior;
- `AMEP-FDE-001` — dependency-derived FDE/risk bookkeeping and detection metrics;
- `AMEP-CAL-001` — installation correction and uncertainty propagation;
- `AMEP-ADAPT-001` — NMEA 0183 normalization.

The normal CI gates remain compile, Ruff, mypy, Bandit, assurance-matrix verification, dependency audit, SBOM generation, and coverage-gated pytest on the repository-specific AMEP Windows self-hosted runner.

## Gaps that remain open by evidence class

The following cannot be declared closed from this increment:

- recorded real multisensor data with independent truth;
- validated protection levels or certified integrity risk;
- platform-specific physical dependency/fault tree validated against the actual vessel;
- measured lever arms, boresights, latency distributions, clock synchronization, temperature calibration, and datum alignment;
- real radar, bathymetry/sonar, vision/LiDAR, DVL, RF-health, CAN/NMEA-2000/ROS 2, or vendor-specific device integration verified against hardware;
- target-hardware WCET, jitter, overload, scheduling, and watchdog evidence;
- HIL campaigns and controlled water trials;
- field-validated SAFE_HOLD behavior;
- independent replication.

The radar/bathymetric topology, persistent-homology, extreme-value tail, and route-optimization research threads also remain experimental. They should not be moved into the authority path until stronger synthetic ablations and then recorded-data comparisons demonstrate incremental value over simpler baselines.

## Release discipline

The historical Version 1.0 negative findings remain authoritative for that deposit. In particular, the correlated-common-bias failure and lack of validated protection levels are not erased by adding new software. Any future Version 2 deposit should report these modules as new work, freeze a new protocol before evaluating claimed improvements, and distinguish SIL capability from measured operational evidence.
