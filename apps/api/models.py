from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
Scalar = Annotated[float, Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Distribution(str, Enum):
    CONSTANT = "constant"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"


class VariableSpec(StrictModel):
    name: str = Field(pattern=NAME_PATTERN)
    distribution: Distribution
    value: Scalar | None = None
    low: Scalar | None = None
    high: Scalar | None = None
    mode: Scalar | None = None
    unit: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_distribution(self) -> "VariableSpec":
        if self.distribution is Distribution.CONSTANT:
            if self.value is None or any(v is not None for v in (self.low, self.high, self.mode)):
                raise ValueError("constant requires value only")
        elif self.distribution is Distribution.UNIFORM:
            if self.low is None or self.high is None or self.low >= self.high:
                raise ValueError("uniform requires low < high")
            if self.value is not None or self.mode is not None:
                raise ValueError("uniform does not accept value or mode")
        else:
            if self.low is None or self.high is None or self.mode is None:
                raise ValueError("triangular requires low, mode and high")
            if not self.low < self.high or not self.low <= self.mode <= self.high:
                raise ValueError("triangular requires low <= mode <= high and low < high")
            if self.value is not None:
                raise ValueError("triangular does not accept value")
        return self

    def bounds(self) -> tuple[float, float]:
        if self.distribution is Distribution.CONSTANT:
            assert self.value is not None
            return self.value, self.value
        assert self.low is not None and self.high is not None
        return self.low, self.high


class InteractionTerm(StrictModel):
    parameter_x: str = Field(pattern=NAME_PATTERN)
    parameter_y: str = Field(pattern=NAME_PATTERN)
    coefficient: Scalar

    @model_validator(mode="after")
    def validate_distinct_parameters(self) -> "InteractionTerm":
        if self.parameter_x == self.parameter_y:
            raise ValueError("interaction parameters must be distinct")
        return self

    def canonical_pair(self) -> tuple[str, str]:
        return tuple(sorted((self.parameter_x, self.parameter_y)))


class OutcomeSpec(StrictModel):
    name: str = Field(pattern=NAME_PATTERN)
    unit: str | None = Field(default=None, max_length=32)
    intercept: Scalar = 0.0
    coefficients: dict[str, Scalar] = Field(min_length=1, max_length=32)
    interactions: tuple[InteractionTerm, ...] = Field(default=(), max_length=64)


class SimulationModelCreate(StrictModel):
    name: str = Field(pattern=NAME_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    summary: str = Field(min_length=3, max_length=500)
    assumptions: tuple[str, ...] = Field(min_length=1, max_length=32)
    variables: tuple[VariableSpec, ...] = Field(min_length=1, max_length=32)
    outcome: OutcomeSpec

    @model_validator(mode="after")
    def validate_model(self) -> "SimulationModelCreate":
        names = [v.name for v in self.variables]
        if len(names) != len(set(names)):
            raise ValueError("variable names must be unique")
        unknown = set(self.outcome.coefficients) - set(names)
        if unknown:
            raise ValueError(f"unknown coefficient variables: {sorted(unknown)}")
        interaction_pairs = []
        for interaction in self.outcome.interactions:
            interaction_names = {interaction.parameter_x, interaction.parameter_y}
            unknown_interaction = interaction_names - set(names)
            if unknown_interaction:
                raise ValueError(f"unknown interaction variables: {sorted(unknown_interaction)}")
            interaction_pairs.append(interaction.canonical_pair())
        if len(interaction_pairs) != len(set(interaction_pairs)):
            raise ValueError("interaction parameter pairs must be unique")
        if any(not item.strip() for item in self.assumptions):
            raise ValueError("assumptions cannot be blank")
        if len(set(self.assumptions)) != len(self.assumptions):
            raise ValueError("assumptions must be unique")
        return self


class SimulationModel(StrictModel):
    id: str
    model_hash: str
    specification: SimulationModelCreate
    created_at: datetime


class ScenarioCreate(StrictModel):
    model_id: str = Field(min_length=1, max_length=64)
    name: str = Field(pattern=NAME_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    description: str = Field(min_length=3, max_length=500)
    parameter_overrides: dict[str, Scalar] = Field(default_factory=dict, max_length=32)
    assumptions: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_assumptions(self) -> "ScenarioCreate":
        if any(not item.strip() for item in self.assumptions):
            raise ValueError("assumptions cannot be blank")
        if len(set(self.assumptions)) != len(self.assumptions):
            raise ValueError("assumptions must be unique")
        return self


class Scenario(StrictModel):
    id: str
    scenario_hash: str
    model_hash: str
    specification: ScenarioCreate
    created_at: datetime


class SimulationRunCreate(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=-(2**63), le=2**63 - 1)
    iterations: int = Field(ge=1, le=10_000)


class SimulationStatistics(StrictModel):
    count: int
    minimum: float
    maximum: float
    mean: float
    population_stddev: float
    p05: float
    median: float
    p95: float


class SimulationRun(StrictModel):
    id: str
    scenario_id: str
    scenario_hash: str
    seed: int
    iterations: int
    algorithm_version: str
    statistics: SimulationStatistics
    qualification: str
    warning: str
    result_hash: str
    reproducible: bool
    idempotent_replay: bool
    created_at: datetime


class ComparisonQualification(str, Enum):
    ROBUST = "ROBUST"
    FRAGILE = "FRAGILE"
    INSUFFICIENT = "INSUFFICIENT"


class ScenarioComparisonCreate(StrictModel):
    baseline_scenario_id: str = Field(min_length=1, max_length=64)
    stress_scenario_id: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=-(2**63), le=2**63 - 1)
    iterations: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_distinct_scenarios(self) -> "ScenarioComparisonCreate":
        if self.baseline_scenario_id == self.stress_scenario_id:
            raise ValueError("baseline and stress scenarios must be distinct")
        return self


class ComparisonDeltas(StrictModel):
    mean: float
    p05: float
    p95: float
    baseline_downside: float
    stress_downside: float
    downside: float


class ScenarioComparison(StrictModel):
    id: str
    baseline_scenario_id: str
    stress_scenario_id: str
    baseline_scenario_hash: str
    stress_scenario_hash: str
    model_hash: str
    seed: int
    iterations: int
    algorithm_version: str
    baseline_statistics: SimulationStatistics
    stress_statistics: SimulationStatistics
    deltas: ComparisonDeltas
    qualification: ComparisonQualification
    warning: str
    report_hash: str
    reproducible: bool
    common_random_numbers: bool
    idempotent_replay: bool
    created_at: datetime


class SensitivityQualification(str, Enum):
    STABLE = "STABLE"
    SENSITIVE = "SENSITIVE"
    INSUFFICIENT = "INSUFFICIENT"


class Monotonicity(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    FLAT = "FLAT"
    NON_MONOTONIC = "NON_MONOTONIC"


class SensitivityAnalysisCreate(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    parameter: str = Field(pattern=NAME_PATTERN)
    grid: tuple[Scalar, ...] | None = Field(default=None, min_length=2, max_length=21)
    start: Scalar | None = None
    stop: Scalar | None = None
    steps: int | None = Field(default=None, ge=2, le=21)
    seed: int = Field(ge=-(2**63), le=2**63 - 1)
    iterations: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_grid_mode(self) -> "SensitivityAnalysisCreate":
        explicit = self.grid is not None
        generated_values = (self.start, self.stop, self.steps)
        generated = all(value is not None for value in generated_values)
        partial = any(value is not None for value in generated_values) and not generated
        if partial or explicit == generated:
            raise ValueError("provide either grid or start/stop/steps")
        if explicit:
            assert self.grid is not None
            values = tuple(float(value) for value in self.grid)
            if any(left >= right for left, right in zip(values, values[1:])):
                raise ValueError("grid values must be strictly increasing")
        else:
            assert self.start is not None and self.stop is not None
            if self.start >= self.stop:
                raise ValueError("start must be lower than stop")
        return self

    def resolved_grid(self) -> tuple[float, ...]:
        if self.grid is not None:
            return tuple(round(float(value), 12) for value in self.grid)
        assert self.start is not None and self.stop is not None and self.steps is not None
        start, stop = float(self.start), float(self.stop)
        interval = (stop - start) / (self.steps - 1)
        return tuple(round(start + interval * index, 12) for index in range(self.steps - 1)) + (round(stop, 12),)


class SensitivityDeltas(StrictModel):
    mean: float
    p05: float
    p95: float


class SensitivityPoint(StrictModel):
    parameter_value: float
    statistics: SimulationStatistics
    deltas_from_reference: SensitivityDeltas


class SensitivityMetrics(StrictModel):
    mean_range: float = Field(ge=0)
    relative_mean_range: float = Field(ge=0)
    endpoint_slope: float
    elasticity: float | None
    monotonicity: Monotonicity


class SensitivityAnalysis(StrictModel):
    id: str
    scenario_id: str
    scenario_hash: str
    model_hash: str
    parameter: str
    parameter_unit: str | None
    grid: tuple[float, ...]
    seed: int
    iterations: int
    algorithm_version: str
    reference_statistics: SimulationStatistics
    points: tuple[SensitivityPoint, ...]
    metrics: SensitivityMetrics
    qualification: SensitivityQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    common_random_numbers: bool
    idempotent_replay: bool
    created_at: datetime


class InteractionQualification(str, Enum):
    ADDITIVE = "ADDITIVE"
    INTERACTIVE = "INTERACTIVE"
    SENSITIVE = "SENSITIVE"
    INSUFFICIENT = "INSUFFICIENT"


class InteractionSurfaceCreate(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    parameter_x: str = Field(pattern=NAME_PATTERN)
    parameter_y: str = Field(pattern=NAME_PATTERN)
    grid_x: tuple[Scalar, ...] | None = Field(default=None, min_length=2, max_length=7)
    start_x: Scalar | None = None
    stop_x: Scalar | None = None
    steps_x: int | None = Field(default=None, ge=2, le=7)
    grid_y: tuple[Scalar, ...] | None = Field(default=None, min_length=2, max_length=7)
    start_y: Scalar | None = None
    stop_y: Scalar | None = None
    steps_y: int | None = Field(default=None, ge=2, le=7)
    seed: int = Field(ge=-(2**63), le=2**63 - 1)
    iterations: int = Field(ge=1, le=10_000)

    @staticmethod
    def _validate_axis(
        axis: str,
        grid: tuple[Scalar, ...] | None,
        start: Scalar | None,
        stop: Scalar | None,
        steps: int | None,
    ) -> None:
        explicit = grid is not None
        generated_values = (start, stop, steps)
        generated = all(value is not None for value in generated_values)
        partial = any(value is not None for value in generated_values) and not generated
        if partial or explicit == generated:
            raise ValueError(f"provide either grid_{axis} or start_{axis}/stop_{axis}/steps_{axis}")
        if explicit:
            assert grid is not None
            values = tuple(float(value) for value in grid)
            if any(left >= right for left, right in zip(values, values[1:])):
                raise ValueError(f"grid_{axis} values must be strictly increasing")
        else:
            assert start is not None and stop is not None
            if start >= stop:
                raise ValueError(f"start_{axis} must be lower than stop_{axis}")

    @model_validator(mode="after")
    def validate_surface(self) -> "InteractionSurfaceCreate":
        if self.parameter_x == self.parameter_y:
            raise ValueError("parameter_x and parameter_y must be distinct")
        self._validate_axis("x", self.grid_x, self.start_x, self.stop_x, self.steps_x)
        self._validate_axis("y", self.grid_y, self.start_y, self.stop_y, self.steps_y)
        if len(self.resolved_grid_x()) * len(self.resolved_grid_y()) > 49:
            raise ValueError("interaction surface cannot exceed 49 cells")
        return self

    @staticmethod
    def _resolved_axis(
        grid: tuple[Scalar, ...] | None,
        start: Scalar | None,
        stop: Scalar | None,
        steps: int | None,
    ) -> tuple[float, ...]:
        if grid is not None:
            return tuple(round(float(value), 12) for value in grid)
        assert start is not None and stop is not None and steps is not None
        first, last = float(start), float(stop)
        interval = (last - first) / (steps - 1)
        return tuple(round(first + interval * index, 12) for index in range(steps - 1)) + (round(last, 12),)

    def resolved_grid_x(self) -> tuple[float, ...]:
        return self._resolved_axis(self.grid_x, self.start_x, self.stop_x, self.steps_x)

    def resolved_grid_y(self) -> tuple[float, ...]:
        return self._resolved_axis(self.grid_y, self.start_y, self.stop_y, self.steps_y)


class SurfaceCell(StrictModel):
    parameter_x_value: float
    parameter_y_value: float
    statistics: SimulationStatistics
    additive_residual: float


class MainEffect(StrictModel):
    minimum_marginal_mean: float
    maximum_marginal_mean: float
    mean_range: float = Field(ge=0)
    endpoint_slope: float


class WorstCell(StrictModel):
    parameter_x_value: float
    parameter_y_value: float
    mean: float


class InteractionMetrics(StrictModel):
    grand_mean: float
    mean_range: float = Field(ge=0)
    relative_mean_range: float = Field(ge=0)
    x_main_effect: MainEffect
    y_main_effect: MainEffect
    maximum_absolute_additive_residual: float = Field(ge=0)
    relative_interaction_residual: float = Field(ge=0)
    worst_cell: WorstCell


class InteractionSurface(StrictModel):
    id: str
    scenario_id: str
    scenario_hash: str
    model_hash: str
    parameter_x: str
    parameter_y: str
    parameter_x_unit: str | None
    parameter_y_unit: str | None
    grid_x: tuple[float, ...]
    grid_y: tuple[float, ...]
    seed: int
    iterations: int
    algorithm_version: str
    cells: tuple[SurfaceCell, ...]
    metrics: InteractionMetrics
    qualification: InteractionQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    common_random_numbers: bool
    idempotent_replay: bool
    created_at: datetime


class RobustnessQualification(str, Enum):
    ROBUST = "ROBUST"
    UNCERTAINTY_SENSITIVE = "UNCERTAINTY_SENSITIVE"
    LIMIT_BREACH = "LIMIT_BREACH"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class RunMetric(str, Enum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MEAN = "mean"
    POPULATION_STDDEV = "population_stddev"
    P05 = "p05"
    MEDIAN = "median"
    P95 = "p95"


class MetricLimit(StrictModel):
    metric: RunMetric
    minimum_allowed: float | None = Field(default=None, allow_inf_nan=False)
    maximum_allowed: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_bounds(self) -> "MetricLimit":
        if self.minimum_allowed is None and self.maximum_allowed is None:
            raise ValueError("metric limit requires at least one bound")
        if (
            self.minimum_allowed is not None
            and self.maximum_allowed is not None
            and self.minimum_allowed > self.maximum_allowed
        ):
            raise ValueError("minimum_allowed cannot exceed maximum_allowed")
        return self


class UncertaintyDossierCreate(StrictModel):
    run_ids: tuple[str, ...] = Field(min_length=2, max_length=100)
    limits: tuple[MetricLimit, ...] = Field(default=(), max_length=7)

    @model_validator(mode="after")
    def validate_unique_inputs(self) -> "UncertaintyDossierCreate":
        if any(not run_id or len(run_id) > 64 for run_id in self.run_ids):
            raise ValueError("run_ids must contain non-empty identifiers of at most 64 characters")
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("run_ids must be unique")
        metrics = [limit.metric for limit in self.limits]
        if len(set(metrics)) != len(metrics):
            raise ValueError("metric limits must be unique")
        return self

    def canonical_run_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.run_ids))

    def canonical_limits(self) -> tuple[MetricLimit, ...]:
        return tuple(sorted(self.limits, key=lambda item: item.metric.value))


class MetricEnvelope(StrictModel):
    metric: RunMetric
    count: int = Field(ge=1, le=100)
    minimum: float
    maximum: float
    mean: float
    p05: float
    median: float
    p95: float
    width: float = Field(ge=0)
    relative_width: float = Field(ge=0)


class LimitViolation(StrictModel):
    run_id: str
    metric: RunMetric
    value: float
    bound: float
    direction: str


class WorstRun(StrictModel):
    run_id: str
    seed: int
    iterations: int
    p05: float
    mean: float
    violation_count: int = Field(ge=0)


class RankingStability(str, Enum):
    STABLE = "STABLE"
    MIXED = "MIXED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MeanDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    ZERO = "ZERO"


class StabilityAnalysis(StrictModel):
    mean_direction: MeanDirection
    ranking_stability: RankingStability
    mean_median_pairwise_agreement: float | None = Field(default=None, ge=0, le=1)
    comparable_pairs: int = Field(ge=0)


class RobustnessThresholds(StrictModel):
    minimum_run_count: int
    relative_width_threshold: float
    ranking_agreement_threshold: float


class UncertaintyDossier(StrictModel):
    id: str
    run_ids: tuple[str, ...]
    limits: tuple[MetricLimit, ...]
    scenario_id: str | None
    scenario_hash: str | None
    model_hash: str | None
    algorithm_version: str
    verified_run_count: int
    compatibility_errors: tuple[str, ...]
    envelopes: tuple[MetricEnvelope, ...]
    violations: tuple[LimitViolation, ...]
    worst_run: WorstRun | None
    stability: StabilityAnalysis | None
    thresholds: RobustnessThresholds
    qualification: RobustnessQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    order_independent: bool
    idempotent_replay: bool
    created_at: datetime


class ConvergenceQualification(str, Enum):
    CONVERGED = "CONVERGED"
    UNSTABLE = "UNSTABLE"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class ConvergenceDossierCreate(StrictModel):
    run_ids: tuple[str, ...] = Field(min_length=3, max_length=50)

    @model_validator(mode="after")
    def validate_unique_runs(self) -> "ConvergenceDossierCreate":
        if any(not run_id or len(run_id) > 64 for run_id in self.run_ids):
            raise ValueError("run_ids must contain non-empty identifiers of at most 64 characters")
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("run_ids must be unique")
        return self

    def canonical_run_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.run_ids))


class CoreMetricDeviation(StrictModel):
    mean: float = Field(ge=0)
    p05: float = Field(ge=0)
    p95: float = Field(ge=0)
    maximum: float = Field(ge=0)


class ConvergencePoint(StrictModel):
    run_id: str
    iterations: int = Field(ge=1, le=10_000)
    statistics: SimulationStatistics
    absolute_deviation: SensitivityDeltas
    relative_deviation: CoreMetricDeviation


class WorstConvergencePoint(StrictModel):
    run_id: str
    iterations: int = Field(ge=1, le=10_000)
    maximum_relative_deviation: float = Field(ge=0)


class ConvergenceThresholds(StrictModel):
    minimum_distinct_budgets: int
    minimum_reference_iterations: int
    relative_deviation_threshold: float


class ConvergenceDossier(StrictModel):
    id: str
    run_ids: tuple[str, ...]
    scenario_id: str | None
    scenario_hash: str | None
    model_hash: str | None
    seed: int | None
    algorithm_version: str
    reference_run_id: str | None
    verified_run_count: int
    compatibility_errors: tuple[str, ...]
    points: tuple[ConvergencePoint, ...]
    worst_point: WorstConvergencePoint | None
    thresholds: ConvergenceThresholds
    qualification: ConvergenceQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    order_independent: bool
    idempotent_replay: bool
    created_at: datetime


class ScenarioDriftQualification(str, Enum):
    STABLE = "STABLE"
    DRIFTING = "DRIFTING"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class ScenarioDriftDossierCreate(StrictModel):
    run_ids: tuple[str, ...] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def validate_unique_runs(self) -> "ScenarioDriftDossierCreate":
        if any(not run_id or len(run_id) > 64 for run_id in self.run_ids):
            raise ValueError("run_ids must contain non-empty identifiers of at most 64 characters")
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("run_ids must be unique")
        return self

    def canonical_run_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.run_ids))


