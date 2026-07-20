from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.core.database import get_engine


MigrationAction = Callable[[Connection], None]


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    apply: MigrationAction


def run_migrations(engine: Engine | None = None) -> list[str]:
    target = engine or get_engine()
    applied_now: list[str] = []
    with target.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS mlapp"))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS mlapp.schema_migrations ("
            "version VARCHAR(128) PRIMARY KEY, "
            "description TEXT NOT NULL, "
            "applied_at TIMESTAMPTZ NOT NULL"
            ")"
        ))
        connection.execute(text(
            "ALTER TABLE mlapp.schema_migrations "
            "ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''"
        ))
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(684617070)"))
        applied = {
            str(row[0])
            for row in connection.execute(text(
                "SELECT version FROM mlapp.schema_migrations"
            ))
        }
        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            migration.apply(connection)
            connection.execute(
                text(
                    "INSERT INTO mlapp.schema_migrations "
                    "(version, description, applied_at) "
                    "VALUES (:version, :description, :applied_at)"
                ),
                {
                    "version": migration.version,
                    "description": migration.description,
                    "applied_at": datetime.now(timezone.utc),
                },
            )
            applied_now.append(migration.version)
        _ensure_root_account(connection)
    return applied_now


def _ensure_root_account(connection: Connection) -> None:
    """Repair the reserved root identity without ever resetting its password."""
    exists = connection.execute(text(
        "SELECT 1 FROM mlapp.user_accounts WHERE id = 'root'"
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if exists is None:
        from app.core.security import hash_password
        connection.execute(
            text(
                "INSERT INTO mlapp.user_accounts "
                "(id, login_name, email, display_name, password_hash, roles, is_active, "
                "is_technical, session_version, created_at, updated_at) "
                "VALUES ('root', 'root', 'root@local.invalid', 'Root Administrator', :password_hash, "
                "'[\"user\", \"administrator\"]'::jsonb, TRUE, TRUE, 1, :now, :now)"
            ),
            {"password_hash": hash_password("toor"), "now": now},
        )
        return
    connection.execute(text(
        "UPDATE mlapp.user_accounts SET login_name = 'root', is_active = TRUE, "
        "is_technical = TRUE, roles = '[\"user\", \"administrator\"]'::jsonb, "
        "session_version = CASE WHEN is_active = FALSE OR roles::jsonb <> "
        "'[\"user\", \"administrator\"]'::jsonb THEN session_version + 1 ELSE session_version END, "
        "updated_at = CASE WHEN is_active = FALSE OR roles::jsonb <> "
        "'[\"user\", \"administrator\"]'::jsonb THEN :now ELSE updated_at END "
        "WHERE id = 'root'"
    ), {"now": now})


def _materialize_group_owners(connection: Connection) -> None:
    connection.execute(text(
        "INSERT INTO mlapp.group_memberships "
        "(id, group_id, user_id, membership_role, added_by, created_at) "
        "SELECT 'owner-' || md5(g.id || ':' || g.owner_id), g.id, g.owner_id, 'owner', "
        "g.created_by, g.created_at FROM mlapp.access_groups g "
        "WHERE NOT EXISTS (SELECT 1 FROM mlapp.group_memberships m "
        "WHERE m.group_id = g.id AND m.user_id = g.owner_id)"
    ))


def _enforce_unique_business_case_names(connection: Connection) -> None:
    """Deduplicate legacy names and enforce global case-insensitive uniqueness."""
    connection.execute(text(
        "WITH ranked AS ("
        "SELECT id, name, row_number() OVER ("
        "PARTITION BY lower(btrim(name)) ORDER BY created_at, id"
        ") AS duplicate_number FROM mlapp.business_cases"
        ") "
        "UPDATE mlapp.business_cases AS bc "
        "SET name = left(btrim(bc.name), 178) || ' (duplicate ' || bc.id || ')' "
        "FROM ranked WHERE ranked.id = bc.id AND ranked.duplicate_number > 1"
    ))
    connection.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_business_cases_name "
        "ON mlapp.business_cases (lower(name))"
    ))


