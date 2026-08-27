from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .engine import (
    ALGORITHM_VERSION,
    COMPARISON_ALGORITHM_VERSION,
    INTERACTION_ALGORITHM_VERSION,
    SENSITIVITY_ALGORITHM_VERSION,
    canonical_hash,
    _statistics,
    simulate,
    simulate_pair,
    simulate_sensitivity,
    simulate_interaction_surface,
)
from .models import (
    AuditEvent,
    ConvergenceDossier,
    ConvergenceDossierCreate,
    ConvergencePoint,
    ConvergenceQualification,
    ConvergenceThresholds,
    CoreMetricDeviation,
    ComparisonDeltas,
    ComparisonQualification,
    InteractionMetrics,
    InteractionQualification,
    InteractionSurface,
    InteractionSurfaceCreate,
    LimitViolation,
    MeanDirection,
    MetricEnvelope,
    MetricLimit,
    RankingStability,
    RobustnessQualification,
    RobustnessThresholds,
    RunMetric,
    Scenario,
    ScenarioComparison,
    ScenarioComparisonCreate,
    ScenarioCreate,
    ScenarioDriftDossier,
    ScenarioDriftDossierCreate,
    ScenarioDriftPoint,
    ScenarioDriftQualification,
    ScenarioDriftThresholds,
    ScenarioDriftTransition,
    ScenarioCoverageDossier,
    ScenarioCoverageDossierCreate,
    ScenarioCoveragePoint,
    ScenarioCoverageQualification,
    ScenarioCoverageThresholds,
    ParameterCoverage,
    WorstParameterCoverage,
    SensitivityAnalysis,
    SensitivityAnalysisCreate,
    SensitivityDeltas,
    SensitivityMetrics,
    SensitivityPoint,
    SensitivityQualification,
    SimulationModel,
    SimulationModelCreate,
    SimulationRun,
    SimulationRunCreate,
    SimulationStatistics,
    SurfaceCell,
    StabilityAnalysis,
    UncertaintyDossier,
    UncertaintyDossierCreate,
    WorstConvergencePoint,
    WorstScenarioDriftTransition,
    WorstRun,
)


PERMANENT_WARNING = (
    "Simulation descriptive fondée sur des hypothèses versionnées; "
    "elle ne constitue ni une prédiction, ni une certification, ni une certitude, ni un conseil de décision."
)
MIN_COMPARISON_ITERATIONS = 100
MIN_SENSITIVITY_ITERATIONS = 100
SENSITIVITY_THRESHOLD = 0.05
MIN_INTERACTION_ITERATIONS = 100
INTERACTION_THRESHOLD = 0.05
SURFACE_SENSITIVITY_THRESHOLD = 0.05
UNCERTAINTY_ALGORITHM_VERSION = "uncertainty-envelope-v1"
MIN_DOSSIER_RUNS = 3
UNCERTAINTY_WIDTH_THRESHOLD = 0.05
RANKING_AGREEMENT_THRESHOLD = 0.80
CONVERGENCE_ALGORITHM_VERSION = "iteration-convergence-v1"
MIN_CONVERGENCE_BUDGETS = 3
MIN_REFERENCE_ITERATIONS = 1000
CONVERGENCE_RELATIVE_THRESHOLD = 0.02
SCENARIO_DRIFT_ALGORITHM_VERSION = "scenario-distribution-drift-v1"
MIN_SCENARIO_DRIFT_RUNS = 2
MIN_SCENARIO_DRIFT_ITERATIONS = 1000
SCENARIO_DRIFT_RELATIVE_THRESHOLD = 0.05
SCENARIO_COVERAGE_ALGORITHM_VERSION = "explicit-scenario-space-coverage-v1"
MIN_SCENARIO_COVERAGE_SCENARIOS = 3
SCENARIO_COVERAGE_BOUNDARY_TOLERANCE = 1e-9


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS simulation_models(
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 model_hash TEXT NOT NULL UNIQUE,
 specification_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(name, version)
);
CREATE TABLE IF NOT EXISTS scenarios(
 id TEXT PRIMARY KEY,
 model_id TEXT NOT NULL REFERENCES simulation_models(id),
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 scenario_hash TEXT NOT NULL UNIQUE,
 specification_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(model_id, name, version)
);
CREATE TABLE IF NOT EXISTS simulation_runs(
 id TEXT PRIMARY KEY,
 scenario_id TEXT NOT NULL REFERENCES scenarios(id),
 seed INTEGER NOT NULL,
 iterations INTEGER NOT NULL CHECK(iterations BETWEEN 1 AND 10000),
 algorithm_version TEXT NOT NULL,
 statistics_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification='DESCRIPTIVE_ONLY'),
 warning TEXT NOT NULL,
 result_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(scenario_id, seed, iterations, algorithm_version)
);
CREATE TABLE IF NOT EXISTS scenario_comparisons(
 id TEXT PRIMARY KEY,
 baseline_scenario_id TEXT NOT NULL REFERENCES scenarios(id),
 stress_scenario_id TEXT NOT NULL REFERENCES scenarios(id),
 seed INTEGER NOT NULL,
 iterations INTEGER NOT NULL CHECK(iterations BETWEEN 1 AND 10000),
 algorithm_version TEXT NOT NULL,
 baseline_statistics_json TEXT NOT NULL,
 stress_statistics_json TEXT NOT NULL,
 deltas_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('ROBUST','FRAGILE','INSUFFICIENT')),
 warning TEXT NOT NULL,
 report_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 CHECK(baseline_scenario_id <> stress_scenario_id),
 UNIQUE(baseline_scenario_id, stress_scenario_id, seed, iterations, algorithm_version)
);
CREATE TABLE IF NOT EXISTS sensitivity_analyses(
 id TEXT PRIMARY KEY,
 scenario_id TEXT NOT NULL REFERENCES scenarios(id),
 parameter TEXT NOT NULL,
 grid_json TEXT NOT NULL,
 grid_hash TEXT NOT NULL,
 seed INTEGER NOT NULL,
 iterations INTEGER NOT NULL CHECK(iterations BETWEEN 1 AND 10000),
 algorithm_version TEXT NOT NULL,
 reference_statistics_json TEXT NOT NULL,
 points_json TEXT NOT NULL,
 metrics_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('STABLE','SENSITIVE','INSUFFICIENT')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(scenario_id, parameter, grid_hash, seed, iterations, algorithm_version)
);
CREATE TABLE IF NOT EXISTS interaction_surfaces(
 id TEXT PRIMARY KEY,
 scenario_id TEXT NOT NULL REFERENCES scenarios(id),
 parameter_x TEXT NOT NULL,
 parameter_y TEXT NOT NULL,
 grid_x_json TEXT NOT NULL,
 grid_y_json TEXT NOT NULL,
 surface_key_hash TEXT NOT NULL,
 seed INTEGER NOT NULL,
 iterations INTEGER NOT NULL CHECK(iterations BETWEEN 1 AND 10000),
 algorithm_version TEXT NOT NULL,
 cells_json TEXT NOT NULL,
 metrics_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('ADDITIVE','INTERACTIVE','SENSITIVE','INSUFFICIENT')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 CHECK(parameter_x <> parameter_y),
 UNIQUE(scenario_id, surface_key_hash, seed, iterations, algorithm_version)
);
CREATE TABLE IF NOT EXISTS uncertainty_dossiers(
 id TEXT PRIMARY KEY,
 request_hash TEXT NOT NULL,
 run_ids_json TEXT NOT NULL,
 limits_json TEXT NOT NULL,
 scenario_id TEXT REFERENCES scenarios(id),
 scenario_hash TEXT,
 model_hash TEXT,
 algorithm_version TEXT NOT NULL,
 verified_run_count INTEGER NOT NULL,
 compatibility_errors_json TEXT NOT NULL,
 envelopes_json TEXT NOT NULL,
 violations_json TEXT NOT NULL,
 worst_run_json TEXT,
 stability_json TEXT,
 thresholds_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('ROBUST','UNCERTAINTY_SENSITIVE','LIMIT_BREACH','INSUFFICIENT','INCOMPATIBLE')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(request_hash, algorithm_version)
);
CREATE TABLE IF NOT EXISTS convergence_dossiers(
 id TEXT PRIMARY KEY,
 request_hash TEXT NOT NULL,
 run_ids_json TEXT NOT NULL,
 scenario_id TEXT REFERENCES scenarios(id),
 scenario_hash TEXT,
 model_hash TEXT,
 seed INTEGER,
 algorithm_version TEXT NOT NULL,
 reference_run_id TEXT REFERENCES simulation_runs(id),
 verified_run_count INTEGER NOT NULL,
 compatibility_errors_json TEXT NOT NULL,
 points_json TEXT NOT NULL,
 worst_point_json TEXT,
 thresholds_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('CONVERGED','UNSTABLE','INSUFFICIENT','INCOMPATIBLE')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(request_hash, algorithm_version)
);
CREATE INDEX IF NOT EXISTS convergence_dossiers_created_idx ON convergence_dossiers(created_at DESC);
CREATE TABLE IF NOT EXISTS scenario_drift_dossiers(
 id TEXT PRIMARY KEY,
 request_hash TEXT NOT NULL,
 requested_run_ids_json TEXT NOT NULL,
 ordered_run_ids_json TEXT NOT NULL,
 model_id TEXT REFERENCES simulation_models(id),
 model_hash TEXT,
 seed INTEGER,
 iterations INTEGER,
 algorithm_version TEXT NOT NULL,
 verified_run_count INTEGER NOT NULL,
 compatibility_errors_json TEXT NOT NULL,
 points_json TEXT NOT NULL,
 transitions_json TEXT NOT NULL,
 worst_transition_json TEXT,
 affected_scenario_ids_json TEXT NOT NULL,
 thresholds_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('STABLE','DRIFTING','INSUFFICIENT','INCOMPATIBLE')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(request_hash, algorithm_version)
);
CREATE INDEX IF NOT EXISTS scenario_drift_dossiers_created_idx ON scenario_drift_dossiers(created_at DESC);
CREATE TABLE IF NOT EXISTS scenario_coverage_dossiers(
 id TEXT PRIMARY KEY,
 request_hash TEXT NOT NULL,
 requested_scenario_ids_json TEXT NOT NULL,
 ordered_scenario_ids_json TEXT NOT NULL,
 model_id TEXT REFERENCES simulation_models(id),
 model_hash TEXT,
 algorithm_version TEXT NOT NULL,
 verified_scenario_count INTEGER NOT NULL,
 compatibility_errors_json TEXT NOT NULL,
 points_json TEXT NOT NULL,
 parameter_coverage_json TEXT NOT NULL,
 missing_parameters_json TEXT NOT NULL,
 partial_parameters_json TEXT NOT NULL,
 fully_covered_parameters_json TEXT NOT NULL,
 worst_parameter_json TEXT,
 thresholds_json TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification IN ('COMPLETE','PARTIAL','INSUFFICIENT','INCOMPATIBLE')),
 warning TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL,
 UNIQUE(request_hash, algorithm_version)
);
CREATE INDEX IF NOT EXISTS scenario_coverage_dossiers_created_idx ON scenario_coverage_dossiers(created_at DESC);
CREATE TABLE IF NOT EXISTS audit_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_type TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 previous_hash TEXT,
 event_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS simulation_models_no_update BEFORE UPDATE ON simulation_models BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS simulation_models_no_delete BEFORE DELETE ON simulation_models BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenarios_no_update BEFORE UPDATE ON scenarios BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenarios_no_delete BEFORE DELETE ON scenarios BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS simulation_runs_no_update BEFORE UPDATE ON simulation_runs BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS simulation_runs_no_delete BEFORE DELETE ON simulation_runs BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_comparisons_no_update BEFORE UPDATE ON scenario_comparisons BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_comparisons_no_delete BEFORE DELETE ON scenario_comparisons BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS sensitivity_analyses_no_update BEFORE UPDATE ON sensitivity_analyses BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS sensitivity_analyses_no_delete BEFORE DELETE ON sensitivity_analyses BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS interaction_surfaces_no_update BEFORE UPDATE ON interaction_surfaces BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS interaction_surfaces_no_delete BEFORE DELETE ON interaction_surfaces BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS uncertainty_dossiers_no_update BEFORE UPDATE ON uncertainty_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS uncertainty_dossiers_no_delete BEFORE DELETE ON uncertainty_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS convergence_dossiers_no_update BEFORE UPDATE ON convergence_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS convergence_dossiers_no_delete BEFORE DELETE ON convergence_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_drift_dossiers_no_update BEFORE UPDATE ON scenario_drift_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_drift_dossiers_no_delete BEFORE DELETE ON scenario_drift_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_coverage_dossiers_no_update BEFORE UPDATE ON scenario_coverage_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS scenario_coverage_dossiers_no_delete BEFORE DELETE ON scenario_coverage_dossiers BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'append-only'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConflictError(ValueError):
    pass


