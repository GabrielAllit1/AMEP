# AMEP-1 software assurance case

## Scope

This assurance case applies to the executable AMEP-1 research software and software-in-the-loop integration contracts. It does **not** claim production readiness, certified PNT integrity, vessel-bus conformance, collision-avoidance safety, MASS conformity, or operational maritime performance.

The authoritative maturity label remains **research software / SIL prototype**.

## Assurance argument

AMEP-1 treats navigation authority as a software contract that must remain narrower than the available evidence. The current assurance argument is:

1. Behavior-affecting runtime configuration is validated and explicitly sealed before the default runtime may process predictions or measurements.
2. The sealed configuration is fingerprinted. Post-seal drift blocks processing and forces the runtime toward SAFE_HOLD semantics.
3. Normalized measurement contracts reject non-finite numeric inputs and require symmetric positive-definite covariance before estimator fusion.
4. DEGRADED sources may contribute to the local information-rank heuristic but do not receive ONLINE navigation-authority credit.
5. Non-GNSS resilient-mode credit requires declared safety credit and dependency-disjoint ONLINE absolute sources. Safety-credit declarations require provenance, a finite timestamp-uncertainty budget, and an assurance reference.
6. A dependency-disjoint cross-source absolute-position contradiction is rejected before estimator mutation and remains latched until multiple independent consistent checks satisfy the configured recovery rule.
7. Replay evidence is bound to a configuration/software fingerprint and deterministic hash-chain contract.
8. CI validates requirements-to-test traceability, pins external GitHub Actions to immutable commit SHAs, captures the fully resolved Python environment, and persists assurance artifacts on the designated AMEP self-hosted Windows runner.

The executable traceability source is `assurance/requirements-to-tests.json`. CI runs `scripts/verify_assurance_contract.py` to fail closed if mapped tests disappear or external Actions revert to mutable tags.

## Explicit limitations

This tranche improves software assurance and change control; it does not close the major production gates already identified in AMEP-1 Version 1.0. Recorded maritime replay, real vessel-bus validation, target-hardware deterministic timing evidence, HIL fault campaigns, controlled water trials, calibrated source-independence evidence, and an operational integrity/safety case remain outside the demonstrated evidence.

The CI dependency resolver is also not hermetic: project dependency ranges remain intentionally compatible with supported Python versions. CI now captures the exact resolved environment and its SHA-256 for each run, but this is evidence of what executed rather than a claim that future dependency resolution is identical.

## Review rule

A change that modifies estimator configuration, source dependency declarations, timing policy, integrity policy, consistency recovery semantics, navigation authority, or the requirements-to-test matrix is assurance-relevant. Such changes must keep the traceability verifier green and must not broaden the public claim boundary without new evidence.
