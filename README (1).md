# AMEP-1 production-oriented hardening

This package implements a hardened version of the published AMEP-1 Version 1.0 seven-state horizontal estimator and supervisor contract.

It intentionally **does not** claim field/production validation. The AMEP-1 paper states that recorded maritime evidence, real vessel-bus adapters, target-hardware timing, HIL/water trials, and deployment-grade integrity evidence remain open gates. This code closes software-engineering gaps in the reference skeleton; it cannot close those evidence gates by itself.

## Preserved AMEP-1 state semantics

`x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T`

- `Vw`: water-relative velocity.
- `C`: estimated surface current.
- `Vg = Vw + C`: ground velocity.
- `psi`: heading.

## Important IMU contract

`HorizontalIMUInput.a_fwd_mps2` and `.a_stbd_mps2` must already be **leveled, gravity-compensated horizontal translational acceleration**. Raw accelerometer specific force is rejected by contract. A production navigation stack should normally obtain these increments from a calibrated INS/attitude mechanization with explicit frame, lever-arm, timebase, and bias handling.

## Hardening included

- Restored heading/input Jacobian terms (`da_E/dpsi`, `da_N/dpsi`).
- Explicit monotonic-time and maximum prediction-gap checks.
- Cholesky/linear-solve innovation math; no explicit matrix inverse.
- Joseph covariance update with PSD projection/symmetry enforcement.
- Generic chi-square threshold by measurement dimension.
- Position, water velocity, ground velocity, current-prior, and heading measurement helpers.
- Recoverable isolation path using probe-only innovations.
- Freshness and sliding rejection-fraction supervision.
- Actual diagonalized local information-rank computation matching the paper's heuristic.
- Reachable `DEGRADED_DEAD_RECKONING` mode.
- Operator/autonomy/safety authority gating.
- Structured navigation status.

## Install and test

```bash
python -m pip install -e '.[test]'
pytest -q
```

## Still required before deployment

This repository does **not** close the paper's production gates: recorded-data validation, same-sensor real baseline comparison, vessel-bus adapters, clock/latency provenance, lever-arm/boresight/datum calibration, target-hardware WCET/jitter/watchdog evidence, HIL campaigns, controlled water trials, common-cause integrity architecture, cybersecurity/supply-chain assurance, and independent replication.

## Operational scaffolding

The package also includes:

- `DeadlineWatchdog` for fail-closed timestamp/deadline supervision.
- `CommunicationsSupervisor` for deterministic priority/freshness link failover.
- `build_reference_health_and_constraints()` for the paper's generic source classes.
- Runtime hard-fault latching: timebase or invalid-IMU prediction faults force `SAFE_HOLD` until explicitly cleared by the integration layer.
