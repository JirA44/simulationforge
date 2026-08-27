from __future__ import annotations

import hashlib
import json
import math

from .models import (
    ComparisonDeltas,
    Distribution,
    InteractionMetrics,
    MainEffect,
    Monotonicity,
    SensitivityDeltas,
    SensitivityMetrics,
    SensitivityPoint,
    SimulationModelCreate,
    SimulationStatistics,
    SurfaceCell,
    WorstCell,
)


ALGORITHM_VERSION = "splitmix64-linear-v1"
COMPARISON_ALGORITHM_VERSION = "splitmix64-linear-paired-v1"
SENSITIVITY_ALGORITHM_VERSION = "splitmix64-linear-sensitivity-v1"
INTERACTION_ALGORITHM_VERSION = "splitmix64-interaction-surface-v1"
MASK_64 = (1 << 64) - 1


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class SplitMix64:
    """Petit PRNG explicite, stable et reproductible; non cryptographique."""

    def __init__(self, seed: int):
        self.state = seed & MASK_64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK_64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK_64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK_64
        return (value ^ (value >> 31)) & MASK_64

    def random(self) -> float:
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))


def _sample(variable, rng: SplitMix64) -> float:
    if variable.distribution is Distribution.CONSTANT:
        return float(variable.value)
    u = rng.random()
    low, high = float(variable.low), float(variable.high)
    if variable.distribution is Distribution.UNIFORM:
        return low + (high - low) * u
    mode = float(variable.mode)
    ratio = (mode - low) / (high - low)
    if u < ratio:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1.0 - u) * (high - low) * (high - mode))


def _rounded(value: float) -> float:
    return round(value, 12)


def _compute_outcome(model: SimulationModelCreate, inputs: dict[str, float]) -> float:
    outcome = float(model.outcome.intercept)
    for name, coefficient in model.outcome.coefficients.items():
        outcome += float(coefficient) * inputs[name]
    for interaction in model.outcome.interactions:
        outcome += (
            float(interaction.coefficient)
            * inputs[interaction.parameter_x]
            * inputs[interaction.parameter_y]
        )
    if not math.isfinite(outcome):
        raise ValueError("computed outcome is not finite")
    return outcome


def _quantile(ordered: list[float], q: float) -> float:
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def simulate(
    model: SimulationModelCreate,
    overrides: dict[str, float],
    seed: int,
    iterations: int,
) -> SimulationStatistics:
    rng = SplitMix64(seed)
    values: list[float] = []
    for _ in range(iterations):
        inputs: dict[str, float] = {}
        for variable in model.variables:
            inputs[variable.name] = (
                float(overrides[variable.name]) if variable.name in overrides else _sample(variable, rng)
            )
        values.append(_compute_outcome(model, inputs))
    ordered = sorted(values)
    mean = math.fsum(values) / iterations
    variance = math.fsum((value - mean) ** 2 for value in values) / iterations
    return SimulationStatistics(
        count=iterations,
        minimum=_rounded(ordered[0]),
        maximum=_rounded(ordered[-1]),
        mean=_rounded(mean),
        population_stddev=_rounded(math.sqrt(variance)),
        p05=_rounded(_quantile(ordered, 0.05)),
        median=_rounded(_quantile(ordered, 0.50)),
        p95=_rounded(_quantile(ordered, 0.95)),
    )


def _statistics(values: list[float]) -> SimulationStatistics:
    ordered = sorted(values)
    count = len(values)
    mean = math.fsum(values) / count
    variance = math.fsum((value - mean) ** 2 for value in values) / count
    return SimulationStatistics(
        count=count,
        minimum=_rounded(ordered[0]),
        maximum=_rounded(ordered[-1]),
        mean=_rounded(mean),
        population_stddev=_rounded(math.sqrt(variance)),
        p05=_rounded(_quantile(ordered, 0.05)),
        median=_rounded(_quantile(ordered, 0.50)),
        p95=_rounded(_quantile(ordered, 0.95)),
    )


