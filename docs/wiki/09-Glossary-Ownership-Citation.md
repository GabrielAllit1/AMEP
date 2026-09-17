# 09 — Glossary, Ownership, and Citation

## Project identity

**Project:** Adaptive Maritime Estimation and PNT (AMEP-1)  
**Organization:** SALT19  
**Full-stack architect:** Gabriel V. Allit  
**AMEP-1 researcher / Version 1.0 author:** Gabriel V. Allit  
**Research DOI:** [10.5281/zenodo.22561851](https://doi.org/10.5281/zenodo.22561851)

AMEP is a SALT19 project. The repository and wiki should preserve the distinction between current software evolution and the frozen Version 1.0 research record.

## Canonical research citation

> Allit, G. (2026). *Adaptive Maritime Estimation and PNT (AMEP-1): A Falsifiable Resilient Multisensor Navigation and Autonomy-Authority Architecture for GNSS-Degraded USV Operation* (Version 1.0). Zenodo. https://doi.org/10.5281/zenodo.22561851

Repository citation metadata is maintained in [`CITATION.cff`](../../CITATION.cff).

## Claim hierarchy

Use the narrowest accurate evidence label when discussing AMEP.

| Label | Meaning |
| --- | --- |
| implemented | code exists |
| unit-tested | a local software contract is tested |
| integration-tested | multiple software components are exercised together |
| SIL-validated | behavior demonstrated in software-in-the-loop conditions |
| replay-validated | behavior reproduced from a declared recording |
| target-hardware validated | timing/resource/fault behavior measured on the actual compute target |
| HIL-validated | real interfaces/hardware exercised with controlled injected faults |
| water-trial validated | behavior demonstrated on a vessel under the declared trial conditions |
| independently replicated | material result reproduced by an independent party/environment |
| certified / approved | only when the relevant external authority has actually granted that status |

Do not collapse these labels into "proven" or "production-ready."

## Glossary

### AMEP
Adaptive Maritime Estimation and PNT. The SALT19 architecture and research project documented here.

### PNT
Position, Navigation, and Timing. The combined capability to determine where the platform is, how it is moving/oriented, and the temporal reference used by navigation systems.

### GNSS
Global Navigation Satellite System. Includes satellite navigation constellations/services used for positioning and timing.

### GNSS-degraded / GNSS-denied
Conditions in which GNSS information is impaired, unavailable, or not trusted for the intended navigation function. These terms do not by themselves identify the cause.

### USV
Uncrewed Surface Vessel.

### EKF
Extended Kalman Filter. A recursive nonlinear state-estimation method based on local linearization.

### ESKF
Error-State Kalman Filter. Common inertial-navigation architecture that estimates errors around a nominal mechanized state. Mentioned as a likely production-facing inertial backend family, not yet provided as validated vessel integration evidence here.

### State vector
The variables estimated together by an estimator. The AMEP maritime reference state is `E, N, Vw_E, Vw_N, C_E, C_N, psi`.

### Water-relative velocity (`Vw`)
Velocity of the vessel through the surrounding water in the local horizontal frame.

### Surface current (`C`)
Estimated velocity of the water/current field in the local horizontal frame.

### Ground velocity (`Vg`)
Velocity relative to the Earth/local frame. In the reference model, `Vg = Vw + C`.

### STW
Speed Through Water. A sensor or derived quantity describing vessel motion relative to the water.

### DVL
Doppler Velocity Log. Depending on mode and environment, can provide velocity relative to the bottom or water mass. Integration must state which semantic quantity is being used.

### NIS
Normalized Innovation Squared. A statistical measure of whether a measurement residual is compatible with the predicted innovation covariance.

### NEES
Normalized Estimation Error Squared. A consistency metric that requires truth/reference error and covariance.

### Innovation gate
A threshold test on measurement residual consistency. Passing or failing a gate is not equivalent to proving a sensor true or false.

### Joseph-form covariance update
A numerically stable covariance-update form used after accepted Kalman updates.

### PSD
Positive semidefinite. A required mathematical property of covariance matrices.

### MeasurementEnvelope
AMEP's normalized measurement contract containing semantic values, covariance, frame, timing, source identity, provenance, and related metadata.

### TimeAligner
AMEP component that normalizes declared clock domains and enforces timing/ordering policy before fusion.

### SourceRegistry
Registry describing source role, clock expectations, provenance, failure domain, shared dependencies, and optional safety credit.

### Failure domain
A physical, software, timing, environmental, or infrastructure dependency that can cause one or more sources to fail together.

### Common-cause fault
A failure mechanism that affects multiple nominally separate sources. Common-cause faults are central to AMEP because agreement between dependent sources can create false confidence.

### Safety credit
An explicit integration decision that allows a source to contribute to integrity-based resilient-navigation authorization. It is conservative and opt-in.

### Cross-source consistency
Pre-fusion comparison of suitable near-synchronous absolute observations to identify contradictions before the candidate mutates estimator state.

### Constraint coverage
AMEP's local information-rank heuristic describing which state variables are constrained by currently healthy sources. It is not a formal proof of nonlinear observability.

### Observability
A systems property describing whether internal state can be inferred from available inputs/outputs over time. AMEP's simplified constraint rank must not be described as full observability proof.

### Integrity
Evidence that the navigation solution is trustworthy enough for a specified operation, including fault-detection assumptions, dependencies, alerting, and risk. Accuracy and integrity are different concepts.

### FDE
Fault Detection and Exclusion. A family of techniques for identifying/excluding faulty information under declared fault hypotheses.

### Protection bound / protection level
A bound intended to support an integrity statement at a declared risk level. AMEP currently does not provide a validated protection bound.

### Containment proxy
AMEP's covariance-derived horizontal radius at a configured probability. It is a diagnostic under covariance assumptions, not a certified protection level.

### `NOMINAL`
Reference navigation mode representing full local constraint coverage with healthy GNSS and no integrity veto.

### `GPS_DENIED_RESILIENT`
Reference mode that requires full non-GNSS coverage plus explicit integrity permission. It cannot be justified by source count/rank alone.

### `DEGRADED_DEAD_RECKONING`
Reference mode representing insufficient evidence for resilient non-GNSS authority but enough information to continue a degraded estimate under policy.

### `SAFE_HOLD`
A software authority/state request indicating normal autonomous navigation authority should not continue. It is not itself a physical station-keeping controller.

### PNTSolution
AMEP's output contract containing navigation state plus schema/covariance labels, source health/age, integrity information, containment diagnostics, and navigation mode.

### DeterministicReplay
Replay path that reproduces online event processing in recorded receive-time order with explicit equal-time sequencing.

### EvidenceLog
Canonical hash-chained software evidence binding replay behavior to behavior-affecting configuration and software identity.

### SIL
Software-in-the-loop. Software components are tested without complete target hardware/physical plant integration.

### HIL
Hardware-in-the-loop. Real hardware/interfaces are exercised against controlled/simulated plant or sensor conditions.

### WCET
Worst-Case Execution Time. A real-time engineering property that must be characterized on the declared target under the relevant assumptions.

### BLOS / LOS
Beyond Line of Sight / Line of Sight communications classes. AMEP treats communications supervision generically and does not implement the RF transport itself.

### MOSA
Modular Open Systems Approach. An acquisition/architecture approach centered on modular design and well-defined interfaces. AMEP's replaceable estimator/interface structure is compatible with modular engineering principles, but this repository does not claim formal MOSA compliance or certification.

## Historical research result boundaries

The Version 1.0 publication should be represented with its full result set:

- clean same-sensor accuracy was essentially parity with the disclosed conventional comparator;
- robust innovation screening substantially reduced error under the disclosed gross-outlier injection families;
- correlated common-mode position bias was a material failure and produced severe covariance overconfidence;
- topology descriptors showed the expected synthetic invariance properties but did not demonstrate incremental bathymetric localization accuracy;
- real recorded maritime replay, HIL, target timing, and controlled water-trial evidence were not included.

## Rights and use boundary

Copyright © 2026 Gabriel V. Allit. All rights reserved, consistent with the repository rights statement. Publication of the research record does not imply permission or certification for safety-critical or operational navigation use.

## Related repository documents

- [`../../README.md`](../../README.md)
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`../GNSS_DENIAL.md`](../GNSS_DENIAL.md)
- [`../PRODUCTION_HARDENING_2026.md`](../PRODUCTION_HARDENING_2026.md)
- [`../VALIDATION.md`](../VALIDATION.md)
- [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)
- [`../../SECURITY.md`](../../SECURITY.md)
