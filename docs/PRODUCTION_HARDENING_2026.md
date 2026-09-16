# AMEP Production-Hardening Baseline — September 2026

AMEP is being evolved from a maritime SIL research kernel into a modular resilient-PNT component architecture that can be integrated into multiple autonomous-platform classes. This document records the research and standards basis for that evolution and separates implemented software contracts from future evidence gates.

**Scope boundary:** this work addresses navigation estimation, integrity, timing, replay, modular interfaces, degradation, and assurance. It does not implement targeting, weapon employment, or autonomous lethal decision functions.

## 1. Current executable baseline

The real-time kernel remains the published seven-state horizontal maritime estimator:

```text
x = [E, N, Vw_E, Vw_N, C_E, C_N, psi]^T
```

The repository now places explicit contracts around that estimator for measurement provenance, source/receive timestamps, clock domains, covariance, sensor health, local constraint coverage, integrity status, navigation modes, and PNT output. The estimator is still a maritime horizontal research model; the new interfaces are the portable part.

## 2. Research and standards findings that drive the architecture

### Confidence and integrity are first-class outputs

Stanford's Navigation and Autonomous Vehicles Lab frames robust multisensor navigation as an accuracy **and confidence** problem and explicitly studies faults in GPS, LiDAR, camera and inertial fusion. Stanford's RAIM/ARAIM work similarly relies on redundant measurements and explicit integrity reasoning rather than treating a fused position as trustworthy merely because an estimator converged.

AMEP implication: health, covariance and NIS are necessary but not enough. The runtime must track source dependencies, cross-source contradictions, and whether enough genuinely distinct evidence exists to justify a resilient mode.

### Common-cause errors defeat naive multisensor redundancy

AMEP v1.0 already demonstrated this experimentally: mutually consistent biased absolute-position sources can keep innovation statistics plausible while the state is wrong and covariance is overconfident. Recent GNSS integrity research continues to emphasize multiple-fault hypotheses, heavy-tailed/non-Gaussian errors, and explicit bounding rather than assuming one Gaussian fault model.

AMEP implication: two healthy sources do **not** count as two independent sources when they share a receiver, RF path, map, clock, preprocessing chain, compute service, or other common dependency. This tranche therefore adds declared failure domains and refuses full GNSS-denied resilience credit without multiple declared non-GNSS absolute-position domains.

### Asynchronous and delayed measurements should not be hidden inside callback timing

CMU/MIT/Georgia Tech factor-graph work demonstrated a clean model for multi-rate, asynchronous and delayed navigation measurements and for concurrent filtering/smoothing. AMEP's real-time EKF remains deterministic and rejects out-of-order measurements, but its `MeasurementEnvelope` now preserves sufficient time/provenance information for a parallel fixed-lag or factor-graph backend later.

AMEP implication: do not distort the real-time EKF to fake delayed-state support. Keep a low-latency filter and a separate delayed-measurement backend behind a stable interface.

### Maritime guidance explicitly requires synchronization, modes, integrity/status and recording

IMO MSC.1/Circ.1575 calls for PNT processing to document operating modes, spatial and temporal synchronization of inputs, dependencies between input performance and output performance, internal status/integrity monitoring, and output suitable for recording. IALA G1180 treats resilient PNT as a system-of-systems problem using dissimilar sources and failure modes.

AMEP implication: source time, receive time, uncertainty, freshness, mode, reason, source health, integrity state and replay evidence belong in the architecture, not only in debug logs.

### Defense portability favors MOSA-style replaceable modules

The U.S. DoD describes MOSA as a modular, loosely coupled, highly cohesive architecture using accepted and verifiable interfaces. SOSA applies the same principle to interoperable sensor/C5ISR elements. FACE defines portable component interfaces for airborne computing environments and its current published material lists Technical Standard Edition 3.2 as the latest edition.

AMEP implication: the portable product is a set of stable PNT/integrity contracts with platform-specific estimators and adapters behind them. A USV water-current state model must not be mislabeled as a universal UAV/UGV/UUV estimator.

