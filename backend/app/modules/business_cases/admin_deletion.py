"""Root-only, irreversible Business Case cleanup.

This module is deliberately separate from the normal Business Case repository.
It is an administrative maintenance operation, not part of the product
lifecycle.  The database does not use foreign keys for these cross-module
relations, therefore their deletion order is explicit and transactional.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class BusinessCaseCascadeDeletion:
    business_case_id: str
    deleted: dict[str, int]
    storage_paths: tuple[Path, ...]


class PostgresBusinessCaseAdminDeletion:
    """Deletes state owned by one Business Case in one database transaction."""

    def __init__(self, engine: Engine, repository_root: Path | None = None) -> None:
        self.engine = engine
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def delete(self, business_case_id: str) -> BusinessCaseCascadeDeletion:
        params = {"business_case_id": business_case_id}
        deleted: dict[str, int] = {}
        storage_paths: list[Path] = []

        with self.engine.begin() as connection:
            business_case = connection.execute(text(
                "SELECT id FROM mlapp.business_cases WHERE id = :business_case_id FOR UPDATE"
            ), params).first()
            if business_case is None:
                return BusinessCaseCascadeDeletion(business_case_id, {}, ())

            run_rows = connection.execute(text(
                "SELECT owner_id, id FROM mlapp.pipeline_runs "
                "WHERE business_case_id = :business_case_id"
            ), params).mappings().all()
            asset_rows = connection.execute(text(
                "SELECT DISTINCT d.owner_id, d.id, d.location_uri "
                "FROM mlapp.data_assets d "
                "JOIN mlapp.artifacts a ON a.reference_id = d.id "
                "WHERE a.business_case_id = :business_case_id "
                "AND NOT EXISTS (SELECT 1 FROM mlapp.business_case_data_attachments other "
                "    WHERE other.data_asset_id = d.id "
                "      AND other.business_case_id <> :business_case_id)"
            ), params).mappings().all()
            deployment_ids = (
                "SELECT id FROM mlapp.serving_deployments "
                "WHERE business_case_id = :business_case_id"
            )
            run_ids = (
                "SELECT id FROM mlapp.pipeline_runs "
                "WHERE business_case_id = :business_case_id"
            )
            pipeline_ids = (
                "SELECT id FROM mlapp.pipelines "
                "WHERE business_case_id = :business_case_id"
            )
            artifact_ids = (
                "SELECT id FROM mlapp.artifacts "
                "WHERE business_case_id = :business_case_id"
            )
            asset_ids = (
                "SELECT DISTINCT d.id FROM mlapp.data_assets d "
                "JOIN mlapp.artifacts a ON a.reference_id = d.id "
                "WHERE a.business_case_id = :business_case_id "
                "AND NOT EXISTS (SELECT 1 FROM mlapp.business_case_data_attachments other "
                "    WHERE other.data_asset_id = d.id "
                "      AND other.business_case_id <> :business_case_id)"
            )

            statements = [
                ("serving_active_assignments", "DELETE FROM mlapp.serving_active_model_assignments "
                 f"WHERE deployment_id IN ({deployment_ids})"),
                ("serving_inference_items", "DELETE FROM mlapp.serving_inference_items "
                 f"WHERE deployment_id IN ({deployment_ids})"),
                ("serving_replay_jobs", "DELETE FROM mlapp.serving_challenger_replay_jobs "
                 f"WHERE deployment_id IN ({deployment_ids})"),
                ("serving_inference_requests", "DELETE FROM mlapp.serving_inference_requests "
                 f"WHERE deployment_id IN ({deployment_ids})"),
                ("serving_monitoring_runs", "DELETE FROM mlapp.serving_monitoring_runs "
                 "WHERE business_case_id = :business_case_id"),
                ("serving_deployment_revisions", "DELETE FROM mlapp.serving_deployment_revisions "
                 f"WHERE deployment_id IN ({deployment_ids})"),
                ("serving_deployments", "DELETE FROM mlapp.serving_deployments "
                 "WHERE business_case_id = :business_case_id"),
                ("pipeline_step_runs", "DELETE FROM mlapp.pipeline_step_runs "
                 f"WHERE pipeline_run_id IN ({run_ids})"),
                ("pipeline_runs", "DELETE FROM mlapp.pipeline_runs "
                 "WHERE business_case_id = :business_case_id"),
                ("pipeline_versions", "DELETE FROM mlapp.pipeline_versions "
                 "WHERE business_case_id = :business_case_id"),
                ("pipelines", "DELETE FROM mlapp.pipelines "
                 "WHERE business_case_id = :business_case_id"),
                ("resource_grants", "DELETE FROM mlapp.resource_grants WHERE "
                 "(resource_kind = 'business_case' AND resource_id = :business_case_id) "
                 f"OR resource_id IN ({artifact_ids}) OR resource_id IN ({pipeline_ids}) OR resource_id IN ({asset_ids})"),
                ("business_case_grants", "DELETE FROM mlapp.business_case_grants "
                 "WHERE business_case_id = :business_case_id"),
                ("business_case_access_requests", "DELETE FROM mlapp.business_case_access_requests "
                 "WHERE business_case_id = :business_case_id"),
                ("data_attachments", "DELETE FROM mlapp.business_case_data_attachments "
                 "WHERE business_case_id = :business_case_id"),
                ("exclusive_data_assets", "DELETE FROM mlapp.data_assets "
                 f"WHERE id IN ({asset_ids})"),
                ("artifacts", "DELETE FROM mlapp.artifacts "
                 "WHERE business_case_id = :business_case_id"),
                ("business_cases", "DELETE FROM mlapp.business_cases "
                 "WHERE id = :business_case_id"),
            ]
            for label, statement in statements:
                deleted[label] = int(connection.execute(text(statement), params).rowcount or 0)

            for row in run_rows:
                storage_paths.append(self.repository_root / "users" / str(row["owner_id"]) / "pipeline-runs" / str(row["id"]))
            for row in asset_rows:
                storage_paths.append(self.repository_root / "users" / str(row["owner_id"]) / str(row["id"]))

        return BusinessCaseCascadeDeletion(
            business_case_id=business_case_id,
            deleted=deleted,
            storage_paths=tuple(storage_paths),
        )

    def delete_storage(self, deletion: BusinessCaseCascadeDeletion) -> None:
        """Remove only paths constructed from trusted database identifiers."""
        for path in deletion.storage_paths:
            target = path.resolve()
            try:
                target.relative_to(self.repository_root)
            except ValueError:
                continue
            if target.exists():
                shutil.rmtree(target)