def _legacy_schema_hardening(connection: Connection) -> None:
    inspector = inspect(connection)
    if inspector.has_table("data_assets", schema="mlapp"):
        statements = [
            "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(64)",
            "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
            (
                "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS "
                "metadata JSONB NOT NULL DEFAULT '{}'::jsonb"
            ),
            "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS logical_id VARCHAR(64)",
            "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS version_number INTEGER",
            "ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS version_stage VARCHAR(32)",
            "UPDATE mlapp.data_assets SET logical_id = id WHERE logical_id IS NULL",
            (
                "UPDATE mlapp.data_assets SET logical_id = 'logical-' || id "
                "WHERE logical_id = id"
            ),
            "UPDATE mlapp.data_assets SET version_number = 1 WHERE version_number IS NULL",
            (
                "UPDATE mlapp.data_assets SET version_stage = "
                "CASE WHEN source_type = 'view' THEN 'view' ELSE 'source' END "
                "WHERE version_stage IS NULL"
            ),
            "ALTER TABLE mlapp.data_assets ALTER COLUMN logical_id SET NOT NULL",
            "ALTER TABLE mlapp.data_assets ALTER COLUMN version_number SET NOT NULL",
            "ALTER TABLE mlapp.data_assets ALTER COLUMN version_stage SET NOT NULL",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_data_assets_logical_version "
                "ON mlapp.data_assets(owner_id, logical_id, version_number)"
            ),
        ]
        for statement in statements:
            connection.execute(text(statement))


