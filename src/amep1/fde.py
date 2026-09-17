from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.stats import chi2

from .math_utils import nearest_psd, symmetrize
from .source_registry import SourceRegistry


@dataclass(frozen=True)
class FaultHypothesis:
    name: str
    excluded_sources: tuple[str, ...]
    dependency_tokens: tuple[str, ...] = ()
    common_cause: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("fault hypothesis name must be non-empty")
        if not self.excluded_sources:
            raise ValueError("fault hypothesis must exclude at least one source")
        if len(set(self.excluded_sources)) != len(self.excluded_sources):
            raise ValueError("excluded_sources must not contain duplicates")


def derive_fault_hypotheses(
    registry: SourceRegistry,
    active_sources: tuple[str, ...] | list[str],
    *,
    safety_credit_only: bool = True,
) -> tuple[FaultHypothesis, ...]:
    """Derive deterministic single-source and declared common-cause hypotheses.

    The result is derived only from the registry's declared dependency graph. It
    is therefore an architecture *model* suitable for SIL FDE campaigns, not a
    verified representation of an actual vessel installation.
    """

    active = tuple(sorted(set(active_sources)))
    descriptors = []
    for source in active:
        descriptor = registry.descriptor(source)
        if descriptor is None:
            continue
        if safety_credit_only and not descriptor.safety_credit:
            continue
        descriptors.append(descriptor)

    hypotheses: list[FaultHypothesis] = []
    for descriptor in descriptors:
        hypotheses.append(
            FaultHypothesis(
                name=f"source:{descriptor.name}",
                excluded_sources=(descriptor.name,),
                dependency_tokens=tuple(sorted(descriptor.integrity_dependencies)),
                common_cause=False,
            )
        )

    by_dependency: dict[str, list[str]] = {}
    for descriptor in descriptors:
        for dependency in descriptor.integrity_dependencies:
            by_dependency.setdefault(dependency, []).append(descriptor.name)
    for dependency, sources in sorted(by_dependency.items()):
        affected = tuple(sorted(set(sources)))
        if len(affected) < 2:
            continue
        hypotheses.append(
            FaultHypothesis(
                name=f"dependency:{dependency}",
                excluded_sources=affected,
                dependency_tokens=(dependency,),
                common_cause=True,
            )
        )

    deduplicated: dict[tuple[str, ...], FaultHypothesis] = {}
    for hypothesis in hypotheses:
        key = hypothesis.excluded_sources
        current = deduplicated.get(key)
        if current is None or (hypothesis.common_cause and not current.common_cause):
            deduplicated[key] = hypothesis
    return tuple(sorted(deduplicated.values(), key=lambda item: item.name))


@dataclass(frozen=True)
class RiskAllocation:
    """Explicit integrity-risk bookkeeping for a declared hypothesis set."""

    total_integrity_risk: float
    hypothesis_allocations: tuple[tuple[str, float], ...]
    unallocated_residual_risk: float = 0.0

    def __post_init__(self) -> None:
        total = float(self.total_integrity_risk)
        residual = float(self.unallocated_residual_risk)
        if not isfinite(total) or not 0.0 < total < 1.0:
            raise ValueError("total_integrity_risk must be finite and in (0,1)")
        if not isfinite(residual) or residual < 0.0:
            raise ValueError("unallocated_residual_risk must be finite and >= 0")
        names: set[str] = set()
        allocated = residual
        for name, probability in self.hypothesis_allocations:
            p = float(probability)
            if not name or name in names:
                raise ValueError("hypothesis allocation names must be unique and non-empty")
            if not isfinite(p) or p <= 0.0:
                raise ValueError("hypothesis allocations must be finite and > 0")
            names.add(name)
            allocated += p
        if allocated > total * (1.0 + 1e-12):
            raise ValueError("allocated integrity risk exceeds total_integrity_risk")

    @classmethod
    def equal(
        cls,
        hypotheses: tuple[FaultHypothesis, ...],
        *,
        total_integrity_risk: float,
        residual_fraction: float = 0.10,
    ) -> "RiskAllocation":
        if not hypotheses:
            raise ValueError("at least one fault hypothesis is required")
        if not isfinite(residual_fraction) or not 0.0 <= residual_fraction < 1.0:
            raise ValueError("residual_fraction must be finite and in [0,1)")
        total = float(total_integrity_risk)
        residual = total * residual_fraction
        each = (total - residual) / len(hypotheses)
        return cls(
            total_integrity_risk=total,
            hypothesis_allocations=tuple((hypothesis.name, each) for hypothesis in hypotheses),
            unallocated_residual_risk=residual,
        )

    def allocation_for(self, hypothesis_name: str) -> float | None:
        return dict(self.hypothesis_allocations).get(hypothesis_name)


@dataclass(frozen=True)
class SolutionCandidate:
    hypothesis: FaultHypothesis
    horizontal_position_m: tuple[float, float]
    horizontal_covariance_m2: tuple[tuple[float, float], tuple[float, float]]

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        position = np.asarray(self.horizontal_position_m, dtype=float).reshape(2)
        covariance = np.asarray(self.horizontal_covariance_m2, dtype=float).reshape(2, 2)
        if not np.all(np.isfinite(position)) or not np.all(np.isfinite(covariance)):
            raise ValueError("solution candidate contains non-finite values")
        if not np.allclose(covariance, covariance.T, rtol=1e-10, atol=1e-12):
            raise ValueError("solution covariance must be symmetric")
        if np.min(np.linalg.eigvalsh(covariance)) <= 0.0:
            raise ValueError("solution covariance must be positive definite")
        return position, covariance