### Production software also needs software-assurance evidence

NIST SP 800-218 SSDF remains a useful secure-development baseline; NIST published an initial public draft of SSDF 1.2 in December 2025. IEEE 1588-2019 remains an active precision clock synchronization standard for networked measurement/control systems.

AMEP implication: release evidence, dependency/configuration fingerprints, secure development practices, deterministic replay, clock provenance and target-hardware timing are production gates, not paperwork after the fact.

## 3. Architecture after this tranche

```text
PLATFORM-SPECIFIC ADAPTERS
GNSS | IMU/INS | radar | camera/LiDAR | DVL/STW | alt-PNT | time/RF health
                 |
                 v
          MeasurementEnvelope
 source + kind + frame + covariance + provenance
 source time + receive time + clock domain + uncertainty
                 |
                 v
             TimeAligner
                 |
                 v
          SourceRegistry
 role + declared failure domain + safety credit
                 |
                 +---------------------+
                 |                     |
                 v                     v
       CrossSourceConsistency     real-time estimator
       independent absolute       EstimatorBackend
       evidence pre-fusion        (AMEPFilter today)
                 |                     |
                 +----------+----------+
                            v
                     SensorHealth
                            |
                     ConstraintCoverage
                            |
                      IntegrityEngine
       dependency diversity + conflicts + health + rank
                            |
                     NavigationSupervisor
      NOMINAL / GPS_DENIED_RESILIENT / DEGRADED / SAFE_HOLD
                            |
                            v
                        PNTSolution

Parallel future path:
MeasurementEnvelope -> DelayedMeasurementBackend -> fixed-lag/FGO corrections

Verification path:
ReplayEvent -> DeterministicReplay -> hash-chained EvidenceLog
```

## 4. New hardening rules

1. **Healthy is not independent.** Failure-domain diversity is separately modeled.
2. **Contradictory independent absolute fixes are checked before fusion.** A conflict is not auto-attributed to either source; the disputed fix is not fused and integrity is latched to ALERT.
3. **GNSS-denied resilience is harder to earn.** Full 7/7 local state coverage with one non-GNSS absolute source is downgraded; the reference policy requires at least two declared non-GNSS absolute failure domains.
4. **Failure domains are declarations, not proof.** A system integrator must derive them from real RF, clock, map, power, compute, network, calibration and preprocessing dependencies.
5. **Protection level remains unavailable.** The covariance containment proxy is still not promoted to a certified integrity bound.
6. **Replay is configuration-bound.** Replay evidence includes a SHA-256 fingerprint of the source dependency registry and a deterministic event order.
7. **Interfaces are portable; dynamics are not automatically portable.** `EstimatorBackend` is the replacement seam. The current AMEPFilter remains maritime/horizontal.

## 5. Production gates, prioritized

### P0 — close before any operational navigation claim

- Recorded real sensor replay with independently referenced truth and predeclared outage/fault windows.
- Measured sensor timestamp provenance and synchronization uncertainty on the target vehicle/network.
- Lever-arm, boresight, datum and coordinate-frame calibration procedures with uncertainty.
- Real bus/transport adapters with disconnect/reconnect, corruption, latency, stale-data and restart testing.
- Target-hardware WCET/jitter/resource measurements and watchdog response under representative load.
- HIL fault injection covering dropout, stale/frozen data, clock skew, frame mistakes, gross faults and correlated/common-cause faults.
- Controlled benign-water trials with independent truth, abort criteria and complete logs.

### P1 — inertial mechanization

Build a separate calibrated strapdown INS/ESKF front end rather than feeding raw specific force into the seven-state AMEPFilter. Minimum production-facing state should normally consider attitude, velocity, position, gyro bias and accelerometer bias, with explicit Earth/gravity/frame conventions. An invariant-filter formulation is a research candidate, not an automatic upgrade; it must win controlled replay/HIL comparisons.

### P2 — fault detection/exclusion and defensible integrity bounds

