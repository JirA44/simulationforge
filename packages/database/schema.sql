-- Schéma PostgreSQL 15+ de référence pour SimulationForge V1.07.
CREATE TABLE simulation_models (
    id UUID PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    version VARCHAR(32) NOT NULL,
    model_hash CHAR(64) NOT NULL UNIQUE,
    specification_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (name, version)
);

CREATE TABLE scenarios (
    id UUID PRIMARY KEY,
    model_id UUID NOT NULL REFERENCES simulation_models(id),
    name VARCHAR(64) NOT NULL,
    version VARCHAR(32) NOT NULL,
    scenario_hash CHAR(64) NOT NULL UNIQUE,
    specification_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (model_id, name, version)
);

CREATE TABLE simulation_runs (
    id UUID PRIMARY KEY,
    scenario_id UUID NOT NULL REFERENCES scenarios(id),
    seed BIGINT NOT NULL,
    iterations INTEGER NOT NULL CHECK (iterations BETWEEN 1 AND 10000),
    algorithm_version VARCHAR(64) NOT NULL,
    statistics_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification = 'DESCRIPTIVE_ONLY'),
    warning TEXT NOT NULL,
    result_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (scenario_id, seed, iterations, algorithm_version)
);

CREATE TABLE scenario_comparisons (
    id UUID PRIMARY KEY,
    baseline_scenario_id UUID NOT NULL REFERENCES scenarios(id),
    stress_scenario_id UUID NOT NULL REFERENCES scenarios(id),
    seed BIGINT NOT NULL,
    iterations INTEGER NOT NULL CHECK (iterations BETWEEN 1 AND 10000),
    algorithm_version VARCHAR(64) NOT NULL,
    baseline_statistics_json JSONB NOT NULL,
    stress_statistics_json JSONB NOT NULL,
    deltas_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('ROBUST', 'FRAGILE', 'INSUFFICIENT')),
    warning TEXT NOT NULL,
    report_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (baseline_scenario_id <> stress_scenario_id),
    UNIQUE (baseline_scenario_id, stress_scenario_id, seed, iterations, algorithm_version)
);

CREATE TABLE sensitivity_analyses (
    id UUID PRIMARY KEY,
    scenario_id UUID NOT NULL REFERENCES scenarios(id),
    parameter VARCHAR(64) NOT NULL,
    grid_json JSONB NOT NULL,
    grid_hash CHAR(64) NOT NULL,
    seed BIGINT NOT NULL,
    iterations INTEGER NOT NULL CHECK (iterations BETWEEN 1 AND 10000),
    algorithm_version VARCHAR(64) NOT NULL,
    reference_statistics_json JSONB NOT NULL,
    points_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('STABLE', 'SENSITIVE', 'INSUFFICIENT')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (scenario_id, parameter, grid_hash, seed, iterations, algorithm_version)
);

CREATE TABLE interaction_surfaces (
    id UUID PRIMARY KEY,
    scenario_id UUID NOT NULL REFERENCES scenarios(id),
    parameter_x VARCHAR(64) NOT NULL,
    parameter_y VARCHAR(64) NOT NULL,
    grid_x_json JSONB NOT NULL,
    grid_y_json JSONB NOT NULL,
    surface_key_hash CHAR(64) NOT NULL,
    seed BIGINT NOT NULL,
    iterations INTEGER NOT NULL CHECK (iterations BETWEEN 1 AND 10000),
    algorithm_version VARCHAR(64) NOT NULL,
    cells_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('ADDITIVE', 'INTERACTIVE', 'SENSITIVE', 'INSUFFICIENT')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (parameter_x <> parameter_y),
    UNIQUE (scenario_id, surface_key_hash, seed, iterations, algorithm_version)
);

CREATE TABLE uncertainty_dossiers (
    id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    run_ids_json JSONB NOT NULL,
    limits_json JSONB NOT NULL,
    scenario_id UUID REFERENCES scenarios(id),
    scenario_hash CHAR(64),
    model_hash CHAR(64),
    algorithm_version VARCHAR(64) NOT NULL,
    verified_run_count INTEGER NOT NULL CHECK (verified_run_count BETWEEN 0 AND 100),
    compatibility_errors_json JSONB NOT NULL,
    envelopes_json JSONB NOT NULL,
    violations_json JSONB NOT NULL,
    worst_run_json JSONB,
    stability_json JSONB,
    thresholds_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('ROBUST', 'UNCERTAINTY_SENSITIVE', 'LIMIT_BREACH', 'INSUFFICIENT', 'INCOMPATIBLE')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (request_hash, algorithm_version)
);

