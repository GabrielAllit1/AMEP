# Validation Status

AMEP uses an evidence ladder. Passing software checks means the implementation satisfies declared software contracts; it does not imply real-vessel navigation performance, certified integrity, or operational safety.

## Current software evidence

The current `main` branch is validated on the repository-specific self-hosted Windows runner `amep-windows-01` on machine `PRAISE-GOD`.

Latest validated main run at the time of this document update:

- GitHub Actions run: `35245881364`;
- Python: `3.13.2`;
- bytecode compilation: PASS;
- Ruff: PASS;
- mypy: PASS (`21 source files`);
- Bandit static security scan: PASS;
- direct runtime dependency audit: PASS (`No known vulnerabilities found`);
- CycloneDX SBOM generation: PASS;
- pytest: `48 passed`;
- measured package coverage: `88.55%`;
- enforced coverage floor: `75%`;
- assurance files (`coverage.xml`, `sbom.cdx.json`) persisted on the self-hosted runner under `_work/_artifacts/AMEP/<run-id>`.

The preserved historical validation files under `docs/validation/` remain historical snapshots. They are not descriptions of the current test count or CI state.

## Covered software contracts

Current automated tests cover, among other software behaviors:

- seven-state water-relative-velocity/current decomposition;
- nonlinear heading-dependent propagation Jacobian checked by finite difference;
- rejection of raw, non-gravity-compensated IMU input;
- monotonic-time and maximum prediction-gap enforcement;
- normalized measurement ingestion and clock-domain handling;
- two-phase timing alignment so rejected contracts do not advance source watermarks;
- position, water/ground velocity, current-prior, and heading observation models;
- chi-square rejection of gross innovation outliers;
- symmetric positive-semidefinite covariance preservation;
- source isolation, freshness, and probe-only recovery;
- configurable state-dimension constraint coverage;
- fail-conservative non-GNSS navigation mode behavior when integrity evidence is absent;
- dependency-disjoint safety-credit rules and shared-dependency handling;
- pre-fusion cross-source contradiction blocking;
- deterministic receive-order replay and separate ingest/estimator/fusion accounting;
- configuration/software fingerprinting and evidence-log tamper detection;
- communications timestamp validation and failover;
- host-SIL deadline monitoring;
- fail-closed runtime transition to `SAFE_HOLD` on prediction faults;
- schema-labeled covariance and explicit containment-probability output.

## Evidence not yet present

The repository does not currently establish evidence for:

- recorded maritime replay with independently referenced truth;
- real active-jamming trials;
- sophisticated spoofing detection;
- real radar/bathymetry/visual localization adapters;
- validated NMEA/IEC 61162 or vehicle-bus integration;
- calibrated inertial bias, lever-arm, boresight, datum, and time-synchronization behavior;
- target-compute WCET/jitter/overload measurements;
- HIL fault-injection campaigns;
- controlled water trials;
- certified FDE/RAIM or validated integrity/protection levels;
- deployment safety or regulatory conformity.

## Scientific claim boundary

The AMEP-1 v1.0 publication reported improved robustness under disclosed synthetic gross-outlier families, while clean same-sensor accuracy was essentially parity with the comparator. It also reported a severe correlated common-mode position-bias failure in which the covariance-derived containment proxy became substantially overconfident.

Those negative results remain part of the engineering contract. Current software hardening does not retroactively change the published evidence.

## Reproduction

From a clean checkout on a supported Python runtime:

```bash
python -m pip install -e '.[test,qa]'
python -m compileall -q src tests examples
python -m ruff check src tests examples
python -m mypy src/amep1
python -m bandit -q -r src/amep1
python -m pytest --cov=amep1 --cov-report=term-missing --cov-fail-under=75
```

CI additionally audits the installed direct runtime dependencies and generates a CycloneDX SBOM. A green CI run is software evidence only.