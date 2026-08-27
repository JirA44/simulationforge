from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api import main
from apps.api.models import ScenarioCoverageDossierCreate, ScenarioCreate, SimulationModelCreate
from apps.api.repository import Repository


def model(repo: Repository, name: str = "coverage_model"):
    return repo.create_model(
        SimulationModelCreate.model_validate(
            {
                "name": name,
                "version": "1.0.0",
                "summary": "Frozen model for explicit scenario-space coverage",
                "assumptions": ["Explicit overrides are descriptive stress points"],
                "variables": [
                    {"name": "x", "distribution": "uniform", "low": 0, "high": 10, "unit": "u"},
                    {"name": "y", "distribution": "uniform", "low": -1, "high": 1},
                    {"name": "fixed", "distribution": "constant", "value": 2},
                ],
                "outcome": {"name": "z", "intercept": 0, "coefficients": {"x": 1, "y": 1, "fixed": 1}},
            }
        )
    )


def scenario(repo: Repository, model_id: str, index: int, overrides: dict[str, float]):
    return repo.create_scenario(
        ScenarioCreate(
            model_id=model_id,
            name="coverage_series",
            version=f"1.0.{index}",
            description=f"Explicit stress point {index}",
            parameter_overrides=overrides,
        )
    )


def complete_series(repo: Repository):
    frozen = model(repo)
    return [
        scenario(repo, frozen.id, 0, {"x": 0, "y": -1}),
        scenario(repo, frozen.id, 1, {"x": 5, "y": 0}),
        scenario(repo, frozen.id, 2, {"x": 10, "y": 1}),
    ]


def test_complete_explicit_scenario_space_is_server_ordered(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    scenarios = complete_series(repo)
    dossier = repo.create_scenario_coverage_dossier(
        ScenarioCoverageDossierCreate(scenario_ids=tuple(item.id for item in reversed(scenarios)))
    )
    assert dossier.qualification == "COMPLETE"
    assert dossier.ordered_scenario_ids == tuple(item.id for item in scenarios)
    assert dossier.missing_parameters == ()
    assert dossier.partial_parameters == ()
    assert dossier.fully_covered_parameters == ("fixed", "x", "y")
    assert {item.parameter: item.coverage_status for item in dossier.parameter_coverage} == {
        "fixed": "CONSTANT", "x": "FULL", "y": "FULL"
    }


def test_partial_and_missing_parameters_are_reported(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    frozen = model(repo)
    scenarios = [scenario(repo, frozen.id, index, {"x": value}) for index, value in enumerate((2, 5, 8))]
    dossier = repo.create_scenario_coverage_dossier(
        ScenarioCoverageDossierCreate(scenario_ids=tuple(item.id for item in scenarios))
    )
    assert dossier.qualification == "PARTIAL"
    assert dossier.partial_parameters == ("x",)
    assert dossier.missing_parameters == ("y",)
    assert dossier.worst_parameter.parameter == "y"
    assert dossier.worst_parameter.span_ratio == 0


def test_two_scenarios_are_insufficient_even_when_bounds_are_present(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    frozen = model(repo)
    scenarios = [
        scenario(repo, frozen.id, 0, {"x": 0, "y": -1}),
        scenario(repo, frozen.id, 1, {"x": 10, "y": 1}),
    ]
    dossier = repo.create_scenario_coverage_dossier(
        ScenarioCoverageDossierCreate(scenario_ids=tuple(item.id for item in scenarios))
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.thresholds.minimum_scenarios == 3


def test_scenarios_from_different_models_are_incompatible(tmp_path):
    repo = Repository(tmp_path / "simulationforge.db")
    left_model = model(repo, "left_model")
    right_model = model(repo, "right_model")
    scenarios = [
        scenario(repo, left_model.id, 0, {"x": 0}),
        scenario(repo, right_model.id, 0, {"x": 10}),
    ]
    dossier = repo.create_scenario_coverage_dossier(
        ScenarioCoverageDossierCreate(scenario_ids=tuple(item.id for item in scenarios))
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert "same frozen model" in " ".join(dossier.compatibility_errors)
    assert dossier.parameter_coverage == ()


def test_order_independent_idempotence_audit_and_immutability(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    scenarios = complete_series(repo)
    ids = tuple(item.id for item in scenarios)
    first = repo.create_scenario_coverage_dossier(ScenarioCoverageDossierCreate(scenario_ids=ids))
    replay = repo.create_scenario_coverage_dossier(ScenarioCoverageDossierCreate(scenario_ids=tuple(reversed(ids))))
    assert replay.id == first.id
    assert replay.snapshot_hash == first.snapshot_hash
    assert replay.idempotent_replay is True
    assert repo.get_scenario_coverage_dossier(first.id) == first
    assert repo.list_scenario_coverage_dossiers()[0] == first
    events = [event for event in repo.list_audit_events() if event.event_type == "SCENARIO_COVERAGE_DOSSIER_CREATED"]
    assert len(events) == 1
    connection = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE scenario_coverage_dossiers SET qualification='PARTIAL' WHERE id=?", (first.id,))
    connection.close()


def test_tampered_scenario_hash_is_detected(tmp_path):
    database = tmp_path / "simulationforge.db"
    repo = Repository(database)
    scenarios = complete_series(repo)
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER scenarios_no_update")
    connection.execute("UPDATE scenarios SET scenario_hash=? WHERE id=?", ("0" * 64, scenarios[0].id))
    connection.commit()
    connection.close()
    dossier = repo.create_scenario_coverage_dossier(
        ScenarioCoverageDossierCreate(scenario_ids=tuple(item.id for item in scenarios))
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert "scenario hash mismatch" in " ".join(dossier.compatibility_errors)


def test_strict_request_and_unknown_scenario_refusal(tmp_path):
    with pytest.raises(ValidationError):
        ScenarioCoverageDossierCreate(scenario_ids=("a", "b"), qualification="COMPLETE")
    with pytest.raises(ValidationError):
        ScenarioCoverageDossierCreate(scenario_ids=("a", "a"))
    repo = Repository(tmp_path / "simulationforge.db")
    with pytest.raises(KeyError, match="not found"):
        repo.create_scenario_coverage_dossier(ScenarioCoverageDossierCreate(scenario_ids=("missing-a", "missing-b")))


def test_http_flow_and_server_only_qualification(tmp_path, monkeypatch):
    repo = Repository(tmp_path / "api.db")
    monkeypatch.setattr(main, "repo", repo)
    client = TestClient(main.app)
    scenarios = complete_series(repo)
    response = client.post(
        "/v1/scenario-coverage-dossiers",
        json={"scenario_ids": [item.id for item in scenarios]},
    )
    assert response.status_code == 201
    assert response.json()["qualification"] == "COMPLETE"
    dossier_id = response.json()["id"]
    assert client.get(f"/v1/scenario-coverage-dossiers/{dossier_id}").status_code == 200
    assert len(client.get("/v1/scenario-coverage-dossiers").json()) == 1
    forbidden = client.post(
        "/v1/scenario-coverage-dossiers",
        json={"scenario_ids": [item.id for item in scenarios], "qualification": "COMPLETE"},
    )
    assert forbidden.status_code == 422
