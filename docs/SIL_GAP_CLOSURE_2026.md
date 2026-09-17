# AMEP SIL gap-closure increment — 2026-09-17

This document records engineering work added after the frozen AMEP-1 Version 1.0 research deposit. It does **not** amend the published Version 1.0 results, create a Version 2 claim, or convert AMEP into production-grade navigation software.

## Scope

The increment closes or substantially advances gaps that can be addressed in software-in-the-loop (SIL) without inventing physical evidence:

1. replaceable strapdown inertial-estimation reference implementations, including a compensated local-level mechanization;
2. dependency-derived fault hypotheses, solution-separation/FDE machinery, integrity-risk bookkeeping, detection metrics, and executable hypothesis-excluded replay;
3. lever-arm/boresight/calibration-uncertainty contracts plus lever-arm-aware ESKF observation Jacobians;
4. a checksum-validating NMEA 0183 normalization path from bounded byte streams to `MeasurementEnvelope` records.

The repository maturity label remains **research software / SIL prototype**.

## 1. Strapdown INS / ESKF reference backends

`src/amep1/inertial.py` provides `StrapdownESKF`, a local-ENU nominal-state strapdown implementation with a 15-state error covariance:

```text
nominal: position(3), velocity(3), quaternion(4), accel bias(3), gyro bias(3)
error:   dp(3), dv(3), dtheta(3), dba(3), dbg(3)
```

The baseline implementation includes raw body-frame specific force and angular-rate input, WGS-84 normal gravity, Earth rotation, Coriolis acceleration, inertial-bias states, covariance propagation, quaternion attitude propagation, chi-square innovation screening, Joseph-form updates, covariance reset after attitude-error injection, and schema-labeled snapshots.

`src/amep1/advanced_inertial.py` adds `CompensatedStrapdownESKF`, preserving the same 15-state semantics while adding the remaining SIL mechanization work identified during review:

- previous/current incremental coning compensation;
- sculling and within-interval rotational velocity-increment compensation;
- WGS-84 meridian and prime-vertical curvature radii;
- local ENU transport rate as a function of velocity and curvature;
- Earth-plus-transport navigation-frame attitude compensation;
- Coriolis-plus-transport velocity mechanization;
- first-order transport-rate velocity coupling in the error dynamics;
- local normal-gravity latitude/height gradients;
- second-order state-transition approximation;
- lever-arm-aware position and ground-velocity measurement models;
- attitude-error Jacobians for displaced sensors;
- optional gyro-bias Jacobian coupling when a velocity lever-arm model consumes a raw IMU angular-rate observation.

The coning/sculling coefficients are executable reference coefficients, not proof that they are correct for a particular IMU output mode, sample grouping, vibration environment, or vendor coning-compensation behavior. Real deployment still requires confirmation against the sensor data sheet and recorded high-rate inertial data.

Neither ESKF is presented as a calibrated production INS. Default noise values remain research assumptions and must be replaced by measured IMU characterization before operational use.

## 2. Fault hypotheses, FDE, integrity-risk bookkeeping, and generated subset solutions

`src/amep1/fde.py` provides estimator-independent integrity research primitives:

- `derive_fault_hypotheses(...)` creates deterministic single-source and shared-dependency/common-cause hypotheses from `SourceRegistry` declarations;
- `RiskAllocation` makes total and per-hypothesis integrity-risk bookkeeping explicit;
- `SolutionSeparationMonitor` compares a primary horizontal solution with hypothesis-excluded alternatives;
- `DetectionTrial` / `DetectionMetrics` report false-alert rate, missed-detection rate, and mean/P95 time-to-alert for declared SIL campaigns.

`src/amep1/fde_replay.py` closes the remaining executable-path gap. `MultiHypothesisReplay` now:

1. replays the complete event set through a fresh primary runtime;
2. derives active-source fault hypotheses from the declared source-dependency model unless hypotheses are supplied explicitly;
3. creates a fresh runtime for each hypothesis;
4. removes only measurement events whose sources are excluded by that hypothesis;
5. preserves all prediction events and all non-excluded measurements in the same recorded receive-time/sequence order;
6. evaluates all primary and subset solutions at one shared final time;
7. extracts schema-labeled horizontal covariance from the actual resulting `PNTSolution` objects;
8. creates the `SolutionCandidate` objects automatically;
9. applies the declared risk allocation and solution-separation monitor.

