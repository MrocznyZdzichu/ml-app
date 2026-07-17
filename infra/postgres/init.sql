CREATE SCHEMA IF NOT EXISTS mlapp;

CREATE TABLE IF NOT EXISTS mlapp.schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mlapp.user_accounts (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON mlapp.user_accounts(email);

CREATE TABLE IF NOT EXISTS mlapp.data_assets (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    format VARCHAR(32) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    original_filename VARCHAR(512),
    location_uri TEXT,
    file_size_bytes INTEGER,
    row_count INTEGER,
    has_header BOOLEAN,
    uploaded_by VARCHAR(64),
    uploaded_at TIMESTAMPTZ,
    deleted_by VARCHAR(64),
    deleted_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_data_assets_owner_id ON mlapp.data_assets(owner_id);

CREATE TABLE IF NOT EXISTS mlapp.business_cases (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    problem_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    business_owner VARCHAR(255) NOT NULL DEFAULT '',
    primary_metric VARCHAR(128) NOT NULL DEFAULT '',
    target_column VARCHAR(255) NOT NULL DEFAULT '',
    business_goal TEXT NOT NULL DEFAULT '',
    success_criteria TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(64) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_business_cases_owner_id ON mlapp.business_cases(owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_business_cases_name ON mlapp.business_cases(LOWER(name));

CREATE TABLE IF NOT EXISTS mlapp.artifacts (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    type VARCHAR(64) NOT NULL,
    reference_id VARCHAR(128) NOT NULL,
    origin VARCHAR(64) NOT NULL,
    business_case_id VARCHAR(64),
    external_notes TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_owner_id ON mlapp.artifacts(owner_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_reference_id ON mlapp.artifacts(reference_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_business_case_id ON mlapp.artifacts(business_case_id);

CREATE TABLE IF NOT EXISTS mlapp.business_case_data_attachments (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    business_case_id VARCHAR(64) NOT NULL,
    artifact_id VARCHAR(64) NOT NULL,
    data_asset_id VARCHAR(64) NOT NULL,
    data_asset_kind VARCHAR(32) NOT NULL,
    role VARCHAR(64) NOT NULL,
    context_note TEXT NOT NULL DEFAULT '',
    primary_key_column VARCHAR(255) NOT NULL DEFAULT '',
    target_column VARCHAR(255) NOT NULL DEFAULT '',
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bc_data_attachments_owner_id ON mlapp.business_case_data_attachments(owner_id);
CREATE INDEX IF NOT EXISTS idx_bc_data_attachments_business_case_id ON mlapp.business_case_data_attachments(business_case_id);
CREATE INDEX IF NOT EXISTS idx_bc_data_attachments_artifact_id ON mlapp.business_case_data_attachments(artifact_id);
CREATE INDEX IF NOT EXISTS idx_bc_data_attachments_data_asset_id ON mlapp.business_case_data_attachments(data_asset_id);

CREATE TABLE IF NOT EXISTS mlapp.pipelines (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    business_case_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipelines_owner_id ON mlapp.pipelines(owner_id);
CREATE INDEX IF NOT EXISTS idx_pipelines_business_case_id ON mlapp.pipelines(business_case_id);

CREATE TABLE IF NOT EXISTS mlapp.pipeline_versions (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    pipeline_id VARCHAR(64) NOT NULL,
    business_case_id VARCHAR(64) NOT NULL,
    version_number INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    definition JSONB NOT NULL DEFAULT '{}'::jsonb,
    definition_hash VARCHAR(64) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_by VARCHAR(64) NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_versions_owner_id ON mlapp.pipeline_versions(owner_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_versions_pipeline_id ON mlapp.pipeline_versions(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_versions_business_case_id ON mlapp.pipeline_versions(business_case_id);

CREATE TABLE IF NOT EXISTS mlapp.pipeline_runs (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    pipeline_id VARCHAR(64) NOT NULL,
    pipeline_version_id VARCHAR(64) NOT NULL,
    business_case_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL,
    runtime_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_dry_run BOOLEAN NOT NULL DEFAULT false,
    requested_step_id VARCHAR(128) NOT NULL DEFAULT '',
    input_row_count INTEGER,
    processed_row_count INTEGER,
    output_row_count INTEGER,
    rejected_row_count INTEGER,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_artifact_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_manifest JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_owner_id ON mlapp.pipeline_runs(owner_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_id ON mlapp.pipeline_runs(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_version_id ON mlapp.pipeline_runs(pipeline_version_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_business_case_id ON mlapp.pipeline_runs(business_case_id);