- Source-dependence graph derived from real architecture.
- Multi-hypothesis/solution-separation or equivalent FDE appropriate to the measurements actually available.
- False-alert, missed-detection and time-to-alert metrics.
- Common-cause fault hypotheses.
- Non-Gaussian/heavy-tail sensitivity.
- Protection/integrity bound only after empirical calibration and a declared risk model.

### P3 — delayed/asynchronous estimation

Add a fixed-lag or factor-graph backend for delayed radar/vision/bathymetry constraints, calibration and replay. Keep the deterministic real-time estimator independently runnable so smoother latency or failure cannot silently remove the low-latency navigation path.

### P4 — platform portability

Define platform profiles that bind:

- estimator backend;
- frames/datum;
- source registry/failure domains;
- time synchronization profile;
- sensor adapters;
- mode/authority policy;
- performance/integrity requirements;
- safe-state contract.

USV, UUV, UAV and UGV profiles should share envelopes, integrity/replay interfaces and assurance tooling while using different dynamics/state models where required.

### P5 — software and supply-chain assurance

- Reproducible dependency locking and SBOM generation.
- Static type/lint/security scanning and dependency vulnerability scanning.
- Signed/tagged release process with immutable evidence manifests.
- NIST SSDF mapping and vulnerability-response procedure.
- Independent review/replay of material positive and negative results.

## 6. What would impress a serious integrator

Not a larger algorithm list. The credible demonstration is an end-to-end evidence package:

1. A frozen vehicle profile and source-dependency graph.
2. Real recorded data with truth and declared fault intervals.
3. Deterministic replay producing the same hashes and outputs on another machine.
4. Side-by-side EKF/ESKF/FGO baselines with equal sensor access.
5. Explicit common-cause tests where the system refuses to overclaim integrity.
6. Timing and resource measurements on target compute.
7. HIL and water/field trials with traceable requirements and failure logs.
8. A PNT output that says what it knows, what it does not know, and why autonomy is or is not permitted.

That is the path from an interesting estimator to an acquisition-relevant navigation subsystem.

## 7. Research/standards references

- Stanford NAV Lab, Robust Navigation and Sensor Fusion: https://navlab.stanford.edu/research/robust-sensor-fusion
- Stanford GPS Lab, RAIM: https://gps.stanford.edu/research/early-gpspnt-research/receiver-autonomous-integrity-monitoring-raim
- Stanford GPS Lab, Advanced RAIM: https://gps.stanford.edu/research/current-and-continuing-gpspnt-research/multi-constellation-gnss/advanced-raim
- Stanford GPS Lab publications (2025–2026 GNSS interference/integrity work): https://gps.stanford.edu/all-gps-lab-published-documents
- Indelman et al., Factor Graph Based Incremental Smoothing in Inertial Navigation Systems: https://publications.ri.cmu.edu/factor-graph-based-incremental-smoothing-in-inertial-navigation-systems
- Williams et al., Concurrent Filtering and Smoothing: https://www.cs.cmu.edu/~kaess/pub/Williams14ijrr.html
- Tian et al., IM-GIV integrity monitoring for GNSS/INS/Vision FGO: https://arxiv.org/abs/2410.22672
- Yan et al., non-Gaussian multi-constellation integrity monitoring: https://arxiv.org/abs/2507.04284
- IMO MSC.1/Circ.1575, Guidelines for shipborne PNT data processing: https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/IMO%20Documents%20related%20to/MSC.1-Circ.1575.pdf
- IALA G1180 Resilient PNT: https://www.iala.int/product/g1180-resilient-pnt/
- DoD MOSA: https://www.cto.mil/sea/mosa/
- The Open Group SOSA: https://www.opengroup.org/sosa/approach
- The Open Group FACE documents and current editions: https://www.opengroup.org/face/docsandtools
- NIST SP 800-218 SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218 Rev.1 / SSDF 1.2 initial public draft: https://csrc.nist.gov/pubs/sp/800/218/r1/ipd
- IEEE 1588-2019 Precision Time Protocol: https://standards.ieee.org/ieee/1588/6825/
