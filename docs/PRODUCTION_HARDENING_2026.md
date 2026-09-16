# AMEP Production-Hardening Baseline — September 2026

AMEP is being evolved from a maritime SIL research kernel into a modular resilient-PNT assurance architecture that can host platform-specific navigation estimators for multiple autonomous-system classes. This document records the research and standards basis for that evolution and separates implemented software contracts from future evidence gates.

**Scope boundary:** this work addresses navigation estimation, integrity, timing, replay, modular interfaces, degradation, and assurance. It does not implement targeting, weapon employment, or autonomous lethal decision functions.

## 1. Current executable baseline

The current reference estimator is still maritime and horizontal:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

That state model is **not** asserted to be universal. The portable layer is now the contract around it: semantic measurement envelopes, time alignment, backend capability discovery, backend-owned measurement models and frames, source dependency declarations, health, constraint coverage, integrity, mode authority, deterministic replay, and evidence-bounded PNT output.

`EstimatorBackend` no longer exposes a seven-state `H` matrix to runtime. A backend declares the measurement kinds and frames it accepts, owns its state dimension and observation models, and returns a portable `EstimatorSnapshot`. This is the architectural seam for a future 15-state/18-state ESKF, invariant filter, UUV estimator, UAV estimator, UGV estimator, or other platform-specific navigation backend.

## 2. Research and standards findings that drive the architecture

### Confidence and integrity are first-class outputs

Stanford's Navigation and Autonomous Vehicles Lab frames robust multisensor navigation as an accuracy **and confidence** problem and explicitly studies faults in GPS, LiDAR, camera and inertial fusion. Stanford's RAIM/ARAIM work likewise treats redundant measurements and integrity reasoning as separate from simply obtaining a converged estimate.

**AMEP implication:** health, covariance and NIS are necessary but not sufficient. Runtime must know whether evidence is actually diverse, whether independent sources contradict each other, and whether the system has enough integrity evidence to grant autonomy authority.

### Common-cause errors defeat naive multisensor redundancy

AMEP v1.0 demonstrated this directly: mutually consistent biased absolute-position sources can preserve plausible innovations while the state is wrong and covariance is severely overconfident. Contemporary integrity research continues to study multiple-fault hypotheses, heavy-tailed/non-Gaussian errors and explicit integrity bounding rather than relying on a single Gaussian outlier model.

**AMEP implication:** two healthy sensor names do not equal two independent sources. Sources can share a receiver chain, RF environment, clock, map, calibration, preprocessing service, network, compute process, power rail or other common cause.

This tranche therefore models:

- a primary failure domain per source;
- additional shared dependency tokens;
- whether a source receives safety credit;
- the largest pairwise dependency-disjoint source subset.

`GPS_DENIED_RESILIENT` is no longer earned by 7/7 local state coverage alone. Under the reference policy, it requires at least two ONLINE non-GNSS absolute-position sources whose declared integrity-dependency sets are pairwise disjoint. Anything less is downgraded rather than described as resilient.

These declarations are an engineering model, not proof of statistical independence. A real vehicle must derive them from its actual architecture and validate the assumptions.

### Asynchronous and delayed measurements should not be hidden inside callback timing

CMU/MIT/Georgia Tech factor-graph work provides a clean model for multi-rate, asynchronous and delayed navigation measurements and concurrent filtering/smoothing.

**AMEP implication:** the deterministic low-latency estimator should not be distorted to fake delayed-state support. `MeasurementEnvelope` preserves source/receive time, clock domain, uncertainty and provenance; `DelayedMeasurementBackend` is a separate seam for a future fixed-lag or factor-graph path.

### Maritime guidance explicitly requires synchronization, modes, integrity/status and recording

IMO MSC.1/Circ.1575 calls for PNT processing to document operating modes, spatial and temporal synchronization of inputs, dependencies between input and output performance, internal status/integrity monitoring and recordable output. IALA G1180 frames resilient PNT as a system-of-systems problem involving dissimilar sources and failure modes.

**AMEP implication:** source time, receive time, timestamp uncertainty, freshness, dependency configuration, mode, reason, source health, integrity state and replay evidence are architecture-level data—not optional debug information.

### Defense portability favors MOSA-style replaceable modules

The U.S. DoD describes MOSA as a modular, loosely coupled, highly cohesive architecture using accepted and verifiable interfaces. SOSA applies related principles to interoperable sensor/C5ISR components, while FACE defines portable component interfaces for airborne computing environments.