class ScenarioDriftPoint(StrictModel):
    run_id: str
    scenario_id: str
    scenario_hash: str
    scenario_name: str
    scenario_version: str
    scenario_created_at: datetime
    statistics: SimulationStatistics


class ScenarioDriftTransition(StrictModel):
    from_run_id: str
    to_run_id: str
    from_scenario_id: str
    to_scenario_id: str
    absolute_delta: SensitivityDeltas
    relative_delta: CoreMetricDeviation
    direction: str


class WorstScenarioDriftTransition(StrictModel):
    from_run_id: str
    to_run_id: str
    maximum_relative_delta: float = Field(ge=0)


class ScenarioDriftThresholds(StrictModel):
    minimum_runs: int
    minimum_iterations: int
    relative_drift_threshold: float


class ScenarioDriftDossier(StrictModel):
    id: str
    requested_run_ids: tuple[str, ...]
    ordered_run_ids: tuple[str, ...]
    model_id: str | None
    model_hash: str | None
    seed: int | None
    iterations: int | None
    algorithm_version: str
    verified_run_count: int
    compatibility_errors: tuple[str, ...]
    points: tuple[ScenarioDriftPoint, ...]
    transitions: tuple[ScenarioDriftTransition, ...]
    worst_transition: WorstScenarioDriftTransition | None
    affected_scenario_ids: tuple[str, ...]
    thresholds: ScenarioDriftThresholds
    qualification: ScenarioDriftQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    order_independent: bool
    idempotent_replay: bool
    created_at: datetime