def _identity_and_access_control(connection: Connection) -> None:
    """Create the single-company identity, sharing and audit foundation."""
    from app.core.security import hash_password
    inspector = inspect(connection)

    statements = [
        (
            "CREATE TABLE IF NOT EXISTS mlapp.user_accounts ("
            "id VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE, "
            "display_name VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, "
            "roles JSONB NOT NULL DEFAULT '[\"user\"]'::jsonb, "
            "created_at TIMESTAMPTZ NOT NULL)"
        ),
        "ALTER TABLE mlapp.user_accounts ADD COLUMN IF NOT EXISTS login_name VARCHAR(320)",
        "ALTER TABLE mlapp.user_accounts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE mlapp.user_accounts ADD COLUMN IF NOT EXISTS is_technical BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE mlapp.user_accounts ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE mlapp.user_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "UPDATE mlapp.user_accounts SET login_name = LOWER(email) WHERE login_name IS NULL",
        "UPDATE mlapp.user_accounts SET updated_at = created_at WHERE updated_at IS NULL",
        (
            "UPDATE mlapp.user_accounts SET roles = '[\"user\"]'::jsonb "
            "WHERE roles IS NULL OR roles::jsonb = '[\"owner\"]'::jsonb OR roles::jsonb = '[]'::jsonb"
        ),
        "ALTER TABLE mlapp.user_accounts ALTER COLUMN login_name SET NOT NULL",
        "ALTER TABLE mlapp.user_accounts ALTER COLUMN updated_at SET NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_accounts_login_name ON mlapp.user_accounts (LOWER(login_name))",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.access_groups ("
            "id VARCHAR(64) PRIMARY KEY, name VARCHAR(255) NOT NULL, description TEXT NOT NULL DEFAULT '', "
            "is_active BOOLEAN NOT NULL DEFAULT TRUE, owner_id VARCHAR(64) NOT NULL, "
            "created_by VARCHAR(64) NOT NULL, updated_by VARCHAR(64) NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)"
        ),
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_access_groups_name ON mlapp.access_groups (LOWER(name))",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.group_memberships ("
            "id VARCHAR(64) PRIMARY KEY, group_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL, "
            "membership_role VARCHAR(32) NOT NULL DEFAULT 'member', added_by VARCHAR(64) NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL, UNIQUE(group_id, user_id))"
        ),
        "CREATE INDEX IF NOT EXISTS ix_group_memberships_user ON mlapp.group_memberships (user_id)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.business_case_grants ("
            "id VARCHAR(64) PRIMARY KEY, business_case_id VARCHAR(64) NOT NULL, "
            "subject_type VARCHAR(16) NOT NULL, subject_id VARCHAR(64) NOT NULL, "
            "access_role VARCHAR(32) NOT NULL, granted_by VARCHAR(64) NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ, "
            "UNIQUE(business_case_id, subject_type, subject_id))"
        ),
        "CREATE INDEX IF NOT EXISTS ix_bc_grants_subject ON mlapp.business_case_grants (subject_type, subject_id)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.resource_grants ("
            "id VARCHAR(64) PRIMARY KEY, resource_kind VARCHAR(32) NOT NULL, resource_id VARCHAR(64) NOT NULL, "
            "subject_type VARCHAR(16) NOT NULL, subject_id VARCHAR(64) NOT NULL, "
            "access_role VARCHAR(32) NOT NULL, granted_by VARCHAR(64) NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ, "
            "UNIQUE(resource_kind, resource_id, subject_type, subject_id))"
        ),
        "CREATE INDEX IF NOT EXISTS ix_resource_grants_subject ON mlapp.resource_grants (subject_type, subject_id)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.audit_events ("
            "id VARCHAR(64) PRIMARY KEY, actor_id VARCHAR(64) NOT NULL, action VARCHAR(128) NOT NULL, "
            "subject_type VARCHAR(32) NOT NULL DEFAULT '', subject_id VARCHAR(64) NOT NULL DEFAULT '', "
            "resource_kind VARCHAR(32) NOT NULL DEFAULT '', resource_id VARCHAR(64) NOT NULL DEFAULT '', "
            "previous_state JSONB NOT NULL DEFAULT '{}'::jsonb, new_state JSONB NOT NULL DEFAULT '{}'::jsonb, "
            "reason TEXT NOT NULL DEFAULT '', request_id VARCHAR(128) NOT NULL DEFAULT '', "
            "created_at TIMESTAMPTZ NOT NULL)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_audit_events_created ON mlapp.audit_events (created_at DESC)",
    ]
    for statement in statements:
        connection.execute(text(statement))

    now = datetime.now(timezone.utc)
    connection.execute(
        text(
            "INSERT INTO mlapp.user_accounts "
            "(id, login_name, email, display_name, password_hash, roles, is_active, "
            "is_technical, session_version, created_at, updated_at) "
            "VALUES ('root', 'root', 'root@local.invalid', 'Root Administrator', :password_hash, "
            "'[\"user\", \"administrator\"]'::jsonb, TRUE, TRUE, 1, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"password_hash": hash_password("toor"), "now": now},
    )

    if inspector.has_table("pipeline_runs", schema="mlapp"):
        statements = [
            (
                "ALTER TABLE mlapp.pipeline_runs ADD COLUMN IF NOT EXISTS "
                "output_manifest JSONB NOT NULL DEFAULT '[]'::jsonb"
            ),
            (
                "ALTER TABLE mlapp.pipeline_runs ADD COLUMN IF NOT EXISTS "
                "error_message TEXT NOT NULL DEFAULT ''"
            ),
            (
                "ALTER TABLE mlapp.pipeline_runs ADD COLUMN IF NOT EXISTS "
                "requested_step_id VARCHAR(128) NOT NULL DEFAULT ''"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_owner_created_at "
                "ON mlapp.pipeline_runs (owner_id, created_at DESC)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_owner_pipeline_created_at "
                "ON mlapp.pipeline_runs (owner_id, pipeline_id, created_at DESC)"
            ),
        ]
        for statement in statements:
            connection.execute(text(statement))


def _online_model_serving(connection: Connection) -> None:
    """Create durable deployment revisions, credentials and inference history."""
    statements = [
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_deployments ("
            "id VARCHAR(64) PRIMARY KEY, owner_id VARCHAR(64) NOT NULL, "
            "business_case_id VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, "
            "slug VARCHAR(255) NOT NULL UNIQUE, status VARCHAR(32) NOT NULL, "
            "active_revision_id VARCHAR(64) NOT NULL DEFAULT '', endpoint_url TEXT, "
            "retention_days INTEGER NOT NULL DEFAULT 365, created_by VARCHAR(64) NOT NULL, "
            "updated_by VARCHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
            "updated_at TIMESTAMPTZ NOT NULL)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_deployments_bc ON mlapp.serving_deployments (business_case_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_serving_deployment_bc_name ON mlapp.serving_deployments (business_case_id, lower(name))",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_deployment_revisions ("
            "id VARCHAR(64) PRIMARY KEY, deployment_id VARCHAR(64) NOT NULL, "
            "version_number INTEGER NOT NULL, assignments JSONB NOT NULL, "
            "created_by VARCHAR(64) NOT NULL, reason TEXT NOT NULL DEFAULT '', "
            "created_at TIMESTAMPTZ NOT NULL, UNIQUE(deployment_id, version_number))"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_revisions_deployment ON mlapp.serving_deployment_revisions (deployment_id, version_number DESC)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_inference_requests ("
            "id VARCHAR(64) PRIMARY KEY, deployment_id VARCHAR(64) NOT NULL, "
            "deployment_revision_id VARCHAR(64) NOT NULL, requested_by VARCHAR(64) NOT NULL, "
            "correlation_id VARCHAR(128) NOT NULL, idempotency_key VARCHAR(255) NOT NULL DEFAULT '', "
            "status VARCHAR(32) NOT NULL, record_count INTEGER NOT NULL, "
            "request_payload JSONB NOT NULL, response_payload JSONB NOT NULL DEFAULT '{}'::jsonb, "
            "warnings JSONB NOT NULL DEFAULT '[]'::jsonb, error_code VARCHAR(128) NOT NULL DEFAULT '', "
            "error_message TEXT NOT NULL DEFAULT '', champion_model_id VARCHAR(64) NOT NULL DEFAULT '', "
            "served_model_id VARCHAR(64) NOT NULL DEFAULT '', served_role VARCHAR(32) NOT NULL DEFAULT '', "
            "fallback_used BOOLEAN NOT NULL DEFAULT FALSE, latency_ms INTEGER, "
            "created_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_inference_deployment_created ON mlapp.serving_inference_requests (deployment_id, created_at DESC, id DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_serving_inference_idempotency ON mlapp.serving_inference_requests (deployment_id, requested_by, idempotency_key) WHERE idempotency_key <> ''",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_inference_items ("
            "id VARCHAR(128) PRIMARY KEY, request_id VARCHAR(64) NOT NULL, "
            "deployment_id VARCHAR(64) NOT NULL, record_id VARCHAR(512) NOT NULL, "
            "model_id VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL, "
            "input JSONB NOT NULL, output JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_items_request ON mlapp.serving_inference_items (request_id)",
        "CREATE INDEX IF NOT EXISTS ix_serving_items_record ON mlapp.serving_inference_items (deployment_id, record_id, created_at DESC)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.api_credentials ("
            "id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, "
            "token_hash VARCHAR(64) NOT NULL UNIQUE, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ, "
            "last_used_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_api_credentials_user ON mlapp.api_credentials (user_id, created_at DESC)",
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_challenger_replay_jobs ("
            "id VARCHAR(64) PRIMARY KEY, deployment_id VARCHAR(64) NOT NULL, "
            "deployment_revision_id VARCHAR(64) NOT NULL, challenger_model_id VARCHAR(64) NOT NULL, "
            "requested_by VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL, "
            "source_before TIMESTAMPTZ NOT NULL, source_since TIMESTAMPTZ, source_until TIMESTAMPTZ, "
            "max_requests INTEGER NOT NULL, processed_requests INTEGER NOT NULL DEFAULT 0, "
            "processed_records INTEGER NOT NULL DEFAULT 0, failed_requests INTEGER NOT NULL DEFAULT 0, "
            "error_message TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL, "
            "started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_replays_deployment ON mlapp.serving_challenger_replay_jobs (deployment_id, created_at DESC)",
    ]
    for statement in statements:
        connection.execute(text(statement))


def _index_model_family_metadata(connection: Connection) -> None:
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_artifacts_model_logical_id "
        "ON mlapp.artifacts ((metadata->>'logical_model_id'), created_at) "
        "WHERE type = 'model_version'"
    ))


def _rename_candidate_model_stage(connection: Connection) -> None:
    """Canonicalize the model lifecycle stage without changing AutoML terminology."""
    connection.execute(text(
        "UPDATE mlapp.artifacts "
        "SET metadata = jsonb_set(metadata::jsonb, '{stage}', to_jsonb('developed'::text), true)::json "
        "WHERE type = 'model_version' AND metadata->>'stage' = 'candidate'"
    ))


def _enforce_active_model_lifecycle(connection: Connection) -> None:
    """Materialize active model roles and enforce stage compatibility in PostgreSQL."""
    statements = [
        (
            "CREATE TABLE IF NOT EXISTS mlapp.serving_active_model_assignments ("
            "deployment_id VARCHAR(64) NOT NULL, revision_id VARCHAR(64) NOT NULL, "
            "model_id VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL, "
            "PRIMARY KEY (deployment_id, model_id))"
        ),
        "CREATE INDEX IF NOT EXISTS ix_serving_active_model ON mlapp.serving_active_model_assignments (model_id)",
        "TRUNCATE TABLE mlapp.serving_active_model_assignments",
        (
            "INSERT INTO mlapp.serving_active_model_assignments (deployment_id, revision_id, model_id, role) "
            "SELECT d.id, r.id, assignment->>'model_id', assignment->>'role' "
            "FROM mlapp.serving_deployments d "
            "JOIN mlapp.serving_deployment_revisions r ON r.id = d.active_revision_id "
            "CROSS JOIN LATERAL jsonb_array_elements(r.assignments::jsonb) assignment "
            "WHERE d.status <> 'stopped'"
        ),
        (
            "UPDATE mlapp.serving_deployments d SET status = 'degraded' "
            "WHERE d.status <> 'stopped' AND EXISTS ("
            "SELECT 1 FROM mlapp.serving_active_model_assignments a "
            "JOIN mlapp.artifacts m ON m.id = a.model_id AND m.type = 'model_version' "
            "WHERE a.deployment_id = d.id AND ("
            "(a.role IN ('champion', 'fallback') AND coalesce(m.metadata->>'stage', 'developed') <> 'production') OR "
            "(a.role IN ('challenger', 'shadow') AND coalesce(m.metadata->>'stage', 'developed') NOT IN ('staging', 'production'))))"
        ),
        (
            "CREATE OR REPLACE FUNCTION mlapp.validate_active_model_assignment() RETURNS trigger AS $$ "
            "DECLARE current_stage TEXT; BEGIN "
            "PERFORM pg_advisory_xact_lock(hashtextextended(NEW.model_id, 0)); "
            "SELECT coalesce(metadata->>'stage', 'developed') INTO current_stage "
            "FROM mlapp.artifacts WHERE id = NEW.model_id AND type = 'model_version'; "
            "IF current_stage IS NULL THEN RETURN NEW; END IF; "
            "IF (NEW.role IN ('champion', 'fallback') AND current_stage <> 'production') "
            "OR (NEW.role IN ('challenger', 'shadow') AND current_stage NOT IN ('staging', 'production')) THEN "
            "RAISE EXCEPTION 'Model stage % cannot be assigned as %', current_stage, NEW.role USING ERRCODE = '23514'; "
            "END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
        ),
        "DROP TRIGGER IF EXISTS trg_validate_active_model_assignment ON mlapp.serving_active_model_assignments",
        (
            "CREATE TRIGGER trg_validate_active_model_assignment BEFORE INSERT OR UPDATE "
            "ON mlapp.serving_active_model_assignments FOR EACH ROW "
            "EXECUTE FUNCTION mlapp.validate_active_model_assignment()"
        ),
        (
            "CREATE OR REPLACE FUNCTION mlapp.prevent_invalid_model_stage_change() RETURNS trigger AS $$ "
            "DECLARE next_stage TEXT; BEGIN "
            "IF NEW.type <> 'model_version' THEN RETURN NEW; END IF; "
            "next_stage := coalesce(NEW.metadata->>'stage', 'developed'); "
            "IF next_stage = 'candidate' THEN next_stage := 'developed'; END IF; "
            "PERFORM pg_advisory_xact_lock(hashtextextended(NEW.id, 0)); "
            "IF EXISTS (SELECT 1 FROM mlapp.serving_active_model_assignments a WHERE a.model_id = NEW.id AND ("
            "(a.role IN ('champion', 'fallback') AND next_stage <> 'production') OR "
            "(a.role IN ('challenger', 'shadow') AND next_stage NOT IN ('staging', 'production')))) THEN "
            "RAISE EXCEPTION 'Model stage % is incompatible with an active serving assignment', next_stage USING ERRCODE = '23514'; "
            "END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
        ),
        "DROP TRIGGER IF EXISTS trg_prevent_invalid_model_stage_change ON mlapp.artifacts",
        (
            "CREATE TRIGGER trg_prevent_invalid_model_stage_change BEFORE UPDATE OF metadata "
            "ON mlapp.artifacts FOR EACH ROW EXECUTE FUNCTION mlapp.prevent_invalid_model_stage_change()"
        ),
    ]
    for statement in statements:
        connection.execute(text(statement))


def _harden_inference_audit_contract(connection: Connection) -> None:
    statements = [
        "ALTER TABLE mlapp.serving_inference_requests ADD COLUMN IF NOT EXISTS request_hash VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE mlapp.serving_inference_items ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'succeeded'",
        "ALTER TABLE mlapp.serving_inference_items ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE mlapp.serving_inference_items ADD COLUMN IF NOT EXISTS latency_ms INTEGER",
    ]
    for statement in statements:
        connection.execute(text(statement))


MIGRATIONS = [
    Migration(
        version="20260703_0001",
        description="Move legacy dataset and pipeline runtime DDL into migrations",
        apply=_legacy_schema_hardening,
    ),
    Migration(
        version="20260717_0002",
        description="Add single-company identity, groups, grants, audit and root bootstrap",
        apply=_identity_and_access_control,
    ),
    Migration(
        version="20260717_0003",
        description="Materialize every group owner as an immutable owner membership",
        apply=_materialize_group_owners,
    ),
    Migration(
        version="20260717_0004",
        description="Enforce globally unique case-insensitive Business Case names",
        apply=_enforce_unique_business_case_names,
    ),
    Migration(
        version="20260719_0005",
        description="Add versioned online model serving, inference history and API credentials",
        apply=_online_model_serving,
    ),
    Migration(
        version="20260719_0006",
        description="Index model family metadata for bounded version history reads",
        apply=_index_model_family_metadata,
    ),
    Migration(
        version="20260720_0007",
        description="Rename the candidate model lifecycle stage to developed",
        apply=_rename_candidate_model_stage,
    ),
    Migration(
        version="20260720_0008",
        description="Enforce model lifecycle compatibility for active serving assignments",
        apply=_enforce_active_model_lifecycle,
    ),
    Migration(
        version="20260720_0009",
        description="Bind idempotency to request content and retain every model execution outcome",
        apply=_harden_inference_audit_contract,
    ),
]