**AMEP implication:** portable interfaces and assurance behavior must be independent of one vehicle's state vector. The current AMEPFilter remains the maritime reference backend; other vehicle classes require their own dynamics and evidence.

### Production software requires software-assurance evidence

NIST SP 800-218 SSDF remains a useful secure-development baseline; NIST published an initial public draft of SSDF 1.2 in December 2025. IEEE 1588-2019 remains an active precision clock synchronization standard for networked measurement/control systems.

**AMEP implication:** deterministic replay, configuration fingerprints, secure development, dependency/SBOM controls, clock provenance and target-hardware timing are production gates, not paperwork after algorithm development.

## 3. Architecture after this tranche

```text
PLATFORM-SPECIFIC SENSOR / BUS ADAPTERS
GNSS | raw INS/IMU | radar | camera/LiDAR | DVL/STW | alt-PNT | time/RF health
                         |
                         v
                 MeasurementEnvelope
 kind + values + covariance + frame + provenance
 source time + receive time + clock domain + uncertainty
                         |
                         v
                     TimeAligner
                         |
                         v
                    SourceRegistry
 role + primary failure domain + shared dependencies + safety credit
               |                              |
               v                              v
 CrossSourceConsistency                 EstimatorBackend
 dependency-disjoint absolute           backend owns state,
 evidence before fusion                 frames & measurement models
               |                              |
               +---------------+--------------+
                               v
                      SensorHealthManager
                               |
                      ConstraintCoverage
                               |
                        IntegrityEngine
      dependency diversity + contradictions + health + rank
                               |
                      NavigationSupervisor
 NOMINAL / GPS_DENIED_RESILIENT / DEGRADED_DEAD_RECKONING / SAFE_HOLD
                               |
                               v
                          PNTSolution
          explicit frame + covariance + health + integrity

Parallel future path:
MeasurementEnvelope -> DelayedMeasurementBackend -> fixed-lag/FGO corrections

Verification path:
ReplayEvent -> DeterministicReplay -> configuration-bound EvidenceLog
```

The assured reference runtime disables legacy direct measurement updates. Measurements must traverse normalized time/provenance/dependency/integrity checks. Compatibility mode remains available only through explicit direct construction of `AMEPRuntime`.

## 4. Implemented hardening rules

1. **Healthy is not independent.** Independence credit uses pairwise-disjoint declared dependencies, not source count.
2. **Contradictory independent absolute fixes are checked before fusion.** The disputed candidate is not fused and integrity latches to `ALERT`; two-source disagreement is not falsely attributed to one source.
3. **Rejected candidates cannot erase integrity evidence.** A later EKF-rejected measurement cannot clear a latched cross-source conflict.
4. **GNSS-denied resilience is deliberately harder to earn.** Full local state coverage with one non-GNSS absolute source remains degraded.
5. **Failure/dependency declarations are assumptions, not proof.** Real system analysis must include RF, clock, map, calibration, power, compute, network and preprocessing common causes.
6. **Runtime does not own estimator state layout.** Semantic measurements and explicit frames cross the backend boundary; the backend owns `H`, state dimension and dynamics.
7. **Protection level remains unavailable.** The covariance containment proxy is not promoted to a certified bound.
8. **Replay is configuration-bound.** Replay evidence contains a SHA-256 fingerprint of the source dependency registry plus deterministic event ordering.
9. **The assured reference path cannot bypass normalization.** Legacy update helpers are compatibility-only and disabled in `build_reference_runtime()`.
10. **Interfaces are portable; vehicle dynamics are not automatically portable.** Each platform estimator must earn its own evidence.

## 5. Production gates, prioritized

### P0 — close before any operational navigation claim

- Recorded real multisensor replay with independently referenced truth and predeclared outage/fault intervals.
- Measured sensor timestamp provenance, synchronization uncertainty and latency on target hardware/network.
- Lever-arm, boresight, datum and coordinate-frame calibration procedures with quantified uncertainty.
- Real bus/transport adapters with corruption, disconnect/reconnect, stale/frozen data, restart and latency testing.
- Target-hardware WCET, jitter, memory/CPU saturation, overload and watchdog response evidence.
- HIL fault injection covering dropout, frozen data, clock skew, frame mistakes, gross faults, slow bias, shared map faults and correlated/common-cause faults.
- Controlled benign-water trials with independent truth, safety observer, abort criteria and complete logs.

### P1 — calibrated inertial mechanization

