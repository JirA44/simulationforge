from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api import main
from apps.api.models import (
    ConvergenceDossierCreate,
    ScenarioCreate,
    SimulationModelCreate,
    SimulationRunCreate,
)
from apps.api.repository import Repository


def constant_scenario(repo: Repository, name: str = "constant"):
    model = repo.create_model(
        SimulationModelCreate.model_validate(
            {
                "name": f"{name}_model",
                "version": "1.0.0",
                "summary": "Constant output for convergence controls",
                "assumptions": ["The output is constant by construction"],
                "variables": [{"name": "x", "distribution": "constant", "value": 2}],
                "outcome": {"name": "y", "intercept": 1, "coefficients": {"x": 3}},
            }
        )
    )
    return repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name=name,
            version="1.0.0",
            description="Frozen constant convergence scenario",
        )
    )


def random_scenario(repo: Repository):
    model = repo.create_model(
        SimulationModelCreate.model_validate(
            {
                "name": "random_model",
                "version": "1.0.0",
                "summary": "Uniform output for convergence controls",
                "assumptions": ["Uniform draws are a descriptive assumption"],
                "variables": [{"name": "x", "distribution": "uniform", "low": -100, "high": 100}],
                "outcome": {"name": "y", "intercept": 0, "coefficients": {"x": 1}},
            }
        )
    )
    return repo.create_scenario(
        ScenarioCreate(
            model_id=model.id,
            name="random",
            version="1.0.0",
            description="Frozen random convergence scenario",
        )
    )


def make_runs(repo: Repository, scenario_id: str, budgets=(100, 1000, 5000), seed=42):
    return [
        repo.run(SimulationRunCreate(scenario_id=scenario_id, seed=seed, iterations=iterations))
        for iterations in budgets
    ]


def test_constant_budget_series_is_converged(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenario = constant_scenario(repo)
    runs = make_runs(repo, scenario.id)
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "CONVERGED"
    assert dossier.reference_run_id == runs[-1].id
    assert dossier.worst_point.maximum_relative_deviation == 0
    assert [point.iterations for point in dossier.points] == [100, 1000, 5000]


def test_reference_budget_below_threshold_is_insufficient(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenario = constant_scenario(repo)
    runs = make_runs(repo, scenario.id, budgets=(10, 100, 999))
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.thresholds.minimum_reference_iterations == 1000


def test_variable_series_can_be_unstable(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenario = random_scenario(repo)
    runs = make_runs(repo, scenario.id, budgets=(3, 30, 1000), seed=7)
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "UNSTABLE"
    assert dossier.worst_point.maximum_relative_deviation > dossier.thresholds.relative_deviation_threshold


def test_different_seeds_are_incompatible(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenario = constant_scenario(repo)
    runs = [
        repo.run(SimulationRunCreate(scenario_id=scenario.id, seed=seed, iterations=budget))
        for seed, budget in ((1, 100), (2, 1000), (3, 5000))
    ]
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "INCOMPATIBLE"
    assert "same seed" in " ".join(dossier.compatibility_errors)
    assert dossier.points == ()


def test_different_scenarios_are_incompatible(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    first = constant_scenario(repo, "first")
    second = constant_scenario(repo, "second")
    runs = make_runs(repo, first.id, budgets=(100, 1000), seed=9)
    runs += make_runs(repo, second.id, budgets=(5000,), seed=9)
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "INCOMPATIBLE"
    assert "same frozen scenario" in " ".join(dossier.compatibility_errors)


def test_order_independent_replay_is_idempotent_and_single_audit(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenario = constant_scenario(repo)
    runs = make_runs(repo, scenario.id)
    ids = tuple(run.id for run in runs)
    first = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=ids))
    replay = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(reversed(ids))))
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert replay.idempotent_replay is True
    assert replay.order_independent is True
    events = [event for event in repo.list_audit_events() if event.event_type == "CONVERGENCE_DOSSIER_CREATED"]
    assert len(events) == 1


def test_dossier_is_immutable_and_get_list_round_trip(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    scenario = constant_scenario(repo)
    runs = make_runs(repo, scenario.id)
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert repo.get_convergence_dossier(dossier.id) == dossier
    assert repo.list_convergence_dossiers()[0] == dossier
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE convergence_dossiers SET qualification='UNSTABLE' WHERE id=?", (dossier.id,))
    connection.close()


def test_tampered_run_is_recalculated_and_incompatible(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    scenario = constant_scenario(repo)
    runs = make_runs(repo, scenario.id)
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER simulation_runs_no_update")
    connection.execute(
        "UPDATE simulation_runs SET statistics_json=? WHERE id=?",
        (json.dumps({"count": 100, "minimum": 0, "maximum": 0, "mean": 0, "population_stddev": 0, "p05": 0, "median": 0, "p95": 0}), runs[0].id),
    )
    connection.commit(); connection.close()
    dossier = repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "INCOMPATIBLE"
    assert "statistics mismatch" in " ".join(dossier.compatibility_errors)


def test_strict_request_and_missing_ids(tmp_path):
    with pytest.raises(ValidationError):
        ConvergenceDossierCreate(run_ids=("a", "b", "c"), qualification="CONVERGED")
    with pytest.raises(ValidationError):
        ConvergenceDossierCreate(run_ids=("a", "a", "b"))
    repo = Repository(tmp_path / "simulationforge.db")
    with pytest.raises(KeyError, match="not found"):
        repo.create_convergence_dossier(ConvergenceDossierCreate(run_ids=("a", "b", "c")))


def test_convergence_http_flow_and_server_only_result(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "repo", Repository(tmp_path / "api.db"))
    client = TestClient(main.app)
    model = client.post(
        "/v1/models",
        json={
            "name": "api_constant",
            "version": "1.0.0",
            "summary": "Constant API convergence model",
            "assumptions": ["Constant by construction"],
            "variables": [{"name": "x", "distribution": "constant", "value": 2}],
            "outcome": {"name": "y", "intercept": 1, "coefficients": {"x": 3}},
        },
    ).json()
    scenario = client.post(
        "/v1/scenarios",
        json={"model_id": model["id"], "name": "api_convergence", "version": "1.0.0", "description": "API convergence scenario"},
    ).json()
    run_ids = [
        client.post("/v1/runs", json={"scenario_id": scenario["id"], "seed": 12, "iterations": n}).json()["id"]
        for n in (100, 1000, 5000)
    ]
    created = client.post("/v1/convergence-dossiers", json={"run_ids": run_ids})
    assert created.status_code == 201
    assert created.json()["qualification"] == "CONVERGED"
    assert client.get(f"/v1/convergence-dossiers/{created.json()['id']}").status_code == 200
    assert len(client.get("/v1/convergence-dossiers").json()) == 1
    forbidden = client.post("/v1/convergence-dossiers", json={"run_ids": run_ids, "qualification": "CONVERGED"})
    assert forbidden.status_code == 422
