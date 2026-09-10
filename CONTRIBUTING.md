# Contributing

AMEP is a safety-adjacent research codebase. Changes should favor explicit contracts, small reviewable diffs, reproducible tests, and conservative claims.

## Development setup

```bash
python -m pip install -e '.[test]'
pytest
```

## Change requirements

For estimator or supervision changes:

1. preserve the published state semantics unless the change explicitly versions the state model;
2. document frame, unit, timestamp, and uncertainty assumptions at the interface;
3. add or update focused tests for every behavioral change;
4. fail closed on invalid timing, non-finite data, malformed covariance, or unusable navigation constraints;
5. do not convert a SIL result into a field-performance claim;
6. retain material negative findings and document changed assumptions or tuning.

For new sensor adapters, keep raw transport/parsing separate from navigation measurements. An adapter should expose timestamp provenance, coordinate frame, units, covariance/uncertainty, source identity, and health/failure status rather than writing directly into estimator internals.

## Verification before review

```bash
python -m compileall -q src tests examples
pytest
```

A pull request that changes navigation mathematics should explain the model change, equations/Jacobians affected, numerical-stability implications, and the tests or independent calculation used to verify it.
