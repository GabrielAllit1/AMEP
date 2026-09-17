# Contributing

AMEP is a safety-adjacent research codebase. Changes should favor explicit contracts, reviewable diffs, reproducible tests, fail-closed behavior, and conservative claims.

## Development setup

```bash
python -m pip install -e '.[test,qa]'
```

## Change requirements

For estimator, integrity, timing, replay, or supervision changes:

1. preserve published state semantics unless the change explicitly versions the state model;
2. document frame, unit, timestamp, covariance, and uncertainty assumptions at the interface;
3. add or update focused tests for every behavioral change and negative path;
4. fail closed on invalid timing, non-finite data, malformed covariance, unknown required source contracts, or unusable navigation constraints;
5. keep source health separate from source independence and document common-cause assumptions;
6. do not convert a software/SIL result into a field-performance or certified-integrity claim;
7. retain material negative findings and document changed assumptions, tuning, or evidence boundaries;
8. update architecture/validation documentation in the same change when executable behavior or public contracts change.

For new sensor adapters, keep raw transport/parsing separate from normalized navigation observations. An adapter should expose source and receive timestamps, clock domain, timestamp uncertainty, coordinate frame/datum, units, covariance/uncertainty, provenance/calibration identity, source identity, and health/failure status rather than writing directly into estimator internals.

A source must not receive integrity safety credit solely because it is a different sensor. Safety-credit changes require a declared failure domain, shared dependencies, provenance enforcement, timestamp-uncertainty budget, and tests demonstrating the intended independence semantics.

## Verification before review

Run the same core checks enforced by CI:

```bash
python -m compileall -q src tests examples
python -m ruff check src tests examples
python -m mypy src/amep1
python -m bandit -q -r src/amep1
python -m pytest --cov=amep1 --cov-report=term-missing --cov-fail-under=75
```

CI additionally audits the installed direct runtime dependencies and generates a CycloneDX SBOM artifact.

A pull request that changes navigation mathematics must explain the model change, equations/Jacobians affected, numerical-stability implications, and the tests or independent calculation used to verify it. A pull request that changes integrity or authority behavior must identify the affected fault assumptions, fail-closed behavior, and mode-transition tests.
