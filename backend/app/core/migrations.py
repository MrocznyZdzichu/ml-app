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
    return applied_now


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
]