@dataclass(frozen=True)
class SeparationTest:
    hypothesis_name: str
    separation_m: float
    statistic: float
    threshold: float
    alert: bool


@dataclass(frozen=True)
class SolutionSeparationReport:
    alert: bool
    tests: tuple[SeparationTest, ...]
    worst_hypothesis: str | None
    maximum_normalized_statistic: float


class SolutionSeparationMonitor:
    """Evaluate full-solution vs hypothesis-excluded horizontal solutions.

    This monitor intentionally accepts precomputed alternative solutions rather
    than cloning estimator internals. A platform can use an ESKF, UKF, factor
    graph, or another estimator to generate each hypothesis solution while the
    FDE decision remains estimator-independent.
    """

    def __init__(self, *, default_probability: float = 0.999) -> None:
        if not isfinite(default_probability) or not 0.5 < default_probability < 1.0:
            raise ValueError("default_probability must be finite and in (0.5,1)")
        self.default_probability = float(default_probability)

    def evaluate(
        self,
        *,
        primary_position_m: tuple[float, float],
        primary_covariance_m2: tuple[tuple[float, float], tuple[float, float]],
        alternatives: tuple[SolutionCandidate, ...],
        risk_allocation: RiskAllocation | None = None,
    ) -> SolutionSeparationReport:
        primary_position = np.asarray(primary_position_m, dtype=float).reshape(2)
        primary_covariance = np.asarray(primary_covariance_m2, dtype=float).reshape(2, 2)
        if not np.all(np.isfinite(primary_position)) or not np.all(np.isfinite(primary_covariance)):
            raise ValueError("primary solution contains non-finite values")
        if np.min(np.linalg.eigvalsh(symmetrize(primary_covariance))) <= 0.0:
            raise ValueError("primary covariance must be positive definite")

        tests: list[SeparationTest] = []
        worst_name: str | None = None
        worst_ratio = 0.0
        for candidate in alternatives:
            position, covariance = candidate.arrays()
            residual = position - primary_position
            combined = nearest_psd(primary_covariance + covariance, 1e-15)
            factor = cho_factor(combined, lower=True, check_finite=True)
            statistic = float(residual.T @ cho_solve(factor, residual))
            alpha = None if risk_allocation is None else risk_allocation.allocation_for(
                candidate.hypothesis.name
            )
            probability = self.default_probability if alpha is None else 1.0 - alpha
            probability = min(max(probability, 0.5000001), 1.0 - 1e-15)
            threshold = float(chi2.ppf(probability, df=2))
            ratio = statistic / threshold if threshold > 0.0 else float("inf")
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst_name = candidate.hypothesis.name
            tests.append(
                SeparationTest(
                    hypothesis_name=candidate.hypothesis.name,
                    separation_m=float(np.linalg.norm(residual)),
                    statistic=statistic,
                    threshold=threshold,
                    alert=statistic > threshold,
                )
            )
        return SolutionSeparationReport(
            alert=any(test.alert for test in tests),
            tests=tuple(tests),
            worst_hypothesis=worst_name,
            maximum_normalized_statistic=worst_ratio,
        )


@dataclass(frozen=True)
class DetectionTrial:
    fault_present: bool
    alert: bool
    time_to_alert_s: float | None = None

    def __post_init__(self) -> None:
        if self.time_to_alert_s is not None:
            value = float(self.time_to_alert_s)
            if not isfinite(value) or value < 0.0:
                raise ValueError("time_to_alert_s must be finite and >= 0")
            if not self.alert:
                raise ValueError("time_to_alert_s requires alert=True")


@dataclass(frozen=True)
class DetectionMetrics:
    trials: int
    fault_trials: int
    nominal_trials: int
    false_alert_rate: float
    missed_detection_rate: float
    mean_time_to_alert_s: float | None
    p95_time_to_alert_s: float | None


def summarize_detection_trials(trials: tuple[DetectionTrial, ...]) -> DetectionMetrics:
    if not trials:
        raise ValueError("at least one detection trial is required")
    fault = tuple(trial for trial in trials if trial.fault_present)
    nominal = tuple(trial for trial in trials if not trial.fault_present)
    false_alerts = sum(1 for trial in nominal if trial.alert)
    misses = sum(1 for trial in fault if not trial.alert)
    latencies = [
        float(trial.time_to_alert_s)
        for trial in fault
        if trial.alert and trial.time_to_alert_s is not None
    ]
    return DetectionMetrics(
        trials=len(trials),
        fault_trials=len(fault),
        nominal_trials=len(nominal),
        false_alert_rate=(false_alerts / len(nominal) if nominal else 0.0),
        missed_detection_rate=(misses / len(fault) if fault else 0.0),
        mean_time_to_alert_s=(mean(latencies) if latencies else None),
        p95_time_to_alert_s=(float(np.percentile(latencies, 95)) if latencies else None),
    )