class Repository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def _audit(self, connection, event_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
        previous = connection.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else None
        created_at = now()
        body = {
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
        event_hash = canonical_hash(body)
        connection.execute(
            "INSERT INTO audit_events(event_type,entity_type,entity_id,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (event_type, entity_type, entity_id, json.dumps(payload, sort_keys=True), previous_hash, event_hash, created_at),
        )

    def create_model(self, data: SimulationModelCreate) -> SimulationModel:
        specification = data.model_dump(mode="json")
        model_hash = canonical_hash(specification)
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM simulation_models WHERE model_hash=?", (model_hash,)).fetchone()
            if existing:
                return self._model(existing)
            identity = connection.execute(
                "SELECT model_hash FROM simulation_models WHERE name=? AND version=?", (data.name, data.version)
            ).fetchone()
            if identity:
                raise ConflictError("model name/version is already frozen with different content")
            model_id, created_at = str(uuid.uuid4()), now()
            connection.execute(
                "INSERT INTO simulation_models VALUES(?,?,?,?,?,?)",
                (model_id, data.name, data.version, model_hash, json.dumps(specification, sort_keys=True), created_at),
            )
            self._audit(connection, "MODEL_FROZEN", "simulation_model", model_id, {"model_hash": model_hash})
            row = connection.execute("SELECT * FROM simulation_models WHERE id=?", (model_id,)).fetchone()
        return self._model(row)

    @staticmethod
    def _model(row) -> SimulationModel:
        return SimulationModel(
            id=row["id"],
            model_hash=row["model_hash"],
            specification=SimulationModelCreate.model_validate_json(row["specification_json"]),
            created_at=row["created_at"],
        )

    def get_model(self, model_id: str) -> SimulationModel:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM simulation_models WHERE id=?", (model_id,)).fetchone()
        if not row:
            raise KeyError("model not found")
        return self._model(row)

    def list_models(self) -> list[SimulationModel]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM simulation_models ORDER BY created_at DESC").fetchall()
        return [self._model(row) for row in rows]

    def create_scenario(self, data: ScenarioCreate) -> Scenario:
        model = self.get_model(data.model_id)
        variables = {variable.name: variable for variable in model.specification.variables}
        unknown = set(data.parameter_overrides) - set(variables)
        if unknown:
            raise ValueError(f"unknown overridden variables: {sorted(unknown)}")
        for name, value in data.parameter_overrides.items():
            low, high = variables[name].bounds()
            if not low <= value <= high:
                raise ValueError(f"override {name} must be within [{low}, {high}]")
        specification = data.model_dump(mode="json")
        scenario_hash = canonical_hash({"model_hash": model.model_hash, "scenario": specification})
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM scenarios WHERE scenario_hash=?", (scenario_hash,)).fetchone()
            if existing:
                return self._scenario(existing)
            identity = connection.execute(
                "SELECT scenario_hash FROM scenarios WHERE model_id=? AND name=? AND version=?",
                (data.model_id, data.name, data.version),
            ).fetchone()
            if identity:
                raise ConflictError("scenario name/version is already frozen with different content")
            scenario_id, created_at = str(uuid.uuid4()), now()
            connection.execute(
                "INSERT INTO scenarios VALUES(?,?,?,?,?,?,?)",
                (scenario_id, data.model_id, data.name, data.version, scenario_hash, json.dumps(specification, sort_keys=True), created_at),
            )
            self._audit(connection, "SCENARIO_FROZEN", "scenario", scenario_id, {"scenario_hash": scenario_hash})
            row = connection.execute("SELECT * FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
        return self._scenario(row)

    def _scenario(self, row) -> Scenario:
        with self.connect() as connection:
            model = connection.execute("SELECT model_hash FROM simulation_models WHERE id=?", (row["model_id"],)).fetchone()
        return Scenario(
            id=row["id"],
            scenario_hash=row["scenario_hash"],
            model_hash=model["model_hash"],
            specification=ScenarioCreate.model_validate_json(row["specification_json"]),
            created_at=row["created_at"],
        )

    def get_scenario(self, scenario_id: str) -> Scenario:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
        if not row:
            raise KeyError("scenario not found")
        return self._scenario(row)

    def list_scenarios(self) -> list[Scenario]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM scenarios ORDER BY created_at DESC").fetchall()
        return [self._scenario(row) for row in rows]

    def run(self, data: SimulationRunCreate) -> SimulationRun:
        scenario = self.get_scenario(data.scenario_id)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM simulation_runs WHERE scenario_id=? AND seed=? AND iterations=? AND algorithm_version=?",
                (data.scenario_id, data.seed, data.iterations, ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._run(existing, scenario.scenario_hash, idempotent=True)
        model = self.get_model(scenario.specification.model_id)
        statistics = simulate(
            model.specification,
            scenario.specification.parameter_overrides,
            data.seed,
            data.iterations,
        )
        result_payload = {
            "scenario_hash": scenario.scenario_hash,
            "seed": data.seed,
            "iterations": data.iterations,
            "algorithm_version": ALGORITHM_VERSION,
            "statistics": statistics.model_dump(mode="json"),
            "qualification": "DESCRIPTIVE_ONLY",
            "warning": PERMANENT_WARNING,
        }
        result_hash = canonical_hash(result_payload)
        run_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO simulation_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    data.scenario_id,
                    data.seed,
                    data.iterations,
                    ALGORITHM_VERSION,
                    json.dumps(statistics.model_dump(mode="json"), sort_keys=True),
                    "DESCRIPTIVE_ONLY",
                    PERMANENT_WARNING,
                    result_hash,
                    created_at,
                ),
            )
            self._audit(connection, "SIMULATION_COMPUTED", "simulation_run", run_id, {"result_hash": result_hash})
            row = connection.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
        return self._run(row, scenario.scenario_hash)

    @staticmethod
    def _run(row, scenario_hash: str, idempotent: bool = False) -> SimulationRun:
        return SimulationRun(
            id=row["id"],
            scenario_id=row["scenario_id"],
            scenario_hash=scenario_hash,
            seed=row["seed"],
            iterations=row["iterations"],
            algorithm_version=row["algorithm_version"],
            statistics=SimulationStatistics.model_validate_json(row["statistics_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            result_hash=row["result_hash"],
            reproducible=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_run(self, run_id: str) -> SimulationRun:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
            if row:
                scenario = connection.execute("SELECT scenario_hash FROM scenarios WHERE id=?", (row["scenario_id"],)).fetchone()
        if not row:
            raise KeyError("simulation run not found")
        return self._run(row, scenario["scenario_hash"])

    def list_runs(self) -> list[SimulationRun]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT r.*,s.scenario_hash FROM simulation_runs r JOIN scenarios s ON s.id=r.scenario_id ORDER BY r.created_at DESC"
            ).fetchall()
        return [self._run(row, row["scenario_hash"]) for row in rows]

    @staticmethod
    def _model_interface(model: SimulationModelCreate) -> tuple:
        variables = tuple((item.name, item.unit) for item in model.variables)
        return variables, model.outcome.name, model.outcome.unit

    def _compatible_comparison_models(self, baseline: Scenario, stress: Scenario) -> SimulationModel:
        baseline_model = self.get_model(baseline.specification.model_id)
        stress_model = self.get_model(stress.specification.model_id)
        if baseline_model.id != stress_model.id or baseline_model.model_hash != stress_model.model_hash:
            raise ValueError("baseline and stress scenarios must reference the same frozen model")
        if self._model_interface(baseline_model.specification) != self._model_interface(stress_model.specification):
            raise ValueError("baseline and stress variables, outcome and units are incompatible")
        return baseline_model

    @staticmethod
    def _comparison_qualification(
        baseline: SimulationStatistics,
        deltas: ComparisonDeltas,
        iterations: int,
    ) -> ComparisonQualification:
        if iterations < MIN_COMPARISON_ITERATIONS:
            return ComparisonQualification.INSUFFICIENT
        scale = max(abs(baseline.mean), abs(baseline.p05), abs(baseline.p95), 1.0)
        materially_lower = min(deltas.mean, deltas.p05, deltas.p95) < -(0.05 * scale)
        materially_more_downside = deltas.downside > 0.05 * scale
        if materially_lower or materially_more_downside:
            return ComparisonQualification.FRAGILE
        return ComparisonQualification.ROBUST

    def compare(self, data: ScenarioComparisonCreate) -> ScenarioComparison:
        baseline = self.get_scenario(data.baseline_scenario_id)
        stress = self.get_scenario(data.stress_scenario_id)
        model = self._compatible_comparison_models(baseline, stress)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM scenario_comparisons WHERE baseline_scenario_id=? AND stress_scenario_id=? "
                "AND seed=? AND iterations=? AND algorithm_version=?",
                (
                    data.baseline_scenario_id,
                    data.stress_scenario_id,
                    data.seed,
                    data.iterations,
                    COMPARISON_ALGORITHM_VERSION,
                ),
            ).fetchone()
        if existing:
            return self._comparison(existing, baseline, stress, model.model_hash, idempotent=True)

        baseline_stats, stress_stats, deltas = simulate_pair(
            model.specification,
            baseline.specification.parameter_overrides,
            stress.specification.parameter_overrides,
            data.seed,
            data.iterations,
        )
        qualification = self._comparison_qualification(baseline_stats, deltas, data.iterations)
        payload = {
            "baseline_scenario_hash": baseline.scenario_hash,
            "stress_scenario_hash": stress.scenario_hash,
            "model_hash": model.model_hash,
            "seed": data.seed,
            "iterations": data.iterations,
            "algorithm_version": COMPARISON_ALGORITHM_VERSION,
            "baseline_statistics": baseline_stats.model_dump(mode="json"),
            "stress_statistics": stress_stats.model_dump(mode="json"),
            "deltas": deltas.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        report_hash = canonical_hash(payload)
        comparison_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO scenario_comparisons VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    comparison_id,
                    data.baseline_scenario_id,
                    data.stress_scenario_id,
                    data.seed,
                    data.iterations,
                    COMPARISON_ALGORITHM_VERSION,
                    json.dumps(baseline_stats.model_dump(mode="json"), sort_keys=True),
                    json.dumps(stress_stats.model_dump(mode="json"), sort_keys=True),
                    json.dumps(deltas.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    report_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "SCENARIOS_COMPARED",
                "scenario_comparison",
                comparison_id,
                {"report_hash": report_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM scenario_comparisons WHERE id=?", (comparison_id,)).fetchone()
        return self._comparison(row, baseline, stress, model.model_hash)

    @staticmethod
    def _comparison(
        row,
        baseline: Scenario,
        stress: Scenario,
        model_hash: str,
        idempotent: bool = False,
    ) -> ScenarioComparison:
        return ScenarioComparison(
            id=row["id"],
            baseline_scenario_id=row["baseline_scenario_id"],
            stress_scenario_id=row["stress_scenario_id"],
            baseline_scenario_hash=baseline.scenario_hash,
            stress_scenario_hash=stress.scenario_hash,
            model_hash=model_hash,
            seed=row["seed"],
            iterations=row["iterations"],
            algorithm_version=row["algorithm_version"],
            baseline_statistics=SimulationStatistics.model_validate_json(row["baseline_statistics_json"]),
            stress_statistics=SimulationStatistics.model_validate_json(row["stress_statistics_json"]),
            deltas=ComparisonDeltas.model_validate_json(row["deltas_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            report_hash=row["report_hash"],
            reproducible=True,
            common_random_numbers=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_comparison(self, comparison_id: str) -> ScenarioComparison:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scenario_comparisons WHERE id=?", (comparison_id,)).fetchone()
        if not row:
            raise KeyError("scenario comparison not found")
        baseline = self.get_scenario(row["baseline_scenario_id"])
        stress = self.get_scenario(row["stress_scenario_id"])
        model = self._compatible_comparison_models(baseline, stress)
        return self._comparison(row, baseline, stress, model.model_hash)

    def list_comparisons(self) -> list[ScenarioComparison]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM scenario_comparisons ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            baseline = self.get_scenario(row["baseline_scenario_id"])
            stress = self.get_scenario(row["stress_scenario_id"])
            model = self._compatible_comparison_models(baseline, stress)
            results.append(self._comparison(row, baseline, stress, model.model_hash))
        return results

    def _sensitivity_context(
        self, data: SensitivityAnalysisCreate
    ) -> tuple[Scenario, SimulationModel, tuple[float, ...], str, str | None]:
        scenario = self.get_scenario(data.scenario_id)
        model = self.get_model(scenario.specification.model_id)
        variables = {variable.name: variable for variable in model.specification.variables}
        if data.parameter not in variables:
            raise ValueError(f"unknown sensitivity parameter: {data.parameter}")
        if not self._parameter_influences_outcome(model.specification, data.parameter):
            raise ValueError("parameter is incompatible with the configured outcome")
        grid = data.resolved_grid()
        low, high = variables[data.parameter].bounds()
        if any(value < low or value > high for value in grid):
            raise ValueError(f"sensitivity grid for {data.parameter} must be within [{low}, {high}]")
        grid_hash = canonical_hash(grid)
        return scenario, model, grid, grid_hash, variables[data.parameter].unit

    @staticmethod
    def _parameter_influences_outcome(model: SimulationModelCreate, parameter: str) -> bool:
        coefficient = model.outcome.coefficients.get(parameter)
        if coefficient is not None and float(coefficient) != 0.0:
            return True
        return any(
            parameter in (term.parameter_x, term.parameter_y) and float(term.coefficient) != 0.0
            for term in model.outcome.interactions
        )

    @staticmethod
    def _sensitivity_qualification(metrics: SensitivityMetrics, iterations: int) -> SensitivityQualification:
        if iterations < MIN_SENSITIVITY_ITERATIONS:
            return SensitivityQualification.INSUFFICIENT
        if metrics.relative_mean_range > SENSITIVITY_THRESHOLD:
            return SensitivityQualification.SENSITIVE
        return SensitivityQualification.STABLE

    def analyze_sensitivity(self, data: SensitivityAnalysisCreate) -> SensitivityAnalysis:
        scenario, model, grid, grid_hash, parameter_unit = self._sensitivity_context(data)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM sensitivity_analyses WHERE scenario_id=? AND parameter=? AND grid_hash=? "
                "AND seed=? AND iterations=? AND algorithm_version=?",
                (
                    data.scenario_id,
                    data.parameter,
                    grid_hash,
                    data.seed,
                    data.iterations,
                    SENSITIVITY_ALGORITHM_VERSION,
                ),
            ).fetchone()
        if existing:
            return self._sensitivity(existing, scenario, model.model_hash, parameter_unit, idempotent=True)

        reference, points, metrics = simulate_sensitivity(
            model.specification,
            scenario.specification.parameter_overrides,
            data.parameter,
            grid,
            data.seed,
            data.iterations,
        )
        qualification = self._sensitivity_qualification(metrics, data.iterations)
        payload = {
            "scenario_hash": scenario.scenario_hash,
            "model_hash": model.model_hash,
            "parameter": data.parameter,
            "parameter_unit": parameter_unit,
            "grid": grid,
            "seed": data.seed,
            "iterations": data.iterations,
            "algorithm_version": SENSITIVITY_ALGORITHM_VERSION,
            "reference_statistics": reference.model_dump(mode="json"),
            "points": [point.model_dump(mode="json") for point in points],
            "metrics": metrics.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        analysis_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sensitivity_analyses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    analysis_id,
                    data.scenario_id,
                    data.parameter,
                    json.dumps(grid),
                    grid_hash,
                    data.seed,
                    data.iterations,
                    SENSITIVITY_ALGORITHM_VERSION,
                    json.dumps(reference.model_dump(mode="json"), sort_keys=True),
                    json.dumps([point.model_dump(mode="json") for point in points], sort_keys=True),
                    json.dumps(metrics.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    snapshot_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "SENSITIVITY_ANALYZED",
                "sensitivity_analysis",
                analysis_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM sensitivity_analyses WHERE id=?", (analysis_id,)).fetchone()
        return self._sensitivity(row, scenario, model.model_hash, parameter_unit)

    @staticmethod
    def _sensitivity(
        row,
        scenario: Scenario,
        model_hash: str,
        parameter_unit: str | None,
        idempotent: bool = False,
    ) -> SensitivityAnalysis:
        return SensitivityAnalysis(
            id=row["id"],
            scenario_id=row["scenario_id"],
            scenario_hash=scenario.scenario_hash,
            model_hash=model_hash,
            parameter=row["parameter"],
            parameter_unit=parameter_unit,
            grid=tuple(json.loads(row["grid_json"])),
            seed=row["seed"],
            iterations=row["iterations"],
            algorithm_version=row["algorithm_version"],
            reference_statistics=SimulationStatistics.model_validate_json(row["reference_statistics_json"]),
            points=tuple(SensitivityPoint.model_validate(item) for item in json.loads(row["points_json"])),
            metrics=SensitivityMetrics.model_validate_json(row["metrics_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            snapshot_hash=row["snapshot_hash"],
            reproducible=True,
            common_random_numbers=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_sensitivity(self, analysis_id: str) -> SensitivityAnalysis:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sensitivity_analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            raise KeyError("sensitivity analysis not found")
        scenario = self.get_scenario(row["scenario_id"])
        model = self.get_model(scenario.specification.model_id)
        variable = next(item for item in model.specification.variables if item.name == row["parameter"])
        return self._sensitivity(row, scenario, model.model_hash, variable.unit)

    def list_sensitivities(self) -> list[SensitivityAnalysis]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM sensitivity_analyses ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            scenario = self.get_scenario(row["scenario_id"])
            model = self.get_model(scenario.specification.model_id)
            variable = next(item for item in model.specification.variables if item.name == row["parameter"])
            results.append(self._sensitivity(row, scenario, model.model_hash, variable.unit))
        return results

    def _interaction_context(
        self, data: InteractionSurfaceCreate
    ) -> tuple[Scenario, SimulationModel, tuple[float, ...], tuple[float, ...], str, str | None, str | None]:
        scenario = self.get_scenario(data.scenario_id)
        model = self.get_model(scenario.specification.model_id)
        variables = {variable.name: variable for variable in model.specification.variables}
        for parameter in (data.parameter_x, data.parameter_y):
            if parameter not in variables:
                raise ValueError(f"unknown interaction parameter: {parameter}")
            if not self._parameter_influences_outcome(model.specification, parameter):
                raise ValueError(f"parameter {parameter} is incompatible with the configured outcome")
        grid_x, grid_y = data.resolved_grid_x(), data.resolved_grid_y()
        for parameter, grid in ((data.parameter_x, grid_x), (data.parameter_y, grid_y)):
            low, high = variables[parameter].bounds()
            if any(value < low or value > high for value in grid):
                raise ValueError(f"interaction grid for {parameter} must be within [{low}, {high}]")
        surface_key_hash = canonical_hash(
            {
                "parameter_x": data.parameter_x,
                "parameter_y": data.parameter_y,
                "grid_x": grid_x,
                "grid_y": grid_y,
            }
        )
        return (
            scenario,
            model,
            grid_x,
            grid_y,
            surface_key_hash,
            variables[data.parameter_x].unit,
            variables[data.parameter_y].unit,
        )

    @staticmethod
    def _interaction_qualification(metrics: InteractionMetrics, iterations: int) -> InteractionQualification:
        if iterations < MIN_INTERACTION_ITERATIONS:
            return InteractionQualification.INSUFFICIENT
        if metrics.relative_interaction_residual > INTERACTION_THRESHOLD:
            return InteractionQualification.INTERACTIVE
        if metrics.relative_mean_range > SURFACE_SENSITIVITY_THRESHOLD:
            return InteractionQualification.SENSITIVE
        return InteractionQualification.ADDITIVE

    def analyze_interaction_surface(self, data: InteractionSurfaceCreate) -> InteractionSurface:
        scenario, model, grid_x, grid_y, key_hash, unit_x, unit_y = self._interaction_context(data)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM interaction_surfaces WHERE scenario_id=? AND surface_key_hash=? "
                "AND seed=? AND iterations=? AND algorithm_version=?",
                (data.scenario_id, key_hash, data.seed, data.iterations, INTERACTION_ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._interaction_surface(existing, scenario, model.model_hash, unit_x, unit_y, idempotent=True)

        cells, metrics = simulate_interaction_surface(
            model.specification,
            scenario.specification.parameter_overrides,
            data.parameter_x,
            data.parameter_y,
            grid_x,
            grid_y,
            data.seed,
            data.iterations,
        )
        qualification = self._interaction_qualification(metrics, data.iterations)
        payload = {
            "scenario_hash": scenario.scenario_hash,
            "model_hash": model.model_hash,
            "parameter_x": data.parameter_x,
            "parameter_y": data.parameter_y,
            "parameter_x_unit": unit_x,
            "parameter_y_unit": unit_y,
            "grid_x": grid_x,
            "grid_y": grid_y,
            "seed": data.seed,
            "iterations": data.iterations,
            "algorithm_version": INTERACTION_ALGORITHM_VERSION,
            "cells": [cell.model_dump(mode="json") for cell in cells],
            "metrics": metrics.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        surface_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO interaction_surfaces VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    surface_id,
                    data.scenario_id,
                    data.parameter_x,
                    data.parameter_y,
                    json.dumps(grid_x),
                    json.dumps(grid_y),
                    key_hash,
                    data.seed,
                    data.iterations,
                    INTERACTION_ALGORITHM_VERSION,
                    json.dumps([cell.model_dump(mode="json") for cell in cells], sort_keys=True),
                    json.dumps(metrics.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    snapshot_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "INTERACTION_SURFACE_ANALYZED",
                "interaction_surface",
                surface_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM interaction_surfaces WHERE id=?", (surface_id,)).fetchone()
        return self._interaction_surface(row, scenario, model.model_hash, unit_x, unit_y)

    @staticmethod
    def _interaction_surface(
        row,
        scenario: Scenario,
        model_hash: str,
        unit_x: str | None,
        unit_y: str | None,
        idempotent: bool = False,
    ) -> InteractionSurface:
        return InteractionSurface(
            id=row["id"],
            scenario_id=row["scenario_id"],
            scenario_hash=scenario.scenario_hash,
            model_hash=model_hash,
            parameter_x=row["parameter_x"],
            parameter_y=row["parameter_y"],
            parameter_x_unit=unit_x,
            parameter_y_unit=unit_y,
            grid_x=tuple(json.loads(row["grid_x_json"])),
            grid_y=tuple(json.loads(row["grid_y_json"])),
            seed=row["seed"],
            iterations=row["iterations"],
            algorithm_version=row["algorithm_version"],
            cells=tuple(SurfaceCell.model_validate(item) for item in json.loads(row["cells_json"])),
            metrics=InteractionMetrics.model_validate_json(row["metrics_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            snapshot_hash=row["snapshot_hash"],
            reproducible=True,
            common_random_numbers=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_interaction_surface(self, surface_id: str) -> InteractionSurface:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM interaction_surfaces WHERE id=?", (surface_id,)).fetchone()
        if not row:
            raise KeyError("interaction surface not found")
        scenario = self.get_scenario(row["scenario_id"])
        model = self.get_model(scenario.specification.model_id)
        variables = {variable.name: variable for variable in model.specification.variables}
        return self._interaction_surface(
            row, scenario, model.model_hash, variables[row["parameter_x"]].unit, variables[row["parameter_y"]].unit
        )

    def list_interaction_surfaces(self) -> list[InteractionSurface]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM interaction_surfaces ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            scenario = self.get_scenario(row["scenario_id"])
            model = self.get_model(scenario.specification.model_id)
            variables = {variable.name: variable for variable in model.specification.variables}
            results.append(
                self._interaction_surface(
                    row,
                    scenario,
                    model.model_hash,
                    variables[row["parameter_x"]].unit,
                    variables[row["parameter_y"]].unit,
                )
            )
        return results

    def _verify_persisted_run(self, run_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"simulation run not found: {run_id}")
        scenario = self.get_scenario(row["scenario_id"])
        model = self.get_model(scenario.specification.model_id)
        errors: list[str] = []
        calculated_model_hash = canonical_hash(model.specification.model_dump(mode="json"))
        if calculated_model_hash != model.model_hash:
            errors.append(f"run {run_id}: model hash mismatch")
        calculated_scenario_hash = canonical_hash(
            {"model_hash": model.model_hash, "scenario": scenario.specification.model_dump(mode="json")}
        )
        if calculated_scenario_hash != scenario.scenario_hash:
            errors.append(f"run {run_id}: scenario hash mismatch")
        if row["algorithm_version"] != ALGORITHM_VERSION:
            errors.append(f"run {run_id}: unsupported simulation algorithm")
            recalculated = None
        else:
            recalculated = simulate(
                model.specification,
                scenario.specification.parameter_overrides,
                row["seed"],
                row["iterations"],
            )
            try:
                stored = SimulationStatistics.model_validate_json(row["statistics_json"])
            except Exception:
                stored = None
                errors.append(f"run {run_id}: invalid stored statistics")
            if stored is not None and stored != recalculated:
                errors.append(f"run {run_id}: statistics mismatch after recalculation")
            expected_payload = {
                "scenario_hash": scenario.scenario_hash,
                "seed": row["seed"],
                "iterations": row["iterations"],
                "algorithm_version": ALGORITHM_VERSION,
                "statistics": recalculated.model_dump(mode="json"),
                "qualification": "DESCRIPTIVE_ONLY",
                "warning": PERMANENT_WARNING,
            }
            if canonical_hash(expected_payload) != row["result_hash"]:
                errors.append(f"run {run_id}: result hash mismatch")
        return {
            "run_id": run_id,
            "scenario": scenario,
            "model": model,
            "seed": row["seed"],
            "iterations": row["iterations"],
            "statistics": recalculated,
            "errors": tuple(errors),
        }

    @staticmethod
    def _metric_value(statistics: SimulationStatistics, metric: RunMetric) -> float:
        return float(getattr(statistics, metric.value))

    @staticmethod
    def _build_envelopes(verified: list[dict]) -> tuple[MetricEnvelope, ...]:
        envelopes = []
        for metric in RunMetric:
            values = [Repository._metric_value(item["statistics"], metric) for item in verified]
            summary = _statistics(values)
            width = summary.maximum - summary.minimum
            scale = max(abs(summary.mean), 1.0)
            envelopes.append(
                MetricEnvelope(
                    metric=metric,
                    count=len(values),
                    minimum=summary.minimum,
                    maximum=summary.maximum,
                    mean=summary.mean,
                    p05=summary.p05,
                    median=summary.median,
                    p95=summary.p95,
                    width=round(width, 12),
                    relative_width=round(width / scale, 12),
                )
            )
        return tuple(envelopes)

    @staticmethod
    def _build_violations(verified: list[dict], limits: tuple[MetricLimit, ...]) -> tuple[LimitViolation, ...]:
        violations = []
        for item in verified:
            for limit in limits:
                value = Repository._metric_value(item["statistics"], limit.metric)
                if limit.minimum_allowed is not None and value < limit.minimum_allowed:
                    violations.append(
                        LimitViolation(
                            run_id=item["run_id"],
                            metric=limit.metric,
                            value=value,
                            bound=limit.minimum_allowed,
                            direction="BELOW_MINIMUM",
                        )
                    )
                if limit.maximum_allowed is not None and value > limit.maximum_allowed:
                    violations.append(
                        LimitViolation(
                            run_id=item["run_id"],
                            metric=limit.metric,
                            value=value,
                            bound=limit.maximum_allowed,
                            direction="ABOVE_MAXIMUM",
                        )
                    )
        return tuple(sorted(violations, key=lambda item: (item.run_id, item.metric.value, item.direction)))

    @staticmethod
    def _build_stability(verified: list[dict]) -> StabilityAnalysis:
        means = [item["statistics"].mean for item in verified]
        tolerance = 1e-12 * max(max(abs(value) for value in means), 1.0)
        signs = {1 if value > tolerance else -1 if value < -tolerance else 0 for value in means}
        if signs == {1}:
            direction = MeanDirection.POSITIVE
        elif signs == {-1}:
            direction = MeanDirection.NEGATIVE
        elif signs == {0}:
            direction = MeanDirection.ZERO
        else:
            direction = MeanDirection.MIXED

        comparable = 0
        agreements = 0
        for left in range(len(verified)):
            for right in range(left + 1, len(verified)):
                mean_delta = verified[left]["statistics"].mean - verified[right]["statistics"].mean
                median_delta = verified[left]["statistics"].median - verified[right]["statistics"].median
                if abs(mean_delta) <= tolerance or abs(median_delta) <= tolerance:
                    continue
                comparable += 1
                if (mean_delta > 0) == (median_delta > 0):
                    agreements += 1
        agreement = None if comparable == 0 else agreements / comparable
        if agreement is None:
            ranking = RankingStability.NOT_APPLICABLE
        elif agreement >= RANKING_AGREEMENT_THRESHOLD:
            ranking = RankingStability.STABLE
        else:
            ranking = RankingStability.MIXED
        return StabilityAnalysis(
            mean_direction=direction,
            ranking_stability=ranking,
            mean_median_pairwise_agreement=None if agreement is None else round(agreement, 12),
            comparable_pairs=comparable,
        )

    def create_uncertainty_dossier(self, data: UncertaintyDossierCreate) -> UncertaintyDossier:
        run_ids = data.canonical_run_ids()
        limits = data.canonical_limits()
        verified = [self._verify_persisted_run(run_id) for run_id in run_ids]
        individual_errors = [error for item in verified for error in item["errors"]]
        scenario_ids = {item["scenario"].id for item in verified}
        model_hashes = {item["model"].model_hash for item in verified}
        compatibility_errors = list(individual_errors)
        if len(scenario_ids) != 1:
            compatibility_errors.append("runs must reference the same frozen scenario")
        if len(model_hashes) != 1:
            compatibility_errors.append("runs must reference the same frozen model")
        compatibility_errors = sorted(set(compatibility_errors))
        compatible = not compatibility_errors
        scenario = verified[0]["scenario"] if len(scenario_ids) == 1 else None
        model_hash = verified[0]["model"].model_hash if len(model_hashes) == 1 else None
        request_payload = {
            "run_ids": run_ids,
            "limits": [limit.model_dump(mode="json") for limit in limits],
        }
        request_hash = canonical_hash(request_payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM uncertainty_dossiers WHERE request_hash=? AND algorithm_version=?",
                (request_hash, UNCERTAINTY_ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._uncertainty_dossier(existing, idempotent=True)

        thresholds = RobustnessThresholds(
            minimum_run_count=MIN_DOSSIER_RUNS,
            relative_width_threshold=UNCERTAINTY_WIDTH_THRESHOLD,
            ranking_agreement_threshold=RANKING_AGREEMENT_THRESHOLD,
        )
        valid_runs = [item for item in verified if not item["errors"]]
        if compatible:
            envelopes = self._build_envelopes(valid_runs)
            violations = self._build_violations(valid_runs, limits)
            stability = self._build_stability(valid_runs)
            violation_counts = {
                run_id: sum(1 for violation in violations if violation.run_id == run_id) for run_id in run_ids
            }
            worst = min(
                valid_runs,
                key=lambda item: (
                    -violation_counts[item["run_id"]],
                    item["statistics"].p05,
                    item["run_id"],
                ),
            )
            worst_run = WorstRun(
                run_id=worst["run_id"],
                seed=worst["seed"],
                iterations=worst["iterations"],
                p05=worst["statistics"].p05,
                mean=worst["statistics"].mean,
                violation_count=violation_counts[worst["run_id"]],
            )
            if len(valid_runs) < MIN_DOSSIER_RUNS:
                qualification = RobustnessQualification.INSUFFICIENT
            elif violations:
                qualification = RobustnessQualification.LIMIT_BREACH
            else:
                core_width = max(
                    envelope.relative_width
                    for envelope in envelopes
                    if envelope.metric in (RunMetric.MEAN, RunMetric.P05, RunMetric.P95)
                )
                qualification = (
                    RobustnessQualification.UNCERTAINTY_SENSITIVE
                    if core_width > UNCERTAINTY_WIDTH_THRESHOLD
                    else RobustnessQualification.ROBUST
                )
        else:
            envelopes = ()
            violations = ()
            stability = None
            worst_run = None
            qualification = RobustnessQualification.INCOMPATIBLE

        payload = {
            **request_payload,
            "scenario_id": scenario.id if scenario else None,
            "scenario_hash": scenario.scenario_hash if scenario else None,
            "model_hash": model_hash,
            "algorithm_version": UNCERTAINTY_ALGORITHM_VERSION,
            "verified_run_count": len(valid_runs),
            "compatibility_errors": compatibility_errors,
            "envelopes": [item.model_dump(mode="json") for item in envelopes],
            "violations": [item.model_dump(mode="json") for item in violations],
            "worst_run": worst_run.model_dump(mode="json") if worst_run else None,
            "stability": stability.model_dump(mode="json") if stability else None,
            "thresholds": thresholds.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        dossier_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO uncertainty_dossiers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    dossier_id,
                    request_hash,
                    json.dumps(run_ids),
                    json.dumps([limit.model_dump(mode="json") for limit in limits], sort_keys=True),
                    scenario.id if scenario else None,
                    scenario.scenario_hash if scenario else None,
                    model_hash,
                    UNCERTAINTY_ALGORITHM_VERSION,
                    len(valid_runs),
                    json.dumps(compatibility_errors),
                    json.dumps([item.model_dump(mode="json") for item in envelopes], sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in violations], sort_keys=True),
                    json.dumps(worst_run.model_dump(mode="json"), sort_keys=True) if worst_run else None,
                    json.dumps(stability.model_dump(mode="json"), sort_keys=True) if stability else None,
                    json.dumps(thresholds.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    snapshot_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "UNCERTAINTY_DOSSIER_CREATED",
                "uncertainty_dossier",
                dossier_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM uncertainty_dossiers WHERE id=?", (dossier_id,)).fetchone()
        return self._uncertainty_dossier(row)

    @staticmethod
    def _uncertainty_dossier(row, idempotent: bool = False) -> UncertaintyDossier:
        return UncertaintyDossier(
            id=row["id"],
            run_ids=tuple(json.loads(row["run_ids_json"])),
            limits=tuple(MetricLimit.model_validate(item) for item in json.loads(row["limits_json"])),
            scenario_id=row["scenario_id"],
            scenario_hash=row["scenario_hash"],
            model_hash=row["model_hash"],
            algorithm_version=row["algorithm_version"],
            verified_run_count=row["verified_run_count"],
            compatibility_errors=tuple(json.loads(row["compatibility_errors_json"])),
            envelopes=tuple(MetricEnvelope.model_validate(item) for item in json.loads(row["envelopes_json"])),
            violations=tuple(LimitViolation.model_validate(item) for item in json.loads(row["violations_json"])),
            worst_run=WorstRun.model_validate_json(row["worst_run_json"]) if row["worst_run_json"] else None,
            stability=StabilityAnalysis.model_validate_json(row["stability_json"]) if row["stability_json"] else None,
            thresholds=RobustnessThresholds.model_validate_json(row["thresholds_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            snapshot_hash=row["snapshot_hash"],
            reproducible=True,
            order_independent=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_uncertainty_dossier(self, dossier_id: str) -> UncertaintyDossier:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM uncertainty_dossiers WHERE id=?", (dossier_id,)).fetchone()
        if not row:
            raise KeyError("uncertainty dossier not found")
        return self._uncertainty_dossier(row)

    def list_uncertainty_dossiers(self) -> list[UncertaintyDossier]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM uncertainty_dossiers ORDER BY created_at DESC").fetchall()
        return [self._uncertainty_dossier(row) for row in rows]

    def create_convergence_dossier(self, data: ConvergenceDossierCreate) -> ConvergenceDossier:
        run_ids = data.canonical_run_ids()
        verified = [self._verify_persisted_run(run_id) for run_id in run_ids]
        errors = [error for item in verified for error in item["errors"]]
        scenario_ids = {item["scenario"].id for item in verified}
        model_hashes = {item["model"].model_hash for item in verified}
        seeds = {item["seed"] for item in verified}
        if len(scenario_ids) != 1:
            errors.append("runs must reference the same frozen scenario")
        if len(model_hashes) != 1:
            errors.append("runs must reference the same frozen model")
        if len(seeds) != 1:
            errors.append("runs must use the same seed to compare iteration budgets")
        compatibility_errors = tuple(sorted(set(errors)))
        compatible = not compatibility_errors
        valid_runs = [item for item in verified if not item["errors"]]
        scenario = verified[0]["scenario"] if len(scenario_ids) == 1 else None
        model_hash = verified[0]["model"].model_hash if len(model_hashes) == 1 else None
        seed = verified[0]["seed"] if len(seeds) == 1 else None
        request_payload = {"run_ids": run_ids}
        request_hash = canonical_hash(request_payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM convergence_dossiers WHERE request_hash=? AND algorithm_version=?",
                (request_hash, CONVERGENCE_ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._convergence_dossier(existing, idempotent=True)

        thresholds = ConvergenceThresholds(
            minimum_distinct_budgets=MIN_CONVERGENCE_BUDGETS,
            minimum_reference_iterations=MIN_REFERENCE_ITERATIONS,
            relative_deviation_threshold=CONVERGENCE_RELATIVE_THRESHOLD,
        )
        reference = None
        points: tuple[ConvergencePoint, ...] = ()
        worst_point = None
        if compatible:
            ordered = sorted(valid_runs, key=lambda item: (item["iterations"], item["run_id"]))
            reference = ordered[-1]
            built_points = []
            for item in ordered:
                absolute = {
                    metric: abs(float(getattr(item["statistics"], metric)) - float(getattr(reference["statistics"], metric)))
                    for metric in ("mean", "p05", "p95")
                }
                relative = {
                    metric: absolute[metric] / max(abs(float(getattr(reference["statistics"], metric))), 1.0)
                    for metric in ("mean", "p05", "p95")
                }
                maximum = max(relative.values())
                built_points.append(
                    ConvergencePoint(
                        run_id=item["run_id"],
                        iterations=item["iterations"],
                        statistics=item["statistics"],
                        absolute_deviation={**absolute},
                        relative_deviation=CoreMetricDeviation(
                            **relative,
                            maximum=round(maximum, 12),
                        ),
                    )
                )
            points = tuple(built_points)
            worst = max(points, key=lambda item: (item.relative_deviation.maximum, -item.iterations, item.run_id))
            worst_point = WorstConvergencePoint(
                run_id=worst.run_id,
                iterations=worst.iterations,
                maximum_relative_deviation=worst.relative_deviation.maximum,
            )
            distinct_budgets = len({item["iterations"] for item in ordered})
            if distinct_budgets < MIN_CONVERGENCE_BUDGETS or reference["iterations"] < MIN_REFERENCE_ITERATIONS:
                qualification = ConvergenceQualification.INSUFFICIENT
            elif worst.relative_deviation.maximum > CONVERGENCE_RELATIVE_THRESHOLD:
                qualification = ConvergenceQualification.UNSTABLE
            else:
                qualification = ConvergenceQualification.CONVERGED
        else:
            qualification = ConvergenceQualification.INCOMPATIBLE

        payload = {
            **request_payload,
            "scenario_id": scenario.id if scenario else None,
            "scenario_hash": scenario.scenario_hash if scenario else None,
            "model_hash": model_hash,
            "seed": seed,
            "algorithm_version": CONVERGENCE_ALGORITHM_VERSION,
            "reference_run_id": reference["run_id"] if reference else None,
            "verified_run_count": len(valid_runs),
            "compatibility_errors": compatibility_errors,
            "points": [item.model_dump(mode="json") for item in points],
            "worst_point": worst_point.model_dump(mode="json") if worst_point else None,
            "thresholds": thresholds.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        dossier_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO convergence_dossiers(
                    id,request_hash,run_ids_json,scenario_id,scenario_hash,model_hash,seed,algorithm_version,
                    reference_run_id,verified_run_count,compatibility_errors_json,points_json,worst_point_json,
                    thresholds_json,qualification,warning,snapshot_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    request_hash,
                    json.dumps(run_ids),
                    scenario.id if scenario else None,
                    scenario.scenario_hash if scenario else None,
                    model_hash,
                    seed,
                    CONVERGENCE_ALGORITHM_VERSION,
                    reference["run_id"] if reference else None,
                    len(valid_runs),
                    json.dumps(compatibility_errors),
                    json.dumps([item.model_dump(mode="json") for item in points], sort_keys=True),
                    json.dumps(worst_point.model_dump(mode="json"), sort_keys=True) if worst_point else None,
                    json.dumps(thresholds.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    snapshot_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "CONVERGENCE_DOSSIER_CREATED",
                "convergence_dossier",
                dossier_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM convergence_dossiers WHERE id=?", (dossier_id,)).fetchone()
        return self._convergence_dossier(row)

    @staticmethod
    def _convergence_dossier(row, idempotent: bool = False) -> ConvergenceDossier:
        return ConvergenceDossier(
            id=row["id"],
            run_ids=tuple(json.loads(row["run_ids_json"])),
            scenario_id=row["scenario_id"],
            scenario_hash=row["scenario_hash"],
            model_hash=row["model_hash"],
            seed=row["seed"],
            algorithm_version=row["algorithm_version"],
            reference_run_id=row["reference_run_id"],
            verified_run_count=row["verified_run_count"],
            compatibility_errors=tuple(json.loads(row["compatibility_errors_json"])),
            points=tuple(ConvergencePoint.model_validate(item) for item in json.loads(row["points_json"])),
            worst_point=(
                WorstConvergencePoint.model_validate_json(row["worst_point_json"])
                if row["worst_point_json"]
                else None
            ),
            thresholds=ConvergenceThresholds.model_validate_json(row["thresholds_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            snapshot_hash=row["snapshot_hash"],
            reproducible=True,
            order_independent=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_convergence_dossier(self, dossier_id: str) -> ConvergenceDossier:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM convergence_dossiers WHERE id=?", (dossier_id,)).fetchone()
        if not row:
            raise KeyError("convergence dossier not found")
        return self._convergence_dossier(row)

    def list_convergence_dossiers(self) -> list[ConvergenceDossier]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM convergence_dossiers ORDER BY created_at DESC").fetchall()
        return [self._convergence_dossier(row) for row in rows]

    def create_scenario_drift_dossier(self, data: ScenarioDriftDossierCreate) -> ScenarioDriftDossier:
        requested_run_ids = data.canonical_run_ids()
        verified = [self._verify_persisted_run(run_id) for run_id in requested_run_ids]
        errors = [error for item in verified for error in item["errors"]]
        model_ids = {item["model"].id for item in verified}
        model_hashes = {item["model"].model_hash for item in verified}
        seeds = {item["seed"] for item in verified}
        iteration_counts = {item["iterations"] for item in verified}
        scenario_ids = {item["scenario"].id for item in verified}
        if len(model_ids) != 1 or len(model_hashes) != 1:
            errors.append("runs must reference the same frozen model")
        if len(seeds) != 1:
            errors.append("runs must use the same seed")
        if len(iteration_counts) != 1:
            errors.append("runs must use the same iteration budget")
        if len(scenario_ids) < MIN_SCENARIO_DRIFT_RUNS:
            errors.append("runs must cover at least two distinct frozen scenarios")
        compatibility_errors = tuple(sorted(set(errors)))
        compatible = not compatibility_errors
        valid_runs = [item for item in verified if not item["errors"]]
        model_id = verified[0]["model"].id if len(model_ids) == 1 else None
        model_hash = verified[0]["model"].model_hash if len(model_hashes) == 1 else None
        seed = verified[0]["seed"] if len(seeds) == 1 else None
        iterations = verified[0]["iterations"] if len(iteration_counts) == 1 else None
        request_hash = canonical_hash({"run_ids": requested_run_ids})
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM scenario_drift_dossiers WHERE request_hash=? AND algorithm_version=?",
                (request_hash, SCENARIO_DRIFT_ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._scenario_drift_dossier(existing, idempotent=True)

        thresholds = ScenarioDriftThresholds(
            minimum_runs=MIN_SCENARIO_DRIFT_RUNS,
            minimum_iterations=MIN_SCENARIO_DRIFT_ITERATIONS,
            relative_drift_threshold=SCENARIO_DRIFT_RELATIVE_THRESHOLD,
        )
        points: tuple[ScenarioDriftPoint, ...] = ()
        transitions: tuple[ScenarioDriftTransition, ...] = ()
        worst_transition = None
        affected_scenario_ids: tuple[str, ...] = ()
        ordered_run_ids: tuple[str, ...] = requested_run_ids
        if compatible:
            ordered = sorted(
                valid_runs,
                key=lambda item: (item["scenario"].created_at, item["scenario"].id, item["run_id"]),
            )
            ordered_run_ids = tuple(item["run_id"] for item in ordered)
            points = tuple(
                ScenarioDriftPoint(
                    run_id=item["run_id"],
                    scenario_id=item["scenario"].id,
                    scenario_hash=item["scenario"].scenario_hash,
                    scenario_name=item["scenario"].specification.name,
                    scenario_version=item["scenario"].specification.version,
                    scenario_created_at=item["scenario"].created_at,
                    statistics=item["statistics"],
                )
                for item in ordered
            )
            built_transitions = []
            affected = set()
            for previous, current in zip(ordered, ordered[1:]):
                signed = {
                    metric: float(getattr(current["statistics"], metric))
                    - float(getattr(previous["statistics"], metric))
                    for metric in ("mean", "p05", "p95")
                }
                absolute = {metric: abs(value) for metric, value in signed.items()}
                relative = {
                    metric: absolute[metric] / max(abs(float(getattr(previous["statistics"], metric))), 1.0)
                    for metric in ("mean", "p05", "p95")
                }
                maximum = max(relative.values())
                tolerance = 1e-12 * max(abs(float(previous["statistics"].mean)), 1.0)
                if all(abs(value) <= tolerance for value in signed.values()):
                    direction = "STABLE"
                elif all(value >= -tolerance for value in signed.values()):
                    direction = "UPWARD"
                elif all(value <= tolerance for value in signed.values()):
                    direction = "DOWNWARD"
                else:
                    direction = "MIXED"
                transition = ScenarioDriftTransition(
                    from_run_id=previous["run_id"],
                    to_run_id=current["run_id"],
                    from_scenario_id=previous["scenario"].id,
                    to_scenario_id=current["scenario"].id,
                    absolute_delta=SensitivityDeltas(**{key: round(value, 12) for key, value in absolute.items()}),
                    relative_delta=CoreMetricDeviation(
                        **{key: round(value, 12) for key, value in relative.items()},
                        maximum=round(maximum, 12),
                    ),
                    direction=direction,
                )
                built_transitions.append(transition)
                if maximum > SCENARIO_DRIFT_RELATIVE_THRESHOLD:
                    affected.update((previous["scenario"].id, current["scenario"].id))
            transitions = tuple(built_transitions)
            affected_scenario_ids = tuple(sorted(affected))
            worst = max(
                transitions,
                key=lambda item: (item.relative_delta.maximum, item.from_run_id, item.to_run_id),
            )
            worst_transition = WorstScenarioDriftTransition(
                from_run_id=worst.from_run_id,
                to_run_id=worst.to_run_id,
                maximum_relative_delta=worst.relative_delta.maximum,
            )
            if iterations is None or iterations < MIN_SCENARIO_DRIFT_ITERATIONS:
                qualification = ScenarioDriftQualification.INSUFFICIENT
            elif worst.relative_delta.maximum > SCENARIO_DRIFT_RELATIVE_THRESHOLD:
                qualification = ScenarioDriftQualification.DRIFTING
            else:
                qualification = ScenarioDriftQualification.STABLE
        else:
            qualification = ScenarioDriftQualification.INCOMPATIBLE

        payload = {
            "requested_run_ids": requested_run_ids,
            "ordered_run_ids": ordered_run_ids,
            "model_id": model_id,
            "model_hash": model_hash,
            "seed": seed,
            "iterations": iterations,
            "algorithm_version": SCENARIO_DRIFT_ALGORITHM_VERSION,
            "verified_run_count": len(valid_runs),
            "compatibility_errors": compatibility_errors,
            "points": [item.model_dump(mode="json") for item in points],
            "transitions": [item.model_dump(mode="json") for item in transitions],
            "worst_transition": worst_transition.model_dump(mode="json") if worst_transition else None,
            "affected_scenario_ids": affected_scenario_ids,
            "thresholds": thresholds.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        dossier_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO scenario_drift_dossiers(
                    id,request_hash,requested_run_ids_json,ordered_run_ids_json,model_id,model_hash,seed,iterations,
                    algorithm_version,verified_run_count,compatibility_errors_json,points_json,transitions_json,
                    worst_transition_json,affected_scenario_ids_json,thresholds_json,qualification,warning,snapshot_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    request_hash,
                    json.dumps(requested_run_ids),
                    json.dumps(ordered_run_ids),
                    model_id,
                    model_hash,
                    seed,
                    iterations,
                    SCENARIO_DRIFT_ALGORITHM_VERSION,
                    len(valid_runs),
                    json.dumps(compatibility_errors),
                    json.dumps([item.model_dump(mode="json") for item in points], sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in transitions], sort_keys=True),
                    json.dumps(worst_transition.model_dump(mode="json"), sort_keys=True) if worst_transition else None,
                    json.dumps(affected_scenario_ids),
                    json.dumps(thresholds.model_dump(mode="json"), sort_keys=True),
                    qualification.value,
                    PERMANENT_WARNING,
                    snapshot_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "SCENARIO_DRIFT_DOSSIER_CREATED",
                "scenario_drift_dossier",
                dossier_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM scenario_drift_dossiers WHERE id=?", (dossier_id,)).fetchone()
        return self._scenario_drift_dossier(row)

    @staticmethod
    def _scenario_drift_dossier(row, idempotent: bool = False) -> ScenarioDriftDossier:
        return ScenarioDriftDossier(
            id=row["id"],
            requested_run_ids=tuple(json.loads(row["requested_run_ids_json"])),
            ordered_run_ids=tuple(json.loads(row["ordered_run_ids_json"])),
            model_id=row["model_id"],
            model_hash=row["model_hash"],
            seed=row["seed"],
            iterations=row["iterations"],
            algorithm_version=row["algorithm_version"],
            verified_run_count=row["verified_run_count"],
            compatibility_errors=tuple(json.loads(row["compatibility_errors_json"])),
            points=tuple(ScenarioDriftPoint.model_validate(item) for item in json.loads(row["points_json"])),
            transitions=tuple(
                ScenarioDriftTransition.model_validate(item) for item in json.loads(row["transitions_json"])
            ),
            worst_transition=(
                WorstScenarioDriftTransition.model_validate_json(row["worst_transition_json"])
                if row["worst_transition_json"]
                else None
            ),
            affected_scenario_ids=tuple(json.loads(row["affected_scenario_ids_json"])),
            thresholds=ScenarioDriftThresholds.model_validate_json(row["thresholds_json"]),
            qualification=row["qualification"],
            warning=row["warning"],
            snapshot_hash=row["snapshot_hash"],
            reproducible=True,
            order_independent=True,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_scenario_drift_dossier(self, dossier_id: str) -> ScenarioDriftDossier:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scenario_drift_dossiers WHERE id=?", (dossier_id,)).fetchone()
        if not row:
            raise KeyError("scenario drift dossier not found")
        return self._scenario_drift_dossier(row)

    def list_scenario_drift_dossiers(self) -> list[ScenarioDriftDossier]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM scenario_drift_dossiers ORDER BY created_at DESC").fetchall()
        return [self._scenario_drift_dossier(row) for row in rows]

    def _verify_persisted_scenario(self, scenario_id: str) -> dict:
        scenario = self.get_scenario(scenario_id)
        model = self.get_model(scenario.specification.model_id)
        errors: list[str] = []
        recomputed_model_hash = canonical_hash(model.specification.model_dump(mode="json"))
        if model.model_hash != recomputed_model_hash:
            errors.append(f"model hash mismatch for scenario {scenario_id}")
        recomputed_scenario_hash = canonical_hash(
            {
                "model_hash": recomputed_model_hash,
                "scenario": scenario.specification.model_dump(mode="json"),
            }
        )
        if scenario.scenario_hash != recomputed_scenario_hash:
            errors.append(f"scenario hash mismatch for scenario {scenario_id}")
        return {"scenario": scenario, "model": model, "errors": errors}

    def create_scenario_coverage_dossier(self, data: ScenarioCoverageDossierCreate) -> ScenarioCoverageDossier:
        requested_scenario_ids = data.canonical_scenario_ids()
        verified = [self._verify_persisted_scenario(scenario_id) for scenario_id in requested_scenario_ids]
        errors = [error for item in verified for error in item["errors"]]
        model_ids = {item["model"].id for item in verified}
        model_hashes = {item["model"].model_hash for item in verified}
        if len(model_ids) != 1 or len(model_hashes) != 1:
            errors.append("scenarios must reference the same frozen model")
        compatibility_errors = tuple(sorted(set(errors)))
        compatible = not compatibility_errors
        valid_scenarios = [item for item in verified if not item["errors"]]
        model_id = verified[0]["model"].id if len(model_ids) == 1 else None
        model_hash = verified[0]["model"].model_hash if len(model_hashes) == 1 else None
        request_hash = canonical_hash({"scenario_ids": requested_scenario_ids})
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM scenario_coverage_dossiers WHERE request_hash=? AND algorithm_version=?",
                (request_hash, SCENARIO_COVERAGE_ALGORITHM_VERSION),
            ).fetchone()
        if existing:
            return self._scenario_coverage_dossier(existing, idempotent=True)

        thresholds = ScenarioCoverageThresholds(
            minimum_scenarios=MIN_SCENARIO_COVERAGE_SCENARIOS,
            boundary_tolerance=SCENARIO_COVERAGE_BOUNDARY_TOLERANCE,
        )
        points: tuple[ScenarioCoveragePoint, ...] = ()
        parameter_coverage: tuple[ParameterCoverage, ...] = ()
        missing_parameters: tuple[str, ...] = ()
        partial_parameters: tuple[str, ...] = ()
        fully_covered_parameters: tuple[str, ...] = ()
        worst_parameter = None
        ordered_scenario_ids = requested_scenario_ids
        if compatible:
            ordered = sorted(
                valid_scenarios,
                key=lambda item: (item["scenario"].created_at, item["scenario"].id),
            )
            ordered_scenario_ids = tuple(item["scenario"].id for item in ordered)
            points = tuple(
                ScenarioCoveragePoint(
                    scenario_id=item["scenario"].id,
                    scenario_hash=item["scenario"].scenario_hash,
                    scenario_name=item["scenario"].specification.name,
                    scenario_version=item["scenario"].specification.version,
                    scenario_created_at=item["scenario"].created_at,
                    overridden_parameters=tuple(sorted(item["scenario"].specification.parameter_overrides)),
                )
                for item in ordered
            )
            model = ordered[0]["model"]
            coverage_items: list[ParameterCoverage] = []
            for variable in sorted(model.specification.variables, key=lambda item: item.name):
                lower, upper = (float(value) for value in variable.bounds())
                values = [
                    float(item["scenario"].specification.parameter_overrides[variable.name])
                    for item in ordered
                    if variable.name in item["scenario"].specification.parameter_overrides
                ]
                distinct = sorted(set(values))
                if lower == upper:
                    minimum = maximum = lower
                    span_ratio = 1.0
                    lower_covered = upper_covered = True
                    status = "CONSTANT"
                elif not values:
                    minimum = maximum = None
                    span_ratio = 0.0
                    lower_covered = upper_covered = False
                    status = "MISSING"
                else:
                    minimum, maximum = min(values), max(values)
                    span_ratio = min(1.0, max(0.0, (maximum - minimum) / (upper - lower)))
                    tolerance = SCENARIO_COVERAGE_BOUNDARY_TOLERANCE * max(abs(lower), abs(upper), 1.0)
                    lower_covered = abs(minimum - lower) <= tolerance
                    upper_covered = abs(maximum - upper) <= tolerance
                    status = "FULL" if lower_covered and upper_covered else "PARTIAL"
                coverage_items.append(
                    ParameterCoverage(
                        parameter=variable.name,
                        unit=variable.unit,
                        lower_bound=round(lower, 12),
                        upper_bound=round(upper, 12),
                        override_count=len(values),
                        distinct_override_count=len(distinct),
                        minimum_override=None if minimum is None else round(minimum, 12),
                        maximum_override=None if maximum is None else round(maximum, 12),
                        span_ratio=round(span_ratio, 12),
                        lower_bound_covered=lower_covered,
                        upper_bound_covered=upper_covered,
                        coverage_status=status,
                    )
                )
            parameter_coverage = tuple(coverage_items)
            missing_parameters = tuple(item.parameter for item in parameter_coverage if item.coverage_status == "MISSING")
            partial_parameters = tuple(item.parameter for item in parameter_coverage if item.coverage_status == "PARTIAL")
            fully_covered_parameters = tuple(
                item.parameter for item in parameter_coverage if item.coverage_status in {"FULL", "CONSTANT"}
            )
            rank = {"MISSING": 0, "PARTIAL": 1, "FULL": 2, "CONSTANT": 3}
            worst = min(
                parameter_coverage,
                key=lambda item: (rank[item.coverage_status], item.span_ratio, item.distinct_override_count, item.parameter),
            )
            worst_parameter = WorstParameterCoverage(
                parameter=worst.parameter,
                coverage_status=worst.coverage_status,
                span_ratio=worst.span_ratio,
                distinct_override_count=worst.distinct_override_count,
            )
            if len(ordered) < MIN_SCENARIO_COVERAGE_SCENARIOS:
                qualification = ScenarioCoverageQualification.INSUFFICIENT
            elif missing_parameters or partial_parameters:
                qualification = ScenarioCoverageQualification.PARTIAL
            else:
                qualification = ScenarioCoverageQualification.COMPLETE
        else:
            qualification = ScenarioCoverageQualification.INCOMPATIBLE

        payload = {
            "requested_scenario_ids": requested_scenario_ids,
            "ordered_scenario_ids": ordered_scenario_ids,
            "model_id": model_id,
            "model_hash": model_hash,
            "algorithm_version": SCENARIO_COVERAGE_ALGORITHM_VERSION,
            "verified_scenario_count": len(valid_scenarios),
            "compatibility_errors": compatibility_errors,
            "points": [item.model_dump(mode="json") for item in points],
            "parameter_coverage": [item.model_dump(mode="json") for item in parameter_coverage],
            "missing_parameters": missing_parameters,
            "partial_parameters": partial_parameters,
            "fully_covered_parameters": fully_covered_parameters,
            "worst_parameter": worst_parameter.model_dump(mode="json") if worst_parameter else None,
            "thresholds": thresholds.model_dump(mode="json"),
            "qualification": qualification.value,
            "warning": PERMANENT_WARNING,
        }
        snapshot_hash = canonical_hash(payload)
        dossier_id, created_at = str(uuid.uuid4()), now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO scenario_coverage_dossiers(
                    id,request_hash,requested_scenario_ids_json,ordered_scenario_ids_json,model_id,model_hash,
                    algorithm_version,verified_scenario_count,compatibility_errors_json,points_json,
                    parameter_coverage_json,missing_parameters_json,partial_parameters_json,
                    fully_covered_parameters_json,worst_parameter_json,thresholds_json,qualification,
                    warning,snapshot_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id, request_hash, json.dumps(requested_scenario_ids), json.dumps(ordered_scenario_ids),
                    model_id, model_hash, SCENARIO_COVERAGE_ALGORITHM_VERSION, len(valid_scenarios),
                    json.dumps(compatibility_errors),
                    json.dumps([item.model_dump(mode="json") for item in points], sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in parameter_coverage], sort_keys=True),
                    json.dumps(missing_parameters), json.dumps(partial_parameters), json.dumps(fully_covered_parameters),
                    json.dumps(worst_parameter.model_dump(mode="json"), sort_keys=True) if worst_parameter else None,
                    json.dumps(thresholds.model_dump(mode="json"), sort_keys=True), qualification.value,
                    PERMANENT_WARNING, snapshot_hash, created_at,
                ),
            )
            self._audit(
                connection,
                "SCENARIO_COVERAGE_DOSSIER_CREATED",
                "scenario_coverage_dossier",
                dossier_id,
                {"snapshot_hash": snapshot_hash, "qualification": qualification.value},
            )
            row = connection.execute("SELECT * FROM scenario_coverage_dossiers WHERE id=?", (dossier_id,)).fetchone()
        return self._scenario_coverage_dossier(row)

    @staticmethod
    def _scenario_coverage_dossier(row, idempotent: bool = False) -> ScenarioCoverageDossier:
        return ScenarioCoverageDossier(
            id=row["id"],
            requested_scenario_ids=tuple(json.loads(row["requested_scenario_ids_json"])),
            ordered_scenario_ids=tuple(json.loads(row["ordered_scenario_ids_json"])),
            model_id=row["model_id"], model_hash=row["model_hash"], algorithm_version=row["algorithm_version"],
            verified_scenario_count=row["verified_scenario_count"],
            compatibility_errors=tuple(json.loads(row["compatibility_errors_json"])),
            points=tuple(ScenarioCoveragePoint.model_validate(item) for item in json.loads(row["points_json"])),
            parameter_coverage=tuple(
                ParameterCoverage.model_validate(item) for item in json.loads(row["parameter_coverage_json"])
            ),
            missing_parameters=tuple(json.loads(row["missing_parameters_json"])),
            partial_parameters=tuple(json.loads(row["partial_parameters_json"])),
            fully_covered_parameters=tuple(json.loads(row["fully_covered_parameters_json"])),
            worst_parameter=(
                WorstParameterCoverage.model_validate_json(row["worst_parameter_json"])
                if row["worst_parameter_json"] else None
            ),
            thresholds=ScenarioCoverageThresholds.model_validate_json(row["thresholds_json"]),
            qualification=row["qualification"], warning=row["warning"], snapshot_hash=row["snapshot_hash"],
            reproducible=True, order_independent=True, idempotent_replay=idempotent, created_at=row["created_at"],
        )

    def get_scenario_coverage_dossier(self, dossier_id: str) -> ScenarioCoverageDossier:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scenario_coverage_dossiers WHERE id=?", (dossier_id,)).fetchone()
        if not row:
            raise KeyError("scenario coverage dossier not found")
        return self._scenario_coverage_dossier(row)

    def list_scenario_coverage_dossiers(self) -> list[ScenarioCoverageDossier]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM scenario_coverage_dossiers ORDER BY created_at DESC").fetchall()
        return [self._scenario_coverage_dossier(row) for row in rows]

    def list_audit_events(self) -> list[AuditEvent]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
        return [
            AuditEvent(
                id=row["id"],
                event_type=row["event_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                payload=json.loads(row["payload_json"]),
                previous_hash=row["previous_hash"],
                event_hash=row["event_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
