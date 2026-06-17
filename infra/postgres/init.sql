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
