from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api import main
from apps.api.engine import simulate
from apps.api.models import (
    InteractionSurfaceCreate,
    MetricLimit,
    ScenarioComparisonCreate,
    ScenarioCreate,
    SensitivityAnalysisCreate,
    SimulationModelCreate,
    SimulationRunCreate,
    UncertaintyDossierCreate,
)
from apps.api.repository import ConflictError, PERMANENT_WARNING, Repository


def model_payload(**changes):
    payload = {
        "name": "demand_model",
        "version": "1.0.0",
        "summary": "Conditional demand model",
        "assumptions": ["Linear relationship is a local approximation"],
        "variables": [
            {"name": "price", "distribution": "uniform", "low": 90, "high": 110, "unit": "EUR"},
            {"name": "trend", "distribution": "triangular", "low": -1, "mode": 0, "high": 2},
        ],
        "outcome": {
            "name": "demand",
            "unit": "units",
            "intercept": 1000,
            "coefficients": {"price": -4, "trend": 25},
        },
    }
    payload.update(changes)
    return payload


def frozen_scenario(repo: Repository):
    model = repo.create_model(SimulationModelCreate.model_validate(model_payload()))
    scenario = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="baseline",
            version="1.0.0",
            description="Baseline bounded scenario",
            parameter_overrides={"trend": 0.25},
            assumptions=("Trend is fixed for this scenario",),
        )
    )
    return model, scenario


def comparison_scenarios(repo: Repository, baseline_price=100.0, stress_price=100.0):
    model = repo.create_model(SimulationModelCreate.model_validate(model_payload()))
    baseline = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="comparison_baseline",
            version="1.0.0",
            description="Frozen comparison baseline",
            parameter_overrides={"price": baseline_price},
        )
    )
    stress = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="comparison_stress",
            version="1.0.0",
            description="Frozen comparison stress",
            parameter_overrides={"price": stress_price},
        )
    )
    return model, baseline, stress


def test_engine_is_deterministic_and_seed_sensitive():
    model = SimulationModelCreate.model_validate(model_payload())
    first = simulate(model, {}, seed=42, iterations=500)
    replay = simulate(model, {}, seed=42, iterations=500)
    other = simulate(model, {}, seed=43, iterations=500)
    assert first == replay
    assert first != other
    assert first.minimum <= first.p05 <= first.median <= first.p95 <= first.maximum