class ScenarioCoverageQualification(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class ScenarioCoverageDossierCreate(StrictModel):
    scenario_ids: tuple[str, ...] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def validate_unique_scenarios(self) -> "ScenarioCoverageDossierCreate":
        if any(not scenario_id or len(scenario_id) > 64 for scenario_id in self.scenario_ids):
            raise ValueError("scenario_ids must contain non-empty identifiers of at most 64 characters")
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        return self

    def canonical_scenario_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.scenario_ids))


class ScenarioCoveragePoint(StrictModel):
    scenario_id: str
    scenario_hash: str
    scenario_name: str
    scenario_version: str
    scenario_created_at: datetime
    overridden_parameters: tuple[str, ...]


class ParameterCoverage(StrictModel):
    parameter: str
    unit: str | None
    lower_bound: float
    upper_bound: float
    override_count: int
    distinct_override_count: int
    minimum_override: float | None
    maximum_override: float | None
    span_ratio: float = Field(ge=0, le=1)
    lower_bound_covered: bool
    upper_bound_covered: bool
    coverage_status: str


class WorstParameterCoverage(StrictModel):
    parameter: str
    coverage_status: str
    span_ratio: float = Field(ge=0, le=1)
    distinct_override_count: int


class ScenarioCoverageThresholds(StrictModel):
    minimum_scenarios: int
    boundary_tolerance: float


class ScenarioCoverageDossier(StrictModel):
    id: str
    requested_scenario_ids: tuple[str, ...]
    ordered_scenario_ids: tuple[str, ...]
    model_id: str | None
    model_hash: str | None
    algorithm_version: str
    verified_scenario_count: int
    compatibility_errors: tuple[str, ...]
    points: tuple[ScenarioCoveragePoint, ...]
    parameter_coverage: tuple[ParameterCoverage, ...]
    missing_parameters: tuple[str, ...]
    partial_parameters: tuple[str, ...]
    fully_covered_parameters: tuple[str, ...]
    worst_parameter: WorstParameterCoverage | None
    thresholds: ScenarioCoverageThresholds
    qualification: ScenarioCoverageQualification
    warning: str
    snapshot_hash: str
    reproducible: bool
    order_independent: bool
    idempotent_replay: bool
    created_at: datetime


class AuditEvent(StrictModel):
    id: int
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict
    previous_hash: str | None
    event_hash: str
    created_at: datetime