CREATE TABLE convergence_dossiers (
    id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    run_ids_json JSONB NOT NULL,
    scenario_id UUID REFERENCES scenarios(id),
    scenario_hash CHAR(64),
    model_hash CHAR(64),
    seed BIGINT,
    algorithm_version VARCHAR(64) NOT NULL,
    reference_run_id UUID REFERENCES simulation_runs(id),
    verified_run_count INTEGER NOT NULL CHECK (verified_run_count BETWEEN 0 AND 50),
    compatibility_errors_json JSONB NOT NULL,
    points_json JSONB NOT NULL,
    worst_point_json JSONB,
    thresholds_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('CONVERGED', 'UNSTABLE', 'INSUFFICIENT', 'INCOMPATIBLE')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (request_hash, algorithm_version)
);

CREATE INDEX convergence_dossiers_created_idx ON convergence_dossiers (created_at DESC);

CREATE TABLE scenario_drift_dossiers (
    id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    requested_run_ids_json JSONB NOT NULL,
    ordered_run_ids_json JSONB NOT NULL,
    model_id UUID REFERENCES simulation_models(id),
    model_hash CHAR(64),
    seed BIGINT,
    iterations INTEGER,
    algorithm_version VARCHAR(64) NOT NULL,
    verified_run_count INTEGER NOT NULL CHECK (verified_run_count BETWEEN 0 AND 100),
    compatibility_errors_json JSONB NOT NULL,
    points_json JSONB NOT NULL,
    transitions_json JSONB NOT NULL,
    worst_transition_json JSONB,
    affected_scenario_ids_json JSONB NOT NULL,
    thresholds_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('STABLE', 'DRIFTING', 'INSUFFICIENT', 'INCOMPATIBLE')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (request_hash, algorithm_version)
);

CREATE INDEX scenario_drift_dossiers_created_idx ON scenario_drift_dossiers (created_at DESC);

CREATE TABLE scenario_coverage_dossiers (
    id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    requested_scenario_ids_json JSONB NOT NULL,
    ordered_scenario_ids_json JSONB NOT NULL,
    model_id UUID REFERENCES simulation_models(id),
    model_hash CHAR(64),
    algorithm_version VARCHAR(64) NOT NULL,
    verified_scenario_count INTEGER NOT NULL CHECK (verified_scenario_count BETWEEN 0 AND 100),
    compatibility_errors_json JSONB NOT NULL,
    points_json JSONB NOT NULL,
    parameter_coverage_json JSONB NOT NULL,
    missing_parameters_json JSONB NOT NULL,
    partial_parameters_json JSONB NOT NULL,
    fully_covered_parameters_json JSONB NOT NULL,
    worst_parameter_json JSONB,
    thresholds_json JSONB NOT NULL,
    qualification VARCHAR(32) NOT NULL CHECK (qualification IN ('COMPLETE', 'PARTIAL', 'INSUFFICIENT', 'INCOMPATIBLE')),
    warning TEXT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (request_hash, algorithm_version)
);

CREATE INDEX scenario_coverage_dossiers_created_idx ON scenario_coverage_dossiers (created_at DESC);

CREATE TABLE audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id UUID NOT NULL,
    payload_json JSONB NOT NULL,
    previous_hash CHAR(64),
    event_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE FUNCTION prevent_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'SimulationForge records are immutable/append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER simulation_models_immutable BEFORE UPDATE OR DELETE ON simulation_models
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER scenarios_immutable BEFORE UPDATE OR DELETE ON scenarios
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER simulation_runs_immutable BEFORE UPDATE OR DELETE ON simulation_runs
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER scenario_comparisons_immutable BEFORE UPDATE OR DELETE ON scenario_comparisons
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER sensitivity_analyses_immutable BEFORE UPDATE OR DELETE ON sensitivity_analyses
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER interaction_surfaces_immutable BEFORE UPDATE OR DELETE ON interaction_surfaces
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER uncertainty_dossiers_immutable BEFORE UPDATE OR DELETE ON uncertainty_dossiers
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER convergence_dossiers_immutable BEFORE UPDATE OR DELETE ON convergence_dossiers
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER scenario_drift_dossiers_immutable BEFORE UPDATE OR DELETE ON scenario_drift_dossiers
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER scenario_coverage_dossiers_immutable BEFORE UPDATE OR DELETE ON scenario_coverage_dossiers
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