def test_repository_replay_is_idempotent_and_server_computed(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, scenario = frozen_scenario(repo)
    request = SimulationRunCreate(scenario_id=scenario.id, seed=20260822, iterations=1000)
    first = repo.run(request)
    replay = repo.run(request)
    assert replay.id == first.id
    assert replay.result_hash == first.result_hash
    assert replay.statistics == first.statistics
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.reproducible is True
    assert replay.qualification == "DESCRIPTIVE_ONLY"
    assert replay.warning == PERMANENT_WARNING


def test_model_and_scenario_hashes_are_idempotent(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    model, scenario = frozen_scenario(repo)
    same_model = repo.create_model(SimulationModelCreate.model_validate(model_payload()))
    same_scenario = repo.create_scenario(scenario.specification)
    assert same_model.id == model.id
    assert same_model.model_hash == model.model_hash
    assert same_scenario.id == scenario.id
    assert same_scenario.scenario_hash == scenario.scenario_hash


def test_frozen_version_rejects_different_content(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    repo.create_model(SimulationModelCreate.model_validate(model_payload()))
    changed = model_payload(summary="Different frozen content")
    with pytest.raises(ConflictError):
        repo.create_model(SimulationModelCreate.model_validate(changed))


def test_override_must_exist_and_stay_within_model_bounds(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    model = repo.create_model(SimulationModelCreate.model_validate(model_payload()))
    base = {
        "model_id": model.id,
        "name": "invalid_scenario",
        "version": "1.0.0",
        "description": "Invalid bounded scenario",
    }
    with pytest.raises(ValueError, match="unknown overridden"):
        repo.create_scenario(ScenarioCreate(**base, parameter_overrides={"ghost": 1}))
    with pytest.raises(ValueError, match="within"):
        repo.create_scenario(ScenarioCreate(**base, parameter_overrides={"price": 200}))


def test_strict_inputs_reject_client_results_and_extra_fields():
    with pytest.raises(ValidationError):
        SimulationRunCreate(
            scenario_id="scenario-id",
            seed=1,
            iterations=100,
            statistics={"mean": 999},
        )
    with pytest.raises(ValidationError):
        SimulationModelCreate.model_validate({**model_payload(), "prediction": "certain"})


def test_audit_log_is_hash_chained_and_append_only(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    _, scenario = frozen_scenario(repo)
    repo.run(SimulationRunCreate(scenario_id=scenario.id, seed=7, iterations=25))
    events = repo.list_audit_events()
    assert [event.event_type for event in events] == ["MODEL_FROZEN", "SCENARIO_FROZEN", "SIMULATION_COMPUTED"]
    assert events[0].previous_hash is None
    assert events[1].previous_hash == events[0].event_hash
    assert events[2].previous_hash == events[1].event_hash
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("UPDATE audit_events SET event_type='TAMPERED' WHERE id=1")
    connection.close()


def test_health_and_api_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "repo", Repository(tmp_path / "api.db"))
    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "1.0.7", "warning": PERMANENT_WARNING}
    model_response = client.post("/v1/models", json=model_payload())
    assert model_response.status_code == 201
    scenario_response = client.post(
        "/v1/scenarios",
        json={
            "model_id": model_response.json()["id"],
            "name": "api_baseline",
            "version": "1.0.0",
            "description": "API baseline scenario",
            "parameter_overrides": {},
            "assumptions": [],
        },
    )
    assert scenario_response.status_code == 201
    run_response = client.post(
        "/v1/runs",
        json={"scenario_id": scenario_response.json()["id"], "seed": 11, "iterations": 50},
    )
    assert run_response.status_code == 201
    assert run_response.json()["statistics"]["count"] == 50
    assert run_response.json()["qualification"] == "DESCRIPTIVE_ONLY"
    forbidden = client.post(
        "/v1/runs",
        json={"scenario_id": scenario_response.json()["id"], "seed": 11, "iterations": 50, "result_hash": "fake"},
    )
    assert forbidden.status_code == 422


def test_static_and_runtime_openapi_are_versioned_and_path_aligned():
    contract_path = Path(__file__).parents[1] / "packages" / "contracts" / "openapi.yaml"
    static = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime = main.app.openapi()
    assert static["openapi"] == "3.1.0"
    assert static["info"]["version"] == runtime["info"]["version"] == "1.0.7"
    assert set(static["paths"]) == set(runtime["paths"])


def test_stable_comparison_is_robust_and_uses_common_draws(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, baseline, stress = comparison_scenarios(repo)
    report = repo.compare(
        ScenarioComparisonCreate(
            baseline_scenario_id=baseline.id,
            stress_scenario_id=stress.id,
            seed=1234,
            iterations=1000,
        )
    )
    assert report.qualification.value == "ROBUST"
    assert report.common_random_numbers is True
    assert report.baseline_statistics == report.stress_statistics
    assert report.deltas.mean == report.deltas.p05 == report.deltas.p95 == 0.0
    assert report.deltas.downside == 0.0
    assert report.warning == PERMANENT_WARNING


def test_material_stress_is_fragile_and_server_computed(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, baseline, stress = comparison_scenarios(repo, baseline_price=90, stress_price=110)
    report = repo.compare(
        ScenarioComparisonCreate(
            baseline_scenario_id=baseline.id,
            stress_scenario_id=stress.id,
            seed=77,
            iterations=500,
        )
    )
    assert report.qualification.value == "FRAGILE"
    assert report.deltas.mean == -80.0
    assert report.deltas.p05 == -80.0
    assert report.deltas.p95 == -80.0
    assert len(report.report_hash) == 64


def test_comparison_is_insufficient_below_documented_minimum(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, baseline, stress = comparison_scenarios(repo)
    report = repo.compare(
        ScenarioComparisonCreate(
            baseline_scenario_id=baseline.id,
            stress_scenario_id=stress.id,
            seed=1,
            iterations=99,
        )
    )
    assert report.qualification.value == "INSUFFICIENT"
    assert report.baseline_statistics.count == report.stress_statistics.count == 99


def test_comparison_rejects_incompatible_models(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    first = repo.create_model(SimulationModelCreate.model_validate(model_payload(name="first_model")))
    second = repo.create_model(SimulationModelCreate.model_validate(model_payload(name="second_model")))
    baseline = repo.create_scenario(
        ScenarioCreate(
            model_id=first.id,
            name="baseline_first",
            version="1.0.0",
            description="Baseline on the first model",
        )
    )
    stress = repo.create_scenario(
        ScenarioCreate(
            model_id=second.id,
            name="stress_second",
            version="1.0.0",
            description="Stress on the second model",
        )
    )
    with pytest.raises(ValueError, match="same frozen model"):
        repo.compare(
            ScenarioComparisonCreate(
                baseline_scenario_id=baseline.id,
                stress_scenario_id=stress.id,
                seed=1,
                iterations=100,
            )
        )


def test_comparison_replay_is_idempotent_and_report_is_immutable(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    _, baseline, stress = comparison_scenarios(repo)
    request = ScenarioComparisonCreate(
        baseline_scenario_id=baseline.id,
        stress_scenario_id=stress.id,
        seed=20260822,
        iterations=250,
    )
    first = repo.compare(request)
    replay = repo.compare(request)
    assert replay.id == first.id
    assert replay.report_hash == first.report_hash
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE scenario_comparisons SET qualification='FRAGILE' WHERE id=?", (first.id,))
    connection.close()


def test_comparison_input_forbids_client_results_and_same_scenario():
    with pytest.raises(ValidationError):
        ScenarioComparisonCreate(
            baseline_scenario_id="baseline",
            stress_scenario_id="stress",
            seed=1,
            iterations=100,
            deltas={"mean": 999},
        )
    with pytest.raises(ValidationError, match="must be distinct"):
        ScenarioComparisonCreate(
            baseline_scenario_id="same",
            stress_scenario_id="same",
            seed=1,
            iterations=100,
        )


def test_comparison_api_flow_and_audit(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "api-comparison.db")
    _, baseline, stress = comparison_scenarios(repository)
    monkeypatch.setattr(main, "repo", repository)
    client = TestClient(main.app)
    response = client.post(
        "/v1/comparisons",
        json={
            "baseline_scenario_id": baseline.id,
            "stress_scenario_id": stress.id,
            "seed": 8,
            "iterations": 100,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["qualification"] == "ROBUST"
    assert client.get(f"/v1/comparisons/{body['id']}").status_code == 200
    assert len(client.get("/v1/comparisons").json()) == 1
    assert repository.list_audit_events()[-1].event_type == "SCENARIOS_COMPARED"


def sensitivity_request(scenario_id: str, **changes) -> SensitivityAnalysisCreate:
    payload = {
        "scenario_id": scenario_id,
        "parameter": "price",
        "grid": [99, 100, 101],
        "seed": 20260822,
        "iterations": 500,
    }
    payload.update(changes)
    return SensitivityAnalysisCreate.model_validate(payload)


def test_narrow_parametric_sweep_is_stable_and_reproducible(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, scenario = frozen_scenario(repo)
    result = repo.analyze_sensitivity(sensitivity_request(scenario.id))
    assert result.qualification.value == "STABLE"
    assert result.common_random_numbers is True
    assert result.reproducible is True
    assert result.grid == (99.0, 100.0, 101.0)
    assert result.metrics.mean_range == 8.0
    assert result.metrics.endpoint_slope == -4.0
    assert result.metrics.monotonicity.value == "DECREASING"
    assert result.points[1].statistics.count == 500
    assert result.warning == PERMANENT_WARNING


def test_wide_parametric_sweep_is_sensitive_and_server_computed(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, scenario = frozen_scenario(repo)
    result = repo.analyze_sensitivity(
        sensitivity_request(scenario.id, grid=[90, 100, 110], seed=77, iterations=1000)
    )
    assert result.qualification.value == "SENSITIVE"
    assert result.metrics.mean_range == 80.0
    assert result.metrics.relative_mean_range > 0.05
    assert result.points[0].statistics.mean - result.points[-1].statistics.mean == 80.0
    assert len(result.snapshot_hash) == 64


def test_sensitivity_is_insufficient_below_documented_minimum(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, scenario = frozen_scenario(repo)
    result = repo.analyze_sensitivity(sensitivity_request(scenario.id, iterations=99))
    assert result.qualification.value == "INSUFFICIENT"
    assert all(point.statistics.count == 99 for point in result.points)


def test_sensitivity_rejects_out_of_bounds_and_incompatible_parameter(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, scenario = frozen_scenario(repo)
    with pytest.raises(ValueError, match="must be within"):
        repo.analyze_sensitivity(sensitivity_request(scenario.id, grid=[80, 100]))
    with pytest.raises(ValueError, match="unknown sensitivity parameter"):
        repo.analyze_sensitivity(sensitivity_request(scenario.id, parameter="ghost", grid=[0, 1]))

    payload = model_payload(name="unused_parameter_model")
    payload["outcome"]["coefficients"] = {"price": -4}
    model = repo.create_model(SimulationModelCreate.model_validate(payload))
    unused = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="unused_parameter_scenario",
            version="1.0.0",
            description="Scenario with an unused parameter",
        )
    )
    with pytest.raises(ValueError, match="incompatible"):
        repo.analyze_sensitivity(sensitivity_request(unused.id, parameter="trend", grid=[-1, 0, 1]))


def test_sensitivity_replay_is_idempotent_and_snapshot_is_immutable(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    _, scenario = frozen_scenario(repo)
    first = repo.analyze_sensitivity(sensitivity_request(scenario.id))
    replay = repo.analyze_sensitivity(
        sensitivity_request(scenario.id, grid=None, start=99, stop=101, steps=3)
    )
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert repo.get_sensitivity(first.id).snapshot_hash == first.snapshot_hash
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE sensitivity_analyses SET qualification='SENSITIVE' WHERE id=?", (first.id,))
    connection.close()


def test_sensitivity_input_is_strict_and_grid_is_bounded():
    with pytest.raises(ValidationError):
        SensitivityAnalysisCreate(
            scenario_id="scenario",
            parameter="price",
            grid=(90, 100, 110),
            seed=1,
            iterations=100,
            qualification="STABLE",
        )
    with pytest.raises(ValidationError):
        SensitivityAnalysisCreate(
            scenario_id="scenario",
            parameter="price",
            start=90,
            stop=110,
            steps=22,
            seed=1,
            iterations=100,
        )
    with pytest.raises(ValidationError, match="strictly increasing"):
        SensitivityAnalysisCreate(
            scenario_id="scenario",
            parameter="price",
            grid=(100, 99),
            seed=1,
            iterations=100,
        )


def test_sensitivity_api_info_and_audit(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "api-sensitivity.db")
    _, scenario = frozen_scenario(repository)
    monkeypatch.setattr(main, "repo", repository)
    client = TestClient(main.app)
    info = client.get("/info")
    assert info.status_code == 200
    assert info.json()["version"] == "1.0.7"
    response = client.post(
        "/v1/sensitivities",
        json={
            "scenario_id": scenario.id,
            "parameter": "price",
            "start": 99,
            "stop": 101,
            "steps": 3,
            "seed": 8,
            "iterations": 100,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["qualification"] == "STABLE"
    assert client.get(f"/v1/sensitivities/{body['id']}").status_code == 200
    assert len(client.get("/v1/sensitivities").json()) == 1
    assert repository.list_audit_events()[-1].event_type == "SENSITIVITY_ANALYZED"


def surface_request(scenario_id: str, **changes) -> InteractionSurfaceCreate:
    payload = {
        "scenario_id": scenario_id,
        "parameter_x": "price",
        "parameter_y": "trend",
        "grid_x": [99, 101],
        "grid_y": [0, 0.1],
        "seed": 20260822,
        "iterations": 500,
    }
    payload.update(changes)
    return InteractionSurfaceCreate.model_validate(payload)


def interactive_model_payload(coefficient: float = 10.0):
    payload = model_payload(name="interactive_demand_model")
    payload["outcome"]["interactions"] = [
        {"parameter_x": "price", "parameter_y": "trend", "coefficient": coefficient}
    ]
    return payload


def test_small_additive_surface_is_reproducible_and_reports_main_effects(tmp_path):
    repo = Repository(tmp_path / "surface.db")
    model, scenario = frozen_scenario(repo)
    result = repo.analyze_interaction_surface(surface_request(scenario.id))
    assert result.qualification.value == "ADDITIVE"
    assert result.common_random_numbers is True
    assert result.reproducible is True
    assert result.parameter_x_unit == "EUR"
    assert result.parameter_y_unit is None
    assert len(result.cells) == 4
    assert result.metrics.maximum_absolute_additive_residual == 0.0
    assert result.metrics.x_main_effect.endpoint_slope == -4.0
    assert result.metrics.y_main_effect.endpoint_slope == 25.0
    assert result.model_hash == model.model_hash
    assert result.warning == PERMANENT_WARNING


def test_wide_additive_surface_is_sensitive(tmp_path):
    repo = Repository(tmp_path / "surface.db")
    _, scenario = frozen_scenario(repo)
    result = repo.analyze_interaction_surface(
        surface_request(scenario.id, grid_x=[90, 100, 110], grid_y=[-1, 0.5, 2], seed=7, iterations=1000)
    )
    assert result.qualification.value == "SENSITIVE"
    assert result.metrics.relative_mean_range > 0.05
    assert result.metrics.relative_interaction_residual == 0.0
    assert result.metrics.worst_cell.parameter_x_value == 110.0
    assert result.metrics.worst_cell.parameter_y_value == -1.0


def test_nonlinear_surface_is_interactive_and_residual_is_server_computed(tmp_path):
    repo = Repository(tmp_path / "surface.db")
    model = repo.create_model(SimulationModelCreate.model_validate(interactive_model_payload()))
    scenario = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="interactive_surface",
            version="1.0.0",
            description="Scenario for a two parameter interaction surface",
        )
    )
    result = repo.analyze_interaction_surface(
        surface_request(scenario.id, grid_x=[90, 100, 110], grid_y=[-1, 0, 1], seed=99, iterations=500)
    )
    assert result.qualification.value == "INTERACTIVE"
    assert result.metrics.maximum_absolute_additive_residual == 100.0
    assert result.metrics.relative_interaction_residual > 0.05
    assert any(cell.additive_residual != 0 for cell in result.cells)
    assert len(result.snapshot_hash) == 64


def test_interaction_surface_is_insufficient_below_fixed_threshold(tmp_path):
    repo = Repository(tmp_path / "surface.db")
    _, scenario = frozen_scenario(repo)
    result = repo.analyze_interaction_surface(surface_request(scenario.id, iterations=99))
    assert result.qualification.value == "INSUFFICIENT"
    assert all(cell.statistics.count == 99 for cell in result.cells)


def test_interaction_surface_rejects_unknown_incompatible_and_out_of_bounds_parameters(tmp_path):
    repo = Repository(tmp_path / "surface.db")
    _, scenario = frozen_scenario(repo)
    with pytest.raises(ValueError, match="unknown interaction parameter"):
        repo.analyze_interaction_surface(surface_request(scenario.id, parameter_y="ghost"))
    with pytest.raises(ValueError, match="must be within"):
        repo.analyze_interaction_surface(surface_request(scenario.id, grid_x=[80, 100]))

    payload = model_payload(name="surface_unused_parameter")
    payload["outcome"]["coefficients"] = {"price": -4}
    model = repo.create_model(SimulationModelCreate.model_validate(payload))
    unused = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="surface_unused",
            version="1.0.0",
            description="Scenario with one output-incompatible parameter",
        )
    )
    with pytest.raises(ValueError, match="incompatible"):
        repo.analyze_interaction_surface(surface_request(unused.id))


def test_interaction_surface_replay_is_idempotent_and_immutable(tmp_path):
    database = tmp_path / "surface.db"
    repo = Repository(database)
    _, scenario = frozen_scenario(repo)
    first = repo.analyze_interaction_surface(surface_request(scenario.id))
    replay = repo.analyze_interaction_surface(
        surface_request(
            scenario.id,
            grid_x=None,
            start_x=99,
            stop_x=101,
            steps_x=2,
            grid_y=None,
            start_y=0,
            stop_y=0.1,
            steps_y=2,
        )
    )
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert repo.get_interaction_surface(first.id).snapshot_hash == first.snapshot_hash
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE interaction_surfaces SET qualification='SENSITIVE' WHERE id=?", (first.id,))
    connection.close()


def test_interaction_surface_input_is_strict_distinct_and_bounded_to_seven_per_axis():
    with pytest.raises(ValidationError):
        InteractionSurfaceCreate(
            scenario_id="scenario",
            parameter_x="price",
            parameter_y="trend",
            grid_x=(90, 100),
            grid_y=(-1, 1),
            seed=1,
            iterations=100,
            cells=[],
        )
    with pytest.raises(ValidationError, match="must be distinct"):
        InteractionSurfaceCreate(
            scenario_id="scenario",
            parameter_x="price",
            parameter_y="price",
            grid_x=(90, 100),
            grid_y=(90, 100),
            seed=1,
            iterations=100,
        )
    with pytest.raises(ValidationError):
        InteractionSurfaceCreate(
            scenario_id="scenario",
            parameter_x="price",
            parameter_y="trend",
            grid_x=(90, 91, 92, 93, 94, 95, 96, 97),
            grid_y=(-1, 1),
            seed=1,
            iterations=100,
        )


def test_interaction_terms_are_strict_and_unique():
    payload = interactive_model_payload()
    payload["outcome"]["interactions"].append(
        {"parameter_x": "trend", "parameter_y": "price", "coefficient": 1}
    )
    with pytest.raises(ValidationError, match="must be unique"):
        SimulationModelCreate.model_validate(payload)
    payload = interactive_model_payload()
    payload["outcome"]["interactions"][0]["server_result"] = 999
    with pytest.raises(ValidationError):
        SimulationModelCreate.model_validate(payload)


def test_interaction_surface_api_info_and_audit(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "surface-api.db")
    _, scenario = frozen_scenario(repository)
    monkeypatch.setattr(main, "repo", repository)
    client = TestClient(main.app)
    info = client.get("/info").json()
    assert info["version"] == "1.0.7"
    assert info["release"] == "V1.07"
    assert "interaction_surface" in info["capabilities"]
    response = client.post(
        "/v1/interaction-surfaces",
        json={
            "scenario_id": scenario.id,
            "parameter_x": "price",
            "parameter_y": "trend",
            "start_x": 99,
            "stop_x": 101,
            "steps_x": 2,
            "start_y": 0,
            "stop_y": 0.1,
            "steps_y": 2,
            "seed": 8,
            "iterations": 100,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["qualification"] == "ADDITIVE"
    assert client.get(f"/v1/interaction-surfaces/{body['id']}").status_code == 200
    assert len(client.get("/v1/interaction-surfaces").json()) == 1
    assert repository.list_audit_events()[-1].event_type == "INTERACTION_SURFACE_ANALYZED"


def persisted_runs(repo: Repository, count: int, iterations: int = 1000, seed_start: int = 100):
    model, scenario = frozen_scenario(repo)
    runs = [
        repo.run(SimulationRunCreate(scenario_id=scenario.id, seed=seed_start + index, iterations=iterations))
        for index in range(count)
    ]
    return model, scenario, runs


def test_uncertainty_dossier_recalculates_runs_and_is_robust(tmp_path):
    repo = Repository(tmp_path / "dossier.db")
    model, scenario, runs = persisted_runs(repo, 4, iterations=1000)
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(run_ids=tuple(run.id for run in runs))
    )
    assert dossier.qualification.value == "ROBUST"
    assert dossier.verified_run_count == 4
    assert dossier.scenario_id == scenario.id
    assert dossier.model_hash == model.model_hash
    assert dossier.compatibility_errors == ()
    assert len(dossier.envelopes) == 7
    assert dossier.worst_run is not None
    assert dossier.stability is not None
    assert dossier.reproducible is True
    assert dossier.order_independent is True


def test_uncertainty_dossier_detects_uncertainty_sensitivity(tmp_path):
    repo = Repository(tmp_path / "dossier.db")
    _, _, runs = persisted_runs(repo, 4, iterations=1, seed_start=1)
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(run_ids=tuple(run.id for run in runs))
    )
    assert dossier.qualification.value == "UNCERTAINTY_SENSITIVE"
    core = {item.metric.value: item for item in dossier.envelopes}
    assert max(core[name].relative_width for name in ("mean", "p05", "p95")) > 0.05


def test_uncertainty_dossier_reports_limit_breaches_and_worst_run(tmp_path):
    repo = Repository(tmp_path / "dossier.db")
    _, _, runs = persisted_runs(repo, 3, iterations=250)
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(
            run_ids=tuple(run.id for run in runs),
            limits=(MetricLimit(metric="mean", minimum_allowed=10_000),),
        )
    )
    assert dossier.qualification.value == "LIMIT_BREACH"
    assert len(dossier.violations) == 3
    assert all(item.direction == "BELOW_MINIMUM" for item in dossier.violations)
    assert dossier.worst_run is not None
    assert dossier.worst_run.violation_count == 1


def test_uncertainty_dossier_is_insufficient_with_only_two_runs(tmp_path):
    repo = Repository(tmp_path / "dossier.db")
    _, _, runs = persisted_runs(repo, 2)
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(run_ids=tuple(run.id for run in runs))
    )
    assert dossier.qualification.value == "INSUFFICIENT"
    assert dossier.thresholds.minimum_run_count == 3


def test_uncertainty_dossier_freezes_incompatible_scenarios(tmp_path):
    repo = Repository(tmp_path / "dossier.db")
    model, first = frozen_scenario(repo)
    second = repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="another_scenario",
            version="1.0.0",
            description="A distinct frozen scenario",
            parameter_overrides={"trend": 0.5},
        )
    )
    first_run = repo.run(SimulationRunCreate(scenario_id=first.id, seed=1, iterations=100))
    second_run = repo.run(SimulationRunCreate(scenario_id=second.id, seed=2, iterations=100))
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(run_ids=(first_run.id, second_run.id))
    )
    assert dossier.qualification.value == "INCOMPATIBLE"
    assert "runs must reference the same frozen scenario" in dossier.compatibility_errors
    assert dossier.envelopes == ()
    assert dossier.worst_run is None


def test_uncertainty_dossier_detects_a_corrupted_persisted_hash(tmp_path):
    database = tmp_path / "dossier.db"
    repo = Repository(database)
    _, _, runs = persisted_runs(repo, 3)
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER simulation_runs_no_update")
    connection.execute("UPDATE simulation_runs SET result_hash=? WHERE id=?", ("0" * 64, runs[0].id))
    connection.commit()
    connection.close()
    dossier = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(run_ids=tuple(run.id for run in runs))
    )
    assert dossier.qualification.value == "INCOMPATIBLE"
    assert any("result hash mismatch" in item for item in dossier.compatibility_errors)
    assert dossier.verified_run_count == 2


def test_uncertainty_dossier_is_order_independent_idempotent_and_immutable(tmp_path):
    database = tmp_path / "dossier.db"
    repo = Repository(database)
    _, _, runs = persisted_runs(repo, 3)
    first = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(
            run_ids=tuple(run.id for run in runs),
            limits=(MetricLimit(metric="p05", minimum_allowed=0), MetricLimit(metric="mean", maximum_allowed=1000)),
        )
    )
    replay = repo.create_uncertainty_dossier(
        UncertaintyDossierCreate(
            run_ids=tuple(run.id for run in reversed(runs)),
            limits=(MetricLimit(metric="mean", maximum_allowed=1000), MetricLimit(metric="p05", minimum_allowed=0)),
        )
    )
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE uncertainty_dossiers SET qualification='ROBUST' WHERE id=?", (first.id,))
    connection.close()


def test_uncertainty_dossier_input_forbids_results_duplicates_and_invalid_limits():
    with pytest.raises(ValidationError):
        UncertaintyDossierCreate(run_ids=("a", "b"), qualification="ROBUST")
    with pytest.raises(ValidationError, match="must be unique"):
        UncertaintyDossierCreate(run_ids=("a", "a"))
    with pytest.raises(ValidationError, match="at least one bound"):
        MetricLimit(metric="mean")
    with pytest.raises(ValidationError, match="cannot exceed"):
        MetricLimit(metric="mean", minimum_allowed=2, maximum_allowed=1)


def test_uncertainty_dossier_api_health_info_and_audit(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "dossier-api.db")
    _, _, runs = persisted_runs(repository, 3, iterations=250)
    monkeypatch.setattr(main, "repo", repository)
    client = TestClient(main.app)
    assert client.get("/health").json()["version"] == "1.0.7"
    info = client.get("/info").json()
    assert info["release"] == "V1.07"
    assert "uncertainty_dossier" in info["capabilities"]
    response = client.post(
        "/v1/uncertainty-dossiers",
        json={"run_ids": [run.id for run in runs], "limits": []},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["qualification"] == "ROBUST"
    assert client.get(f"/v1/uncertainty-dossiers/{body['id']}").status_code == 200
    assert len(client.get("/v1/uncertainty-dossiers").json()) == 1
    assert repository.list_audit_events()[-1].event_type == "UNCERTAINTY_DOSSIER_CREATED"
