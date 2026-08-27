from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from . import __version__
from .models import (
    AuditEvent,
    ConvergenceDossier,
    ConvergenceDossierCreate,
    InteractionSurface,
    InteractionSurfaceCreate,
    Scenario,
    ScenarioComparison,
    ScenarioComparisonCreate,
    ScenarioCreate,
    ScenarioDriftDossier,
    ScenarioDriftDossierCreate,
    ScenarioCoverageDossier,
    ScenarioCoverageDossierCreate,
    SensitivityAnalysis,
    SensitivityAnalysisCreate,
    SimulationModel,
    SimulationModelCreate,
    SimulationRun,
    SimulationRunCreate,
    UncertaintyDossier,
    UncertaintyDossierCreate,
)
from .repository import ConflictError, PERMANENT_WARNING, Repository


app = FastAPI(
    title="SimulationForge API",
    version=__version__,
    description="Simulations, surfaces, incertitude, convergence, dérive et couverture explicite de scénarios déterministes, reproductibles et non prédictives.",
)
DB_PATH = os.getenv("SIMULATIONFORGE_DB", str(Path(__file__).resolve().parents[2] / "simulationforge.db"))
repo = Repository(DB_PATH)


def not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=exc.args[0])


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "warning": PERMANENT_WARNING}


@app.get("/info")
def info():
    return {
        "name": "SimulationForge",
        "version": __version__,
        "release": "V1.07",
        "capabilities": [
            "simulation",
            "scenario_comparison",
            "parametric_sensitivity",
            "interaction_surface",
            "uncertainty_dossier",
            "iteration_convergence_dossier",
            "scenario_distribution_drift_dossier",
            "explicit_scenario_space_coverage_dossier",
        ],
        "warning": PERMANENT_WARNING,
    }


@app.post("/v1/models", response_model=SimulationModel, status_code=201)
def create_model(data: SimulationModelCreate):
    try:
        return repo.create_model(data)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/models", response_model=list[SimulationModel])
def list_models():
    return repo.list_models()


@app.get("/v1/models/{model_id}", response_model=SimulationModel)
def get_model(model_id: str):
    try:
        return repo.get_model(model_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/scenarios", response_model=Scenario, status_code=201)
def create_scenario(data: ScenarioCreate):
    try:
        return repo.create_scenario(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/scenarios", response_model=list[Scenario])
def list_scenarios():
    return repo.list_scenarios()


@app.get("/v1/scenarios/{scenario_id}", response_model=Scenario)
def get_scenario(scenario_id: str):
    try:
        return repo.get_scenario(scenario_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/runs", response_model=SimulationRun, status_code=201)
def run_simulation(data: SimulationRunCreate):
    try:
        return repo.run(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/runs", response_model=list[SimulationRun])
def list_runs():
    return repo.list_runs()


@app.get("/v1/runs/{run_id}", response_model=SimulationRun)
def get_run(run_id: str):
    try:
        return repo.get_run(run_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/comparisons", response_model=ScenarioComparison, status_code=201)
def compare_scenarios(data: ScenarioComparisonCreate):
    try:
        return repo.compare(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/comparisons", response_model=list[ScenarioComparison])
def list_comparisons():
    return repo.list_comparisons()


@app.get("/v1/comparisons/{comparison_id}", response_model=ScenarioComparison)
def get_comparison(comparison_id: str):
    try:
        return repo.get_comparison(comparison_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/sensitivities", response_model=SensitivityAnalysis, status_code=201)
def analyze_sensitivity(data: SensitivityAnalysisCreate):
    try:
        return repo.analyze_sensitivity(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/sensitivities", response_model=list[SensitivityAnalysis])
def list_sensitivities():
    return repo.list_sensitivities()


@app.get("/v1/sensitivities/{analysis_id}", response_model=SensitivityAnalysis)
def get_sensitivity(analysis_id: str):
    try:
        return repo.get_sensitivity(analysis_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/interaction-surfaces", response_model=InteractionSurface, status_code=201)
def analyze_interaction_surface(data: InteractionSurfaceCreate):
    try:
        return repo.analyze_interaction_surface(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/interaction-surfaces", response_model=list[InteractionSurface])
def list_interaction_surfaces():
    return repo.list_interaction_surfaces()


@app.get("/v1/interaction-surfaces/{surface_id}", response_model=InteractionSurface)
def get_interaction_surface(surface_id: str):
    try:
        return repo.get_interaction_surface(surface_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/uncertainty-dossiers", response_model=UncertaintyDossier, status_code=201)
def create_uncertainty_dossier(data: UncertaintyDossierCreate):
    try:
        return repo.create_uncertainty_dossier(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/uncertainty-dossiers", response_model=list[UncertaintyDossier])
def list_uncertainty_dossiers():
    return repo.list_uncertainty_dossiers()


@app.get("/v1/uncertainty-dossiers/{dossier_id}", response_model=UncertaintyDossier)
def get_uncertainty_dossier(dossier_id: str):
    try:
        return repo.get_uncertainty_dossier(dossier_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/convergence-dossiers", response_model=ConvergenceDossier, status_code=201)
def create_convergence_dossier(data: ConvergenceDossierCreate):
    try:
        return repo.create_convergence_dossier(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/convergence-dossiers", response_model=list[ConvergenceDossier])
def list_convergence_dossiers():
    return repo.list_convergence_dossiers()


@app.get("/v1/convergence-dossiers/{dossier_id}", response_model=ConvergenceDossier)
def get_convergence_dossier(dossier_id: str):
    try:
        return repo.get_convergence_dossier(dossier_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/scenario-drift-dossiers", response_model=ScenarioDriftDossier, status_code=201)
def create_scenario_drift_dossier(data: ScenarioDriftDossierCreate):
    try:
        return repo.create_scenario_drift_dossier(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/scenario-drift-dossiers", response_model=list[ScenarioDriftDossier])
def list_scenario_drift_dossiers():
    return repo.list_scenario_drift_dossiers()


@app.get("/v1/scenario-drift-dossiers/{dossier_id}", response_model=ScenarioDriftDossier)
def get_scenario_drift_dossier(dossier_id: str):
    try:
        return repo.get_scenario_drift_dossier(dossier_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.post("/v1/scenario-coverage-dossiers", response_model=ScenarioCoverageDossier, status_code=201)
def create_scenario_coverage_dossier(data: ScenarioCoverageDossierCreate):
    try:
        return repo.create_scenario_coverage_dossier(data)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/scenario-coverage-dossiers", response_model=list[ScenarioCoverageDossier])
def list_scenario_coverage_dossiers():
    return repo.list_scenario_coverage_dossiers()


@app.get("/v1/scenario-coverage-dossiers/{dossier_id}", response_model=ScenarioCoverageDossier)
def get_scenario_coverage_dossier(dossier_id: str):
    try:
        return repo.get_scenario_coverage_dossier(dossier_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/v1/audit-events", response_model=list[AuditEvent])
def list_audit_events():
    return repo.list_audit_events()
