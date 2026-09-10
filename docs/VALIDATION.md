# Validation Status

AMEP uses an evidence ladder. Passing software tests means the implementation satisfies declared software contracts; it does not imply real-vessel navigation performance.

## Current software evidence

The preserved pre-normalization validation snapshot records:

- `21 passed` under pytest;
- successful bytecode compilation of source and tests;
- software/unit/integration scope only.

The normalized repository keeps the same source and test content under the intended `src/amep1/` and `tests/` paths and adds clean-checkout CI.

Covered contracts include:

- seven-state water-relative-velocity/current decomposition;
- nonlinear heading-dependent propagation Jacobian checked by finite difference;
- rejection of raw, non-gravity-compensated IMU input;
- monotonic-time and maximum prediction-gap enforcement;
- position, ground-velocity, current-prior, and heading measurement updates;
- chi-square rejection of gross innovation outliers;
- symmetric positive-semidefinite covariance preservation;
- source isolation, freshness, and probe-only recovery;
- local information-rank navigation modes;
- communications priority/failover;
- host-SIL deadline monitoring;
- fail-closed runtime transition to `SAFE_HOLD` on prediction faults.

## Evidence not yet present

The repository does not currently contain evidence for:

- recorded maritime replay with independent truth;
- real active-jamming trials;
- sophisticated spoofing detection;
- real radar/bathymetry/visual localization adapters;
- actual NMEA/IEC 61162 or vehicle-bus validation;
- calibrated inertial bias/lever-arm/boresight/time-sync behavior;
- target-compute WCET/jitter/overload measurements;
- HIL fault-injection campaigns;
- controlled water trials;
- certified integrity/protection levels;
- deployment safety or regulatory conformity.

## Scientific claim boundary

The AMEP-1 v1.0 publication reported that robust gating materially reduced error under disclosed synthetic gross-outlier families, while clean same-sensor accuracy was essentially parity with the comparator. It also reported a severe failure under correlated common-mode position bias: the covariance-derived containment proxy became substantially overconfident.

Those negative results remain part of the engineering contract. Future improvements should be versioned against them rather than replacing them rhetorically.

## Reproduction

From a clean checkout:

```bash
python -m pip install -e '.[test]'
python -m compileall -q src tests examples
pytest
```

The CI workflow runs the same package/test path on every push and pull request.