def simulate_pair(
    model: SimulationModelCreate,
    baseline_overrides: dict[str, float],
    stress_overrides: dict[str, float],
    seed: int,
    iterations: int,
) -> tuple[SimulationStatistics, SimulationStatistics, ComparisonDeltas]:
    """Recalcule les deux distributions avec les mêmes tirages par variable."""
    rng = SplitMix64(seed)
    baseline_values: list[float] = []
    stress_values: list[float] = []
    for _ in range(iterations):
        baseline_inputs: dict[str, float] = {}
        stress_inputs: dict[str, float] = {}
        for variable in model.variables:
            sampled = _sample(variable, rng)
            baseline_inputs[variable.name] = float(baseline_overrides.get(variable.name, sampled))
            stress_inputs[variable.name] = float(stress_overrides.get(variable.name, sampled))
        baseline_values.append(_compute_outcome(model, baseline_inputs))
        stress_values.append(_compute_outcome(model, stress_inputs))

    baseline_stats = _statistics(baseline_values)
    stress_stats = _statistics(stress_values)
    baseline_downside = max(0.0, baseline_stats.mean - baseline_stats.p05)
    stress_downside = max(0.0, stress_stats.mean - stress_stats.p05)
    deltas = ComparisonDeltas(
        mean=_rounded(stress_stats.mean - baseline_stats.mean),
        p05=_rounded(stress_stats.p05 - baseline_stats.p05),
        p95=_rounded(stress_stats.p95 - baseline_stats.p95),
        baseline_downside=_rounded(baseline_downside),
        stress_downside=_rounded(stress_downside),
        downside=_rounded(stress_downside - baseline_downside),
    )
    return baseline_stats, stress_stats, deltas


def simulate_sensitivity(
    model: SimulationModelCreate,
    scenario_overrides: dict[str, float],
    parameter: str,
    grid: tuple[float, ...],
    seed: int,
    iterations: int,
) -> tuple[SimulationStatistics, tuple[SensitivityPoint, ...], SensitivityMetrics]:
    """Balaye un paramètre avec les mêmes tirages pour la référence et chaque point."""
    rng = SplitMix64(seed)
    reference_values: list[float] = []
    grid_values: list[list[float]] = [[] for _ in grid]
    for _ in range(iterations):
        sampled_inputs: dict[str, float] = {}
        for variable in model.variables:
            sampled_inputs[variable.name] = _sample(variable, rng)

        reference_inputs: dict[str, float] = {}
        for variable in model.variables:
            sampled = sampled_inputs[variable.name]
            reference_inputs[variable.name] = float(scenario_overrides.get(variable.name, sampled))
        reference_values.append(_compute_outcome(model, reference_inputs))
        point_outcomes = []
        for parameter_value in grid:
            point_inputs = dict(reference_inputs)
            point_inputs[parameter] = parameter_value
            point_outcomes.append(_compute_outcome(model, point_inputs))
        for index, value in enumerate(point_outcomes):
            grid_values[index].append(value)

    reference_stats = _statistics(reference_values)
    points: list[SensitivityPoint] = []
    for parameter_value, values in zip(grid, grid_values):
        stats = _statistics(values)
        points.append(
            SensitivityPoint(
                parameter_value=_rounded(parameter_value),
                statistics=stats,
                deltas_from_reference=SensitivityDeltas(
                    mean=_rounded(stats.mean - reference_stats.mean),
                    p05=_rounded(stats.p05 - reference_stats.p05),
                    p95=_rounded(stats.p95 - reference_stats.p95),
                ),
            )
        )

    means = [point.statistics.mean for point in points]
    mean_range = max(means) - min(means)
    scale = max(abs(reference_stats.mean), 1.0)
    slope = (means[-1] - means[0]) / (grid[-1] - grid[0])
    midpoint_parameter = (grid[0] + grid[-1]) / 2.0
    midpoint_mean = (means[0] + means[-1]) / 2.0
    elasticity = None if midpoint_parameter == 0 or midpoint_mean == 0 else slope * midpoint_parameter / midpoint_mean
    tolerance = 1e-12 * max(max(abs(value) for value in means), 1.0)
    changes = [right - left for left, right in zip(means, means[1:])]
    if all(abs(change) <= tolerance for change in changes):
        monotonicity = Monotonicity.FLAT
    elif all(change >= -tolerance for change in changes):
        monotonicity = Monotonicity.INCREASING
    elif all(change <= tolerance for change in changes):
        monotonicity = Monotonicity.DECREASING
    else:
        monotonicity = Monotonicity.NON_MONOTONIC
    metrics = SensitivityMetrics(
        mean_range=_rounded(mean_range),
        relative_mean_range=_rounded(mean_range / scale),
        endpoint_slope=_rounded(slope),
        elasticity=None if elasticity is None else _rounded(elasticity),
        monotonicity=monotonicity,
    )
    return reference_stats, tuple(points), metrics


