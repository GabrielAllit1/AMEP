# AMEP Software Gap Closure — 17 September 2026

This note updates the software status described by `PRODUCTION_HARDENING_2026.md`. It does **not** change the AMEP-1 Version 1.0 research claim boundary and does not convert the repository into validated operational navigation software.

## Closed at the software-implementation layer

### P1 — inertial mechanization implementation

`src/amep1/strapdown.py` now provides a separate bias-aware local-level strapdown INS/error-state EKF backend behind the existing `EstimatorBackend` boundary.

Implemented software contracts include:

- raw FRD IMU specific-force and body-rate input;
- nominal position, velocity, quaternion attitude, accelerometer bias, and gyro bias;
- 15-state error covariance over position, velocity, attitude error, accelerometer bias, and gyro bias;
- explicit local-NED / body-FRD frame conventions;
- internal gravity compensation rather than feeding raw specific force into the published seven-state estimator;
- bias-corrected strapdown propagation;
- covariance propagation with inertial-noise and bias-random-walk inputs;
- local ENU position/ground-velocity aiding and heading aiding;
- NIS gating, Cholesky solves, Joseph covariance update, and PSD enforcement;
- schema-labeled 15-state covariance output.

The published seven-state AMEP-1 estimator remains intact and independently runnable.

This closes the absence of an inertial backend implementation. It does **not** close IMU calibration, coning/sculling, Earth-rate/transport-rate modeling, scale/misalignment states, lever arms, real-data tuning, or vehicle validation.

### P3 — delayed/asynchronous estimation implementation

`src/amep1/fixed_lag.py` now provides a bounded fixed-lag rewind/replay adapter around a deepcopy-compatible `EstimatorBackend`.

`src/amep1/delayed_runtime.py` adds an explicit delayed-ingestion path that preserves the normal runtime contracts for:

- envelope validity;
- clock-domain normalization;
- transport latency and measurement age;
- timestamp uncertainty;
- source registration/provenance policy;
- pre-fusion cross-source consistency;
- estimator innovation gating;
- source-health accounting;
- source ordering/freshness monotonicity.

Normal `AMEPRuntime.ingest_measurement()` still rejects out-of-order samples. Delayed ordering is relaxed only through `ingest_delayed_measurement()` with `FixedLagBackendAdapter`, and samples outside the configured fixed-lag window fail closed.

This closes the absence of an executable delayed-estimation path. It is not a factor graph, a real-time smoother timing guarantee, or evidence that delayed optimization is safe on target hardware.

## Still open by design

### P0 — operational evidence

Still open: recorded maritime truth replay, measured synchronization/latency budgets, calibrated lever arms/boresight/datums, real vessel-bus fault handling, target-compute timing, HIL fault injection, and controlled water trials.

### P2 — deployment integrity/FDE

Still open: platform-derived fault hypotheses, validated solution-separation or multi-hypothesis FDE, false-alert/missed-detection/time-to-alert characterization, explicit integrity-risk allocation, and an empirically validated protection bound. The software continues to report no validated protection bound.

### P4 — vehicle-specific platform profile

The repository contains research profiles and reusable profile contracts, but no real vessel-specific profile is claimed. A deployment profile must be derived from the actual vehicle, sensors, buses, clocks, calibration, dependency graph, safe state, and performance requirements.

### P5 — release/supply-chain maturity beyond CI

The repository enforces compile, tests, coverage, lint, typing, static security analysis, runtime dependency audit, and CycloneDX SBOM generation. Full reproducible transitive dependency locking, signed formal releases, SSDF traceability, and an operational vulnerability-response process remain release-engineering work.

## Validation snapshot

The software changes above were exercised on the dedicated AMEP self-hosted Windows runner before merge. The preserved machine-readable/human-readable snapshot is `docs/validation/SOFTWARE_GAP_CLOSURE_TEST_RESULTS_2026-09-17.txt`.

The correct maturity statement remains: **research / integration software with production-oriented architecture; not field-validated or certified navigation software.**