Build a separate strapdown INS/ESKF backend rather than feeding raw accelerometer specific force directly into the seven-state AMEPFilter. A production-facing state will normally need position, velocity, attitude, gyro bias and accelerometer bias at minimum, with explicit Earth/gravity/frame conventions and sensor calibration. Invariant-filter formulations are candidates to compare, not automatic upgrades.

The new backend boundary exists specifically so this can be introduced without cloning the health/integrity/authority/replay stack.

### P2 — FDE and defensible integrity bounds

- Architecture-derived source-dependence graph.
- Multi-hypothesis/solution-separation or equivalent FDE appropriate to the real measurement set.
- False-alert, missed-detection and time-to-alert metrics.
- Explicit common-cause hypotheses.
- Non-Gaussian/heavy-tail sensitivity.
- Protection/integrity bound only after a declared risk model and empirical calibration with independent truth.

### P3 — delayed/asynchronous estimation

Add a fixed-lag or factor-graph backend for delayed radar/vision/bathymetry constraints, calibration and replay. Keep the real-time estimator independently runnable so optimizer latency or failure cannot silently remove low-latency navigation.

### P4 — platform profiles

Define platform profiles binding:

- estimator backend and prediction-input type;
- accepted frames/datum;
- source registry and dependency model;
- clock synchronization profile;
- sensor/bus adapters;
- constraint/observability model;
- integrity and authority policy;
- performance/integrity requirements;
- safe-state contract.

USV, UUV, UAV and UGV integrations should share envelope, timing, dependency, integrity, replay and evidence contracts while using different dynamics/state models when required.

### P5 — software and supply-chain assurance

- Reproducible dependency locking and SBOM generation.
- Static type/lint/security scanning and dependency vulnerability scanning.
- Signed/tagged release process with immutable evidence manifests.
- NIST SSDF mapping and vulnerability-response procedure.
- Independent review/replay of material positive and negative findings.

## 6. What would impress a serious integrator

Not a larger algorithm list. The credible demonstration is an end-to-end evidence package:

1. Frozen vehicle profile, frames, calibration and source-dependency graph.
2. Real recorded data with independent truth and declared fault intervals.
3. Deterministic replay producing matching configuration/event hashes and outputs on another machine.
4. Equal-sensor EKF/ESKF/FGO comparisons with no privileged preprocessing.
5. Common-cause challenges where AMEP refuses to grant false independence credit.
6. Measured timing/resource behavior on target compute.
7. HIL and water/field trials with traceable requirements, failure logs and abort criteria.
8. A PNT output that explicitly states what it knows, what it does not know, and why autonomy is or is not permitted.

That is the transition from an interesting estimator to an acquisition-relevant navigation subsystem.

## 7. Research/standards references

- Stanford NAV Lab, Robust Navigation and Sensor Fusion: https://navlab.stanford.edu/research/robust-sensor-fusion
- Stanford GPS Lab, RAIM: https://gps.stanford.edu/research/early-gpspnt-research/receiver-autonomous-integrity-monitoring-raim
- Stanford GPS Lab, Advanced RAIM: https://gps.stanford.edu/research/current-and-continuing-gpspnt-research/multi-constellation-gnss/advanced-raim
- Stanford GPS Lab publications: https://gps.stanford.edu/all-gps-lab-published-documents
- Indelman et al., Factor Graph Based Incremental Smoothing in Inertial Navigation Systems: https://publications.ri.cmu.edu/factor-graph-based-incremental-smoothing-in-inertial-navigation-systems
- Williams et al., Concurrent Filtering and Smoothing: https://www.cs.cmu.edu/~kaess/pub/Williams14ijrr.html
- Tian et al., IM-GIV integrity monitoring for GNSS/INS/Vision FGO: https://arxiv.org/abs/2410.22672
- Yan et al., non-Gaussian multi-constellation integrity monitoring: https://arxiv.org/abs/2507.04284
- IMO MSC.1/Circ.1575, Guidelines for shipborne PNT data processing: https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/IMO%20Documents%20related%20to/MSC.1-Circ.1575.pdf
- IALA G1180 Resilient PNT: https://www.iala.int/product/g1180-resilient-pnt/
- DoD MOSA: https://www.cto.mil/sea/mosa/
- The Open Group SOSA: https://www.opengroup.org/sosa/approach
- The Open Group FACE documents and tools: https://www.opengroup.org/face/docsandtools
- NIST SP 800-218 SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218 Rev.1 / SSDF 1.2 initial public draft: https://csrc.nist.gov/pubs/sp/800/218/r1/ipd
- IEEE 1588-2019 Precision Time Protocol: https://standards.ieee.org/ieee/1588/6825/
