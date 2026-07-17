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
]