def simulate_interaction_surface(
    model: SimulationModelCreate,
    scenario_overrides: dict[str, float],
    parameter_x: str,
    parameter_y: str,
    grid_x: tuple[float, ...],
    grid_y: tuple[float, ...],
    seed: int,
    iterations: int,
) -> tuple[tuple[SurfaceCell, ...], InteractionMetrics]:
    """Recalcule chaque cellule avec un seul flux de tirages communs."""
    rng = SplitMix64(seed)
    coordinates = [(x_value, y_value) for x_value in grid_x for y_value in grid_y]
    cell_values: list[list[float]] = [[] for _ in coordinates]
    for _ in range(iterations):
        inputs: dict[str, float] = {}
        for variable in model.variables:
            sampled = _sample(variable, rng)
            inputs[variable.name] = float(scenario_overrides.get(variable.name, sampled))
        for index, (x_value, y_value) in enumerate(coordinates):
            cell_inputs = dict(inputs)
            cell_inputs[parameter_x] = x_value
            cell_inputs[parameter_y] = y_value
            cell_values[index].append(_compute_outcome(model, cell_inputs))

    statistics = [_statistics(values) for values in cell_values]
    means = [item.mean for item in statistics]
    x_count, y_count = len(grid_x), len(grid_y)
    grand_mean = math.fsum(means) / len(means)
    x_marginals = [math.fsum(means[x_index * y_count : (x_index + 1) * y_count]) / y_count for x_index in range(x_count)]
    y_marginals = [math.fsum(means[x_index * y_count + y_index] for x_index in range(x_count)) / x_count for y_index in range(y_count)]

    residuals: list[float] = []
    cells: list[SurfaceCell] = []
    for index, ((x_value, y_value), stats) in enumerate(zip(coordinates, statistics)):
        x_index, y_index = divmod(index, y_count)
        residual = stats.mean - x_marginals[x_index] - y_marginals[y_index] + grand_mean
        residuals.append(residual)
        cells.append(
            SurfaceCell(
                parameter_x_value=_rounded(x_value),
                parameter_y_value=_rounded(y_value),
                statistics=stats,
                additive_residual=_rounded(residual),
            )
        )

    scale = max(abs(grand_mean), 1.0)
    mean_range = max(means) - min(means)
    maximum_residual = max(abs(value) for value in residuals)
    worst_index = min(range(len(means)), key=lambda index: (means[index], coordinates[index]))
    worst_x, worst_y = coordinates[worst_index]
    metrics = InteractionMetrics(
        grand_mean=_rounded(grand_mean),
        mean_range=_rounded(mean_range),
        relative_mean_range=_rounded(mean_range / scale),
        x_main_effect=MainEffect(
            minimum_marginal_mean=_rounded(min(x_marginals)),
            maximum_marginal_mean=_rounded(max(x_marginals)),
            mean_range=_rounded(max(x_marginals) - min(x_marginals)),
            endpoint_slope=_rounded((x_marginals[-1] - x_marginals[0]) / (grid_x[-1] - grid_x[0])),
        ),
        y_main_effect=MainEffect(
            minimum_marginal_mean=_rounded(min(y_marginals)),
            maximum_marginal_mean=_rounded(max(y_marginals)),
            mean_range=_rounded(max(y_marginals) - min(y_marginals)),
            endpoint_slope=_rounded((y_marginals[-1] - y_marginals[0]) / (grid_y[-1] - grid_y[0])),
        ),
        maximum_absolute_additive_residual=_rounded(maximum_residual),
        relative_interaction_residual=_rounded(maximum_residual / scale),
        worst_cell=WorstCell(
            parameter_x_value=_rounded(worst_x),
            parameter_y_value=_rounded(worst_y),
            mean=_rounded(means[worst_index]),
        ),
    )
    return tuple(cells), metrics
