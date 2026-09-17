# Validation Status

AMEP uses an evidence ladder. Passing software checks means the implementation satisfies declared software contracts; it does not imply real-vessel navigation performance, certified integrity, or operational safety.

## Release-binding rule

`docs/VALIDATION.md` is the current release-candidate validation record, not a rolling archive of earlier CI counts. For a formal software release, this document must be checked against the exact commit that will be tagged, and the tag must point to the same commit that passed the trusted release CI.

Do not copy forward a test count, source-file count, coverage percentage, Python version, or workflow-run identifier from an earlier `main` snapshot. The preserved files under `docs/validation/` are historical snapshots and are intentionally not authoritative for the current suite.

As of 2026-09-17, the repository has no formal GitHub software release. The post-September-17 hardening tree is therefore release-candidate software, not a backdated extension of the September 10 `0.2.0` metadata.

## Current release-candidate software evidence

The trusted CI path is the repository-specific Windows self-hosted runner `amep-windows-01` with labels `self-hosted`, `windows`, `x64`, and `amep`.

Latest fully observed green `main` baseline before this release-consistency cleanup:

- GitHub Actions run: `35259543210`;
- commit: `ea88f55dc4e2757f63b5134c7d98ced59c9ee8f1`;
- runner: `amep-windows-01`;
- bytecode compilation: PASS;
- Ruff: PASS;
- mypy: PASS;
- Bandit static security scan: PASS;
- assurance-matrix/action-pinning verification: PASS;
- direct runtime dependency audit: PASS;
- CycloneDX SBOM generation: PASS;
- coverage-gated pytest: PASS;
- enforced coverage floor: `75%`.

Current tree inventory after the September 17 SIL gap-closure work includes 27 Python package files under `src/amep1` and 7 pytest modules under `tests`. Those inventory values are descriptive only. The authoritative collected-test count, exact coverage result, resolved environment, and artifact hashes for a formal release must come from CI on the final tagged commit.

The exact measured coverage percentage is deliberately not copied from the earlier 48-test validation snapshot. CI writes the current result to `coverage.xml` and persists the assurance artifacts from the tested tree.

## Covered software contracts

Current automated tests cover, among other software behaviors:

- seven-state water-relative-velocity/current decomposition;
- nonlinear heading-dependent propagation Jacobian checked by finite difference;
- rejection of raw, non-gravity-compensated IMU input by the seven-state reference filter;
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
- schema-labeled covariance and explicit containment-probability output;
- baseline 15-state strapdown ESKF prediction/update behavior;
- compensated coning/sculling, curvature/transport, Earth/transport-frame, and lever-arm-aware ESKF behavior;
- installation lever-arm/boresight contracts and first-order uncertainty propagation;
- dependency-derived single-source and common-cause fault hypotheses;
- integrity-risk bookkeeping and solution-separation research logic;
- generated hypothesis-excluded multi-runtime replay;
- false-alert, missed-detection, and time-to-alert metric calculation;
- checksum-validating selected-sentence NMEA 0183 parsing and bounded byte-stream normalization to `MeasurementEnvelope`.

## Evidence not yet present

The repository does not currently establish evidence for:

- recorded maritime replay with independently referenced truth;
- real active-jamming trials;
- sophisticated spoofing detection;
- real radar/bathymetry/visual/LiDAR/DVL localization or device adapters;
- validated NMEA/IEC 61162, CAN/NMEA-2000, ROS 2, or vendor-specific vessel-bus integration;
- measured platform lever arms, boresights, datum alignment, clock synchronization, latency distributions, or temperature calibration;
- measured IMU noise/bias behavior and device-specific coning/increment semantics;
- a reviewed and physically validated platform dependency/common-cause fault graph;
- target-compute WCET/jitter/overload measurements;
- HIL fault-injection campaigns;
- controlled water trials;
- certified FDE/RAIM or validated integrity/protection levels;
- field-validated `SAFE_HOLD` behavior;
- deployment safety or regulatory conformity;
- independent replication.

## Scientific claim boundary

The AMEP-1 Version 1.0 publication reported improved robustness under disclosed synthetic gross-outlier families, while clean same-sensor accuracy was essentially parity with the comparator. It also reported a severe correlated common-mode position-bias failure in which the covariance-derived containment proxy became substantially overconfident.

Those negative results remain part of the engineering contract. The September 17 software/SIL gap closure does not retroactively change the published Version 1.0 evidence.

## Reproduction

From a clean checkout on a supported Python runtime:

```bash
python -m pip install -e '.[test,qa]'
python -m compileall -q src tests examples scripts
python -m ruff check src tests examples scripts
python -m mypy src/amep1
python -m bandit -q -r src/amep1
python scripts/verify_assurance_contract.py
python -m pytest --cov=amep1 --cov-report=term-missing --cov-report=xml --cov-fail-under=75
```

CI additionally audits the installed direct runtime dependencies, generates a CycloneDX SBOM, and persists `coverage.xml`, `sbom.cdx.json`, resolved-environment capture/hash, runtime dependency input, and assurance-verification output on the self-hosted runner.

## Formal software-release procedure

For the first post-hardening software release:

1. set `pyproject.toml` and `CITATION.cff` to the final non-development software version;
2. add the actual release date to `CITATION.cff`;
3. run the full trusted CI on that exact commit;
4. update this document from that run and exact tree, including the collected test count, measured coverage, runtime versions, and artifact hashes as appropriate;
5. create the Git tag on that tested commit;
6. create the GitHub Release from that tag.

No post-tag documentation edit should be used to make an earlier CI run look like validation of a different tree.