Callers therefore no longer need to manufacture alternative solutions manually for SIL FDE campaigns.

This is still not a validated maritime protection-level implementation. The current solution-separation monitor combines primary and subset covariance and does not claim a certified RAIM cross-covariance model. A real platform still needs a reviewed physical/electrical/software dependency graph, platform-derived fault priors or allocations, frozen alert limits, non-Gaussian/common-cause sensitivity analysis, and empirical validation against independent truth.

## 3. Installation calibration and uncertainty

`src/amep1/installation.py` adds `SensorInstallation`, which records sensor/body frame identities, three-axis lever arm, boresight roll/pitch/yaw, a 6 x 6 calibration covariance, calibration identity/provenance, measured-state declaration, clock domain, nominal latency, and latency uncertainty.

The module implements rigid-body velocity translation from a displaced sensor to the body origin and first-order covariance propagation from measurement, lever-arm/boresight, and optional angular-rate uncertainty.

The compensated ESKF complements that preprocessing path by allowing displaced position and ground-velocity measurements to be modeled directly at the estimator observation layer when the integration chooses not to pre-reduce them to the body origin.

This closes the **software data-model, propagation, and observation-Jacobian** gap. The repository still does not contain measured vessel installation values, survey evidence, temperature dependence, alignment-repeatability data, or an accepted calibration procedure for a specific platform.

## 4. NMEA 0183 reference adapter

`src/amep1/nmea0183.py` adds checksum validation, selected GGA/RMC/HDT/VHW parsing, explicit geodetic-to-local projection ownership, ENU velocity construction, heading normalization, water-relative velocity construction, bounded CR/LF byte-stream framing, and conversion to timestamped/provenance-bearing/covariance-bearing `MeasurementEnvelope` records.

This is a real sentence/byte normalization path, but it does not open or configure a serial port and it is not IEC 61162/NMEA conformance evidence. Electrical interfaces, vendor-specific messages, device configuration, bus loading, failover, and actual vessel integration remain platform work.

## Verification and traceability

`tests/test_sil_gap_closure.py` exercises the first gap-closure increment. `tests/test_final_sil_gaps.py` exercises the deeper mechanization and generated FDE replay path.

The executable assurance matrix now traces:

- `AMEP-INS-001` — baseline strapdown ESKF reference behavior;
- `AMEP-INS-002` — compensated coning/sculling, curvature/transport, and lever-arm-aware observation behavior;
- `AMEP-FDE-001` — dependency-derived FDE/risk bookkeeping and detection metrics;
- `AMEP-FDE-002` — deterministic generation of hypothesis-excluded subset solutions;
- `AMEP-CAL-001` — installation correction and uncertainty propagation;
- `AMEP-ADAPT-001` — NMEA 0183 normalization.

The normal CI gates remain compile, Ruff, mypy, Bandit, assurance-matrix verification, dependency audit, SBOM generation, and coverage-gated pytest on the repository-specific AMEP Windows self-hosted runner.

## Gaps that remain open by evidence class

After this increment, the major remaining gaps are no longer missing SIL architecture primitives. They are evidence and platform-integration gaps:

- recorded real multisensor data with independent truth;
- validated protection levels or certified integrity risk;
- a platform-specific physical dependency/fault tree validated against the actual vessel;
- measured lever arms, boresights, latency distributions, clock synchronization, temperature calibration, and datum alignment;
- real radar, bathymetry/sonar, vision/LiDAR, DVL, RF-health, CAN/NMEA-2000/ROS 2, or vendor-specific device integration verified against hardware;
- target-hardware WCET, jitter, overload, scheduling, and watchdog evidence;
- HIL campaigns and controlled water trials;
- field-validated SAFE_HOLD behavior;
- independent replication.

The radar/bathymetric topology, persistent-homology, extreme-value-tail, and route-optimization research threads also remain experimental. They should not be moved into the authority path until stronger synthetic ablations and then recorded-data comparisons demonstrate incremental value over simpler baselines.

## Release discipline

The historical Version 1.0 negative findings remain authoritative for that deposit. In particular, the correlated-common-bias failure and lack of validated protection levels are not erased by adding new software. Any future Version 2 deposit should report these modules as new work, freeze a new protocol before evaluating claimed improvements, and distinguish SIL capability from measured operational evidence.
