from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api import main
from apps.api.models import (
    ScenarioCreate,
    ScenarioDriftDossierCreate,
    SimulationModelCreate,
    SimulationRunCreate,
)
from apps.api.repository import Repository


def model(repo: Repository, name: str = "drift_model"):
    return repo.create_model(
        SimulationModelCreate.model_validate(
            {
                "name": name,
                "version": "1.0.0",
                "summary": "Frozen model for chronological scenario drift controls",
                "assumptions": ["Scenario overrides are descriptive"],
                "variables": [{"name": "x", "distribution": "uniform", "low": 0, "high": 10}],
                "outcome": {"name": "y", "intercept": 0, "coefficients": {"x": 10}},
            }
        )
    )


def scenario(repo: Repository, model_id: str, version: str, x: float):
    return repo.create_scenario(
        ScenarioCreate(
            model_id=model_id,
            name="scenario_evolution",
            version=version,
            description=f"Frozen scenario {version}",
            parameter_overrides={"x": x},
        )
    )


def series(repo: Repository, values=(1.0, 1.01, 1.02), seed=42, iterations=1000):
    frozen_model = model(repo)
    scenarios = [scenario(repo, frozen_model.id, f"1.0.{index}", value) for index, value in enumerate(values)]
    runs = [
        repo.run(SimulationRunCreate(scenario_id=item.id, seed=seed, iterations=iterations))
        for item in scenarios
    ]
    return scenarios, runs


def test_small_scenario_changes_are_stable_and_server_ordered(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenarios, runs = series(repo)
    dossier = repo.create_scenario_drift_dossier(
        ScenarioDriftDossierCreate(run_ids=tuple(run.id for run in reversed(runs)))
    )
    assert dossier.qualification == "STABLE"
    assert dossier.ordered_run_ids == tuple(run.id for run in runs)
    assert [point.scenario_version for point in dossier.points] == ["1.0.0", "1.0.1", "1.0.2"]
    assert dossier.worst_transition.maximum_relative_delta <= 0.05
    assert dossier.affected_scenario_ids == ()


def test_large_scenario_change_is_drifting(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenarios, runs = series(repo, values=(1.0, 1.02, 2.0))
    dossier = repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "DRIFTING"
    assert dossier.worst_transition.maximum_relative_delta > 0.05
    assert set(dossier.affected_scenario_ids) == {scenarios[1].id, scenarios[2].id}
    assert dossier.transitions[-1].direction == "UPWARD"


def test_low_iteration_evidence_is_insufficient(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    _, runs = series(repo, iterations=999)
    dossier = repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=tuple(run.id for run in runs)))
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.thresholds.minimum_iterations == 1000


@pytest.mark.parametrize("difference", ["seed", "iterations"])
def test_mismatched_run_contract_is_incompatible(tmp_path, difference):
    repo = Repository(tmp_path / "simulationforge.db")
    frozen_model = model(repo)
    first = scenario(repo, frozen_model.id, "1.0.0", 1)
    second = scenario(repo, frozen_model.id, "1.0.1", 2)
    left = repo.run(SimulationRunCreate(scenario_id=first.id, seed=1, iterations=1000))
    right = repo.run(
        SimulationRunCreate(
            scenario_id=second.id,
            seed=2 if difference == "seed" else 1,
            iterations=2000 if difference == "iterations" else 1000,
        )
    )
    dossier = repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=(left.id, right.id)))
    assert dossier.qualification == "INCOMPATIBLE"
    expected = "seed" if difference == "seed" else "iteration"
    assert expected in " ".join(dossier.compatibility_errors)
    assert dossier.transitions == ()


def test_order_independent_idempotence_audit_and_immutability(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    _, runs = series(repo)
    ids = tuple(run.id for run in runs)
    first = repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=ids))
    replay = repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=tuple(reversed(ids))))
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert replay.idempotent_replay is True
    assert repo.get_scenario_drift_dossier(first.id) == first
    assert repo.list_scenario_drift_dossiers()[0] == first
    events = [event for event in repo.list_audit_events() if event.event_type == "SCENARIO_DRIFT_DOSSIER_CREATED"]
    assert len(events) == 1
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE scenario_drift_dossiers SET qualification='DRIFTING' WHERE id=?", (first.id,))
    connection.close()


def test_tampered_run_is_recalculated_and_incompatible(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    _, runs = series(repo)
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER simulation_runs_no_update")
    connection.execute(
        "UPDATE simulation_runs SET statistics_json=? WHERE id=?",
        (json.dumps({"count": 1000, "minimum": 0, "maximum": 0, "mean": 0, "population_stddev": 0, "p05": 0, "median": 0, "p95": 0}), runs[0].id),
    )
    connection.commit()
    connection.close()
    dossier = repo.create_scenario_drift_dossier(
        ScenarioDriftDossierCreate(run_ids=tuple(run.id for run in runs))
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert "statistics mismatch" in " ".join(dossier.compatibility_errors)


def test_strict_request_and_unknown_run_refusal(tmp_path):
    with pytest.raises(ValidationError):
        ScenarioDriftDossierCreate(run_ids=("a", "b"), qualification="STABLE")
    with pytest.raises(ValidationError):
        ScenarioDriftDossierCreate(run_ids=("a", "a"))
    repo = Repository(tmp_path / "simulationforge.db")
    with pytest.raises(KeyError, match="not found"):
        repo.create_scenario_drift_dossier(ScenarioDriftDossierCreate(run_ids=("missing-a", "missing-b")))


def test_http_flow_and_server_only_qualification(tmp_path, monkeypatch):
    repo = Repository(tmp_path / "api.db")
    monkeypatch.setattr(main, "repo", repo)
    client = TestClient(main.app)
    _, runs = series(repo)
    created = client.post("/v1/scenario-drift-dossiers", json={"run_ids": [run.id for run in runs]})
    assert created.status_code == 201
    assert created.json()["qualification"] == "STABLE"
    dossier_id = created.json()["id"]
    assert client.get(f"/v1/scenario-drift-dossiers/{dossier_id}").status_code == 200
    assert len(client.get("/v1/scenario-drift-dossiers").json()) == 1
    forbidden = client.post(
        "/v1/scenario-drift-dossiers",
        json={"run_ids": [run.id for run in runs], "qualification": "STABLE"},
    )
    assert forbidden.status_code == 422
