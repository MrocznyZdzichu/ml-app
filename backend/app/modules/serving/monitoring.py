from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.business_cases.domain import (
    Artifact,
    ArtifactOrigin,
    ArtifactType,
    BusinessCaseDataAttachment,
    DataArtifactKind,
    DataRole,
)
from app.modules.business_cases.repository import PostgresBusinessCaseRepository
from app.modules.business_cases.lineage import DatasetLineageResolver
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.service import DatasetService
from app.modules.models.service import ModelService
from app.modules.pipelines.model_evaluation import ModelEvaluationSnapshotBuilder
from app.modules.pipelines.runtime import json_safe, sql_literal
from app.modules.serving.domain import MonitoringRunStatus, OnlineMonitoringRun
from app.modules.serving.repository import PostgresServingRepository, ServingRepository
from app.modules.serving.schemas import OnlineMonitoringRunCreate
from app.modules.sharing.domain import AuditEvent, BC_ROLE_RANK, BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy
from app.modules.sharing.repository import PostgresSharingRepository
from app.shared.duckdb_runtime import configured_duckdb_connection, write_parquet_atomic
from app.shared.sql_security import identifier


logger = logging.getLogger("mlapp.serving.monitoring")


class OnlineMonitoringService:
    """Runs full-scope, immutable monitoring over a pinned online inference window."""

    snapshot_columns = {
        "prediction_id": "VARCHAR",
        "request_id": "VARCHAR",
        "record_id": "VARCHAR",
        "scored_at": "TIMESTAMPTZ",
        "completed_at": "TIMESTAMPTZ",
        "deployment_revision_id": "VARCHAR",
        "model_id": "VARCHAR",
        "role": "VARCHAR",
        "served": "BOOLEAN",
        "request_status": "VARCHAR",
        "execution_status": "VARCHAR",
        "fallback_used": "BOOLEAN",
        "request_latency_ms": "INTEGER",
        "execution_latency_ms": "INTEGER",
        "prediction_value": "VARCHAR",
        "prediction_score": "DOUBLE",
        "input_json": "VARCHAR",
        "error_message": "VARCHAR",
    }

    def __init__(
        self,
        repository: ServingRepository | None = None,
        datasets: DatasetService | None = None,
        models: ModelService | None = None,
        enqueue: Callable[[str], Any] | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.repository = repository or PostgresServingRepository()
        self.datasets = datasets or DatasetService()
        self.dataset_repository = getattr(self.datasets, "repository", None) or PostgresDatasetRepository()
        self.models = models or ModelService()
        self.business_cases = PostgresBusinessCaseRepository()
        self.sharing = PostgresSharingRepository()
        self.store = ColumnarDatasetStore(repository_root or Path("data/repository"))
        self.repository_root = (repository_root or Path("data/repository")).resolve()
        self.enqueue = enqueue

    def create_run(
        self,
        deployment_id: str,
        payload: OnlineMonitoringRunCreate,
        principal: Principal,
    ) -> OnlineMonitoringRun:
        deployment = self._deployment(deployment_id, principal, BusinessCaseAccessRole.CONTRIBUTOR)
        now = datetime.now(timezone.utc)
        since = payload.since.astimezone(timezone.utc)
        until = payload.until.astimezone(timezone.utc)
        if until > now:
            raise HTTPException(status_code=422, detail="Monitoring until cannot be in the future")
        retention_cutoff = now - timedelta(days=deployment.retention_days)
        if since < retention_cutoff:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Monitoring window starts before the deployment's {deployment.retention_days}-day "
                    "Inference Log retention boundary; select a complete retained window"
                ),
            )

        champion = self._active_champion(deployment, principal)
        problem_type = payload.problem_type or champion.problem_type
        if problem_type not in {
            "binary_classification", "multiclass_classification", "regression"
        }:
            raise HTTPException(
                status_code=422,
                detail=f"Online effectiveness monitoring does not support problem type {problem_type!r}",
            )
        business_case = self.business_cases.get_business_case(deployment.business_case_id)
        if business_case is None:
            raise HTTPException(status_code=409, detail="Deployment Business Case no longer exists")
        actuals_dataset_id = payload.actuals_dataset_id.strip()
        actuals_artifact_id = ""
        actuals_record_id_column = ""
        target_column = payload.target_column.strip() or champion.target_column
        actuals_target_column = ""
        if actuals_dataset_id:
            actuals = self.datasets.get_asset(actuals_dataset_id, principal)
            attachment = self._actuals_attachment(deployment.business_case_id, actuals.id)
            actuals_target_column = (
                payload.actuals_target_column.strip()
                or attachment.target_column.strip()
                or target_column
            )
            if not actuals_target_column:
                raise HTTPException(
                    status_code=422,
                    detail="Actuals target column could not be inferred; configure it on the Business Case attachment or request",
                )
            actuals_artifact_id = self._ensure_actuals_artifact(
                actuals, deployment.business_case_id, business_case.owner_id, principal.user_id
            ).id
            actuals_record_id_column = (
                payload.join.actuals_record_id_column.strip()
                or attachment.primary_key_column.strip()
                or "record_id"
            )

        run = OnlineMonitoringRun(
            id=str(uuid4()),
            deployment_id=deployment.id,
            business_case_id=deployment.business_case_id,
            owner_id=business_case.owner_id,
            requested_by=principal.user_id,
            status=MonitoringRunStatus.QUEUED,
            since=since,
            until=until,
            source_before=now,
            actuals_dataset_id=actuals_dataset_id,
            aggregation_granularity=payload.aggregation_granularity,
            actuals_artifact_id=actuals_artifact_id,
            join_strategy=payload.join.strategy,
            actuals_prediction_id_column=payload.join.actuals_prediction_id_column,
            actuals_request_id_column=payload.join.actuals_request_id_column,
            actuals_record_id_column=actuals_record_id_column,
            actuals_target_column=actuals_target_column,
            problem_type=problem_type,
            target_column=target_column or actuals_target_column,
        )
        self.repository.add_monitoring_run(run)
        self.sharing.add_audit(AuditEvent(
            id=str(uuid4()),
            actor_id=principal.user_id,
            action="serving.monitoring_run_queued",
            subject_type="deployment",
            subject_id=deployment.id,
            resource_kind="business_case",
            resource_id=deployment.business_case_id,
            new_state={
                "monitoring_run_id": run.id,
                "since": run.since.isoformat(),
                "until": run.until.isoformat(),
                "actuals_dataset_id": run.actuals_dataset_id,
            },
        ))
        if self.enqueue is not None:
            self.enqueue(run.id)
        else:
            from app.worker.tasks import run_online_monitoring
            run_online_monitoring.delay(run.id)
        return run

    def list_runs(
        self,
        principal: Principal,
        *,
        deployment_id: str | None = None,
        limit: int = 200,
        include_archived: bool = False,
    ) -> list[OnlineMonitoringRun]:
        if deployment_id:
            deployment = self._deployment(
                deployment_id, principal, BusinessCaseAccessRole.REPORT_VIEWER
            )
            return self.repository.list_monitoring_runs(
                deployment.id, limit, include_archived=include_archived
            )
        return [
            run for run in self.repository.list_monitoring_runs(
                None, limit, include_archived=include_archived
            )
            if self._can_view_report(principal, run.business_case_id)
        ]

    def get_run(self, run_id: str, principal: Principal) -> OnlineMonitoringRun:
        run = self.repository.get_monitoring_run(run_id)
        if run is None or not self._can_view_report(principal, run.business_case_id):
            raise HTTPException(status_code=404, detail="Online monitoring run not found")
        return run

    def archive_run(
        self, run_id: str, reason: str, principal: Principal
    ) -> OnlineMonitoringRun:
        run = self.repository.get_monitoring_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Online monitoring run not found")
        self._deployment(run.deployment_id, principal, BusinessCaseAccessRole.CONTRIBUTOR)
        if run.status not in {MonitoringRunStatus.SUCCEEDED, MonitoringRunStatus.FAILED}:
            raise HTTPException(status_code=409, detail="Only finished monitoring runs can be archived")
        if run.archived_at is not None:
            return run
        run.archived_at = datetime.now(timezone.utc)
        run.archived_by = principal.user_id
        run.archive_reason = reason
        self.repository.update_monitoring_run(run)
        self._audit_archive(principal, run, reason, bulk=False)
        return run

    def archive_history(
        self, deployment_id: str, reason: str, principal: Principal
    ) -> int:
        deployment = self._deployment(
            deployment_id, principal, BusinessCaseAccessRole.CONTRIBUTOR
        )
        archived_at = datetime.now(timezone.utc)
        count = self.repository.archive_monitoring_runs(
            deployment.id, principal.user_id, archived_at, reason
        )
        self.sharing.add_audit(AuditEvent(
            id=str(uuid4()),
            actor_id=principal.user_id,
            action="serving.monitoring_history_archived",
            subject_type="deployment",
            subject_id=deployment.id,
            resource_kind="business_case",
            resource_id=deployment.business_case_id,
            new_state={"archived_run_count": count, "reason": reason},
        ))
        return count

    def _audit_archive(
        self,
        principal: Principal,
        run: OnlineMonitoringRun,
        reason: str,
        *,
        bulk: bool,
    ) -> None:
        self.sharing.add_audit(AuditEvent(
            id=str(uuid4()),
            actor_id=principal.user_id,
            action="serving.monitoring_history_archived" if bulk else "serving.monitoring_run_archived",
            subject_type="online_monitoring_run",
            subject_id=run.id,
            resource_kind="business_case",
            resource_id=run.business_case_id,
            new_state={"archived_at": run.archived_at.isoformat() if run.archived_at else None, "reason": reason},
        ))

    def execute_run(self, run_id: str) -> OnlineMonitoringRun:
        run = self.repository.get_monitoring_run(run_id)
        if run is None:
            raise ValueError("Online monitoring run not found")
        if run.status == MonitoringRunStatus.SUCCEEDED:
            return run
        principal = self._requester(run)
        if principal is None:
            return self._fail(run, "Monitoring requester is no longer active")
        try:
            deployment = self._deployment(
                run.deployment_id, principal, BusinessCaseAccessRole.CONTRIBUTOR
            )
            actuals = None
            if run.actuals_dataset_id:
                actuals = self.datasets.get_asset(run.actuals_dataset_id, principal)
                self._actuals_attachment(run.business_case_id, actuals.id)
        except Exception as exc:
            return self._fail(run, f"Monitoring authorization or input validation failed before execution: {exc}")

        run.status = MonitoringRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.error_message = ""
        self.repository.update_monitoring_run(run)
        try:
            result = self._calculate(run, deployment, actuals, principal)
            run.status = MonitoringRunStatus.SUCCEEDED
            run.completed_at = datetime.now(timezone.utc)
            run.report = result["report"]
            run.report_artifact_id = result["report_artifact_id"]
            run.snapshot_dataset_id = result["snapshot_dataset_id"]
            run.joined_dataset_id = result["joined_dataset_id"]
            run.processed_request_count = result["processed_request_count"]
            run.processed_row_count = result["processed_row_count"]
            run.matched_row_count = result["matched_row_count"]
            run.missing_actuals_count = result["missing_actuals_count"]
            run.unmatched_actuals_count = result["unmatched_actuals_count"]
            run.join_strategy = result["join_strategy"]
            run.warnings = result["warnings"]
            self.repository.update_monitoring_run(run)
            return run
        except Exception as exc:
            logger.exception("Online monitoring failed run_id=%s", run.id)
            return self._fail(run, str(exc))

    def _calculate(
        self,
        run: OnlineMonitoringRun,
        deployment: Any,
        actuals: DataAsset | None,
        principal: Principal,
    ) -> dict[str, Any]:
        directory = self._run_directory(run)
        directory.mkdir(parents=True, exist_ok=True)
        snapshot_dataset_id = str(uuid5(NAMESPACE_URL, f"mlapp:online-monitoring:{run.id}:predictions"))
        joined_dataset_id = str(uuid5(NAMESPACE_URL, f"mlapp:online-monitoring:{run.id}:joined"))
        snapshot_csv = directory / "prediction-snapshot.csv"
        snapshot_path = directory / "prediction-snapshot.parquet"
        joined_path = directory / "predictions-with-actuals.parquet"

        health = self.repository.monitoring_request_stats(
            run.deployment_id, run.since, run.until, run.source_before
        )
        processed_request_count = int(health.get("request_count") or 0)
        run.processed_request_count = processed_request_count
        self.repository.update_monitoring_run(run)
        item_count = self._write_snapshot_csv(run, snapshot_csv)

        connection = configured_duckdb_connection(directory / ".duckdb-tmp")
        joined_stats = None
        strategy = "not_applicable"
        matched_count = 0
        missing_actuals_count = 0
        unmatched_actuals_count = 0
        try:
            snapshot_csv_relation = self._csv_relation(snapshot_csv)
            snapshot_stats = write_parquet_atomic(connection, snapshot_csv_relation, snapshot_path)
            snapshot_relation = f"read_parquet({sql_literal(str(snapshot_path))})"
            model_ids = [
                str(row[0]) for row in connection.execute(
                    f"SELECT DISTINCT model_id FROM {snapshot_relation} ORDER BY model_id"
                ).fetchall()
            ]
            models = {
                model_id: self.models.get_model_for_inference(model_id, principal)
                for model_id in model_ids
            }
            representative = self._representative_model(deployment, models, principal)
            served_count = int(connection.execute(
                f"SELECT count(*) FILTER (WHERE served) FROM {snapshot_relation}"
            ).fetchone()[0])
            if actuals is not None:
                actuals_path = self.store.ensure_parquet(
                    actuals,
                    lambda dataset_id: self.datasets.get_asset(dataset_id, principal),
                )
                actuals_relation = f"read_parquet({sql_literal(str(actuals_path))})"
                actual_columns = {
                    str(row[0]) for row in connection.execute(
                        f"DESCRIBE SELECT * FROM {actuals_relation}"
                    ).fetchall()
                }
                if run.actuals_target_column not in actual_columns:
                    raise ValueError(
                        f"Actuals dataset is missing target column '{run.actuals_target_column}'"
                    )
                strategy = self._resolve_join_strategy(run, actual_columns)
                labels_sql, unmatched_actuals_count = self._labels_sql(
                    connection, run, strategy, snapshot_relation, actuals_relation
                )
                joined_sql = (
                    "WITH monitoring_labels AS (" + labels_sql + ") "
                    "SELECT predictions.*, labels.monitoring_actual "
                    f"FROM {snapshot_relation} predictions LEFT JOIN monitoring_labels labels "
                    "ON labels.request_id = predictions.request_id "
                    "AND labels.record_id = predictions.record_id"
                )
                joined_stats = write_parquet_atomic(connection, joined_sql, joined_path)
                joined_relation = f"read_parquet({sql_literal(str(joined_path))})"
                served_count, matched_count = connection.execute(
                    f"SELECT count(*) FILTER (WHERE served), "
                    f"count(*) FILTER (WHERE served AND monitoring_actual IS NOT NULL) "
                    f"FROM {joined_relation}"
                ).fetchone()
                missing_actuals_count = int(served_count) - int(matched_count)
                evaluation = self._performance_report(
                    connection, joined_relation, run, representative, models
                )
            else:
                evaluation = {
                    "available": False,
                    "reason": "actuals_not_provided",
                    "message": "Performance metrics were not evaluated because actuals were not provided",
                    "problem_type": run.problem_type,
                    "target_column": run.target_column,
                    "service": None,
                    "models": [],
                    "warnings": [],
                }
            input_monitoring = self._input_monitoring(
                connection, snapshot_relation, representative
            )
            prediction_monitoring = self._prediction_monitoring(
                connection, snapshot_relation, run.problem_type
            )
            time_aggregation = self._time_aggregation(
                connection, snapshot_relation, run
            )
        finally:
            connection.close()
            snapshot_csv.unlink(missing_ok=True)

        snapshot_artifact = self._register_dataset(
            run=run,
            dataset_id=snapshot_dataset_id,
            name=f"{deployment.name} online predictions {run.since.date()} to {run.until.date()}",
            path=snapshot_path,
            row_count=snapshot_stats.row_count,
            role=DataRole.SCORING_OUTPUT,
            artifact_type=ArtifactType.PREDICTION_DATASET,
            metadata={
                "origin": "platform_generated",
                "online_monitoring": {
                    "run_id": run.id,
                    "deployment_id": run.deployment_id,
                    "since": run.since.isoformat(),
                    "until": run.until.isoformat(),
                    "source_before": run.source_before.isoformat(),
                    "time_basis": run.time_basis,
                },
                "score_contract": self._score_contract(representative),
                "data_scope": "full",
            },
        )
        joined_artifact = None
        if actuals is not None and joined_stats is not None:
            joined_artifact = self._register_dataset(
                run=run,
                dataset_id=joined_dataset_id,
                name=f"{deployment.name} predictions with actuals {run.since.date()} to {run.until.date()}",
                path=joined_path,
                row_count=joined_stats.row_count,
                role=DataRole.MONITORING_INPUT,
                artifact_type=ArtifactType.DATASET,
                metadata={
                    "origin": "platform_generated",
                    "online_monitoring": {
                        "run_id": run.id,
                        "prediction_dataset_id": snapshot_dataset_id,
                        "actuals_dataset_id": run.actuals_dataset_id,
                        "join_strategy": strategy,
                    },
                    "data_scope": "full",
                },
            )

        warnings = list(dict.fromkeys([
            *evaluation.get("warnings", []),
            *input_monitoring.get("warnings", []),
            *prediction_monitoring.get("warnings", []),
        ]))
        if actuals is None:
            warnings.insert(0, "Actuals were not provided; performance and effectiveness metrics were not evaluated")
        report = {
            "contract_version": "1.1",
            "report_type": "online_service_monitoring_report",
            "evaluation_scope": "performance" if actuals is not None else "operational",
            "name": f"{deployment.name} online monitoring",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deployment": {
                "id": deployment.id,
                "name": deployment.name,
                "business_case_id": deployment.business_case_id,
            },
            "data_scope": {
                "mode": "full",
                "time_basis": run.time_basis,
                "since": run.since.isoformat(),
                "until": run.until.isoformat(),
                "source_before": run.source_before.isoformat(),
                "processed_request_count": processed_request_count,
                "processed_execution_count": item_count,
                "served_prediction_count": int(served_count),
                "matched_actual_count": int(matched_count),
                "missing_actual_count": missing_actuals_count,
                "unmatched_actual_count": unmatched_actuals_count,
                "actuals_coverage": (
                    int(matched_count) / int(served_count)
                    if actuals is not None and served_count else None
                ),
            },
            "actuals": {
                "status": "provided" if actuals is not None else "not_provided",
                "dataset_id": run.actuals_dataset_id,
                "artifact_id": run.actuals_artifact_id,
                "target_column": run.actuals_target_column,
                "join_strategy": strategy,
                "record_id_column": run.actuals_record_id_column,
            },
            "service_health": health,
            "input_monitoring": input_monitoring,
            "prediction_monitoring": prediction_monitoring,
            "time_aggregation": time_aggregation,
            "performance": evaluation,
            "artifacts": {
                "prediction_dataset_id": snapshot_dataset_id,
                "prediction_artifact_id": snapshot_artifact.id,
                "joined_dataset_id": joined_dataset_id if joined_artifact else "",
                "joined_artifact_id": joined_artifact.id if joined_artifact else "",
            },
            "warnings": warnings,
        }
        report_artifact = self._register_report(
            run, report, snapshot_artifact, joined_artifact
        )
        report["artifacts"]["report_artifact_id"] = report_artifact.id
        report_artifact.metadata["report"] = report
        self.business_cases.update_artifact(report_artifact)
        return {
            "report": report,
            "report_artifact_id": report_artifact.id,
            "snapshot_dataset_id": snapshot_dataset_id,
            "joined_dataset_id": joined_dataset_id if joined_artifact else "",
            "processed_request_count": processed_request_count,
            "processed_row_count": item_count,
            "matched_row_count": int(matched_count),
            "missing_actuals_count": missing_actuals_count,
            "unmatched_actuals_count": unmatched_actuals_count,
            "join_strategy": strategy,
            "warnings": warnings,
        }

    def _write_snapshot_csv(
        self, run: OnlineMonitoringRun, destination: Path
    ) -> int:
        count = 0
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.snapshot_columns))
            writer.writeheader()
            for item in self.repository.iter_monitoring_items(
                run.deployment_id, run.since, run.until, run.source_before
            ):
                output = dict(item.get("output") or {})
                prediction = output.get("prediction")
                score = output.get("prediction_score")
                writer.writerow({
                    "prediction_id": item["prediction_id"],
                    "request_id": item["request_id"],
                    "record_id": item["record_id"],
                    "scored_at": item["scored_at"].isoformat(),
                    "completed_at": item["completed_at"].isoformat() if item.get("completed_at") else "",
                    "deployment_revision_id": item["deployment_revision_id"],
                    "model_id": item["model_id"],
                    "role": item["role"],
                    "served": bool(item.get("served")),
                    "request_status": item["request_status"],
                    "execution_status": item["status"],
                    "fallback_used": bool(item.get("fallback_used")),
                    "request_latency_ms": item.get("request_latency_ms"),
                    "execution_latency_ms": item.get("execution_latency_ms"),
                    "prediction_value": "" if prediction is None else str(json_safe(prediction)),
                    "prediction_score": score if isinstance(score, (int, float)) else "",
                    "input_json": json.dumps(json_safe(item.get("input") or {}), ensure_ascii=False, separators=(",", ":")),
                    "error_message": str(item.get("error_message") or ""),
                })
                count += 1
                if count % 10_000 == 0:
                    run.processed_row_count = count
                    self.repository.update_monitoring_run(run)
        run.processed_row_count = count
        self.repository.update_monitoring_run(run)
        return count

    def _csv_relation(self, path: Path) -> str:
        columns = ", ".join(
            f"{sql_literal(name)}: {sql_literal(kind)}"
            for name, kind in self.snapshot_columns.items()
        )
        return (
            f"SELECT * FROM read_csv({sql_literal(str(path))}, header=true, "
            f"columns={{{columns}}}, nullstr='', strict_mode=true)"
        )

    def _resolve_join_strategy(
        self, run: OnlineMonitoringRun, actual_columns: set[str]
    ) -> str:
        if run.join_strategy != "auto":
            strategy = run.join_strategy
        elif run.actuals_prediction_id_column in actual_columns:
            strategy = "prediction_id"
        elif (
            run.actuals_request_id_column in actual_columns
            and run.actuals_record_id_column in actual_columns
        ):
            strategy = "request_record_id"
        else:
            strategy = "record_id"
        required = {
            "prediction_id": [run.actuals_prediction_id_column],
            "request_record_id": [run.actuals_request_id_column, run.actuals_record_id_column],
            "record_id": [run.actuals_record_id_column],
        }[strategy]
        missing = [column for column in required if column not in actual_columns]
        if missing:
            raise ValueError(
                f"Actuals dataset is missing join column(s): {', '.join(missing)}"
            )
        return strategy

    def _labels_sql(
        self,
        connection: Any,
        run: OnlineMonitoringRun,
        strategy: str,
        snapshot: str,
        actuals: str,
    ) -> tuple[str, int]:
        target = identifier(run.actuals_target_column)
        record = identifier(run.actuals_record_id_column)
        prediction_id = identifier(run.actuals_prediction_id_column)
        request_id = identifier(run.actuals_request_id_column)
        if strategy == "prediction_id":
            self._validate_unique_key(connection, actuals, [prediction_id], "actuals prediction_id")
            labels = (
                f"SELECT served.request_id, served.record_id, actuals.{target} AS monitoring_actual "
                f"FROM {actuals} actuals JOIN {snapshot} served "
                f"ON cast(actuals.{prediction_id} AS VARCHAR) = served.prediction_id "
                "WHERE served.served"
            )
            unmatched = connection.execute(
                f"SELECT count(*) FROM {actuals} actuals LEFT JOIN {snapshot} served "
                f"ON cast(actuals.{prediction_id} AS VARCHAR) = served.prediction_id AND served.served "
                "WHERE served.prediction_id IS NULL"
            ).fetchone()[0]
        elif strategy == "request_record_id":
            self._validate_unique_key(
                connection, actuals, [request_id, record], "actuals request_id + record_id"
            )
            labels = (
                f"SELECT cast(actuals.{request_id} AS VARCHAR) AS request_id, "
                f"cast(actuals.{record} AS VARCHAR) AS record_id, "
                f"actuals.{target} AS monitoring_actual FROM {actuals} actuals"
            )
            unmatched = connection.execute(
                f"SELECT count(*) FROM {actuals} actuals LEFT JOIN {snapshot} served "
                f"ON cast(actuals.{request_id} AS VARCHAR) = served.request_id "
                f"AND cast(actuals.{record} AS VARCHAR) = served.record_id AND served.served "
                "WHERE served.prediction_id IS NULL"
            ).fetchone()[0]
        else:
            self._validate_unique_key(connection, actuals, [record], "actuals record_id")
            duplicate_prediction_records = connection.execute(
                f"SELECT count(*) FROM (SELECT record_id FROM {snapshot} WHERE served "
                "GROUP BY record_id HAVING count(*) > 1) duplicates"
            ).fetchone()[0]
            if int(duplicate_prediction_records):
                raise ValueError(
                    "record_id is not unique in the selected inference window; provide prediction_id, "
                    "request_id + record_id, or select a narrower window"
                )
            labels = (
                f"SELECT served.request_id, served.record_id, actuals.{target} AS monitoring_actual "
                f"FROM {snapshot} served JOIN {actuals} actuals "
                f"ON served.record_id = cast(actuals.{record} AS VARCHAR) WHERE served.served"
            )
            unmatched = connection.execute(
                f"SELECT count(*) FROM {actuals} actuals LEFT JOIN {snapshot} served "
                f"ON cast(actuals.{record} AS VARCHAR) = served.record_id AND served.served "
                "WHERE served.prediction_id IS NULL"
            ).fetchone()[0]
        return labels, int(unmatched)

    @staticmethod
    def _validate_unique_key(
        connection: Any, relation: str, columns: list[str], label: str
    ) -> None:
        null_predicate = " OR ".join(f"{column} IS NULL" for column in columns)
        distinct = ", ".join(columns)
        total, nulls = connection.execute(
            f"SELECT count(*), count(*) FILTER (WHERE {null_predicate}) FROM {relation}"
        ).fetchone()
        unique = connection.execute(
            f"SELECT count(*) FROM (SELECT {distinct} FROM {relation} "
            f"WHERE NOT ({null_predicate}) GROUP BY {distinct}) unique_keys"
        ).fetchone()[0]
        if int(nulls):
            raise ValueError(f"{label} contains {int(nulls)} null key value(s)")
        if int(unique) != int(total):
            raise ValueError(f"{label} must be unique; duplicate keys would create a many-to-many join")

    def _performance_report(
        self,
        connection: Any,
        joined_relation: str,
        run: OnlineMonitoringRun,
        representative: Any,
        models_by_id: dict[str, Any],
    ) -> dict[str, Any]:
        target_cast = "try_cast(monitoring_actual AS DOUBLE)" if run.problem_type == "regression" else "cast(monitoring_actual AS VARCHAR)"
        prediction_cast = "try_cast(prediction_value AS DOUBLE)" if run.problem_type == "regression" else "cast(prediction_value AS VARCHAR)"
        score_contract = self._score_contract(representative)
        service_relation = (
            f"SELECT *, {target_cast} AS monitoring_target, {prediction_cast} AS monitoring_prediction "
            f"FROM {joined_relation} WHERE served AND execution_status = 'succeeded'"
        )
        builder = ModelEvaluationSnapshotBuilder()
        service = builder.build(
            connection,
            service_relation,
            problem_type="regression" if run.problem_type == "regression" else "classification",
            target_column="monitoring_target",
            prediction_column="monitoring_prediction",
            score_contract=score_contract,
        )
        groups = connection.execute(
            f"SELECT deployment_revision_id, model_id, role, count(*) "
            f"FROM {joined_relation} WHERE execution_status = 'succeeded' "
            "GROUP BY deployment_revision_id, model_id, role "
            "ORDER BY deployment_revision_id, role, model_id"
        ).fetchall()
        models = []
        for revision_id, model_id, role, row_count in groups:
            relation = (
                f"SELECT *, {target_cast} AS monitoring_target, {prediction_cast} AS monitoring_prediction "
                f"FROM {joined_relation} WHERE execution_status = 'succeeded' "
                f"AND deployment_revision_id = {sql_literal(str(revision_id))} "
                f"AND model_id = {sql_literal(str(model_id))} AND role = {sql_literal(str(role))}"
            )
            evaluation = builder.build(
                connection,
                relation,
                problem_type="regression" if run.problem_type == "regression" else "classification",
                target_column="monitoring_target",
                prediction_column="monitoring_prediction",
                score_contract=score_contract,
            )
            group_warnings = list(evaluation.get("warnings") or [])
            if role == "fallback":
                group_warnings.append(
                    "Fallback performance is measured on a selective technical-failure cohort and may not represent normal traffic"
                )
            evaluation["warnings"] = list(dict.fromkeys(group_warnings))
            models.append({
                "deployment_revision_id": str(revision_id),
                "model_id": str(model_id),
                "bundle_id": (
                    models_by_id[str(model_id)].pipeline_run_id
                    or models_by_id[str(model_id)].id
                ),
                "role": str(role),
                "scored_row_count": int(row_count),
                "evaluation": evaluation,
            })
        return {
            "problem_type": run.problem_type,
            "target_column": run.actuals_target_column,
            "service": service,
            "models": models,
            "warnings": list(service.get("warnings") or []),
        }

    def _input_monitoring(
        self, connection: Any, snapshot_relation: str, model: Any
    ) -> dict[str, Any]:
        feature_definition = model.feature_engineering_definition or {}
        features = [
            str(value) for value in (
                feature_definition.get("feature_columns") or model.feature_columns
            )
        ]
        auto_fe = dict(model.training_config.get("auto_feature_engineering") or {})
        decisions = {
            str(item.get("column")): item
            for item in auto_fe.get("column_decisions") or []
            if isinstance(item, dict) and item.get("column")
        }
        rows = []
        warnings: list[str] = []
        for feature in features:
            path = '$."' + feature.replace('\\', '\\\\').replace('"', '\\"') + '"'
            expression = f"json_extract_string(input_json, {sql_literal(path)})"
            decision = decisions.get(feature, {})
            baseline = dict(decision.get("numeric_profile") or {})
            is_numeric = any(
                token in str(decision.get("type") or "").upper()
                for token in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC")
            ) or bool(baseline)
            if is_numeric:
                total, missing, valid, mean, minimum, maximum = connection.execute(
                    f"SELECT count(*), count(*) FILTER (WHERE {expression} IS NULL), "
                    f"count(try_cast({expression} AS DOUBLE)), avg(try_cast({expression} AS DOUBLE)), "
                    f"min(try_cast({expression} AS DOUBLE)), max(try_cast({expression} AS DOUBLE)) "
                    f"FROM {snapshot_relation} WHERE served AND execution_status = 'succeeded'"
                ).fetchone()
                baseline_min = baseline.get("min")
                baseline_max = baseline.get("max")
                baseline_mean = baseline.get("mean")
                range_violations = 0
                if baseline_min is not None and baseline_max is not None:
                    range_violations = int(connection.execute(
                        f"SELECT count(*) FROM {snapshot_relation} WHERE served AND execution_status = 'succeeded' "
                        f"AND try_cast({expression} AS DOUBLE) IS NOT NULL AND "
                        f"(try_cast({expression} AS DOUBLE) < ? OR try_cast({expression} AS DOUBLE) > ?)",
                        [float(baseline_min), float(baseline_max)],
                    ).fetchone()[0])
                width = (
                    float(baseline_max) - float(baseline_min)
                    if baseline_min is not None and baseline_max is not None
                    else 0.0
                )
                mean_shift = (
                    abs(float(mean) - float(baseline_mean)) / width
                    if mean is not None and baseline_mean is not None and width > 0
                    else None
                )
                rows.append({
                    "feature": feature,
                    "kind": "numeric",
                    "row_count": int(total),
                    "missing_count": int(missing),
                    "valid_numeric_count": int(valid),
                    "current": {"mean": mean, "minimum": minimum, "maximum": maximum},
                    "baseline": {
                        "source": "model_training_profile" if baseline else "unavailable",
                        "mean": baseline_mean,
                        "minimum": baseline_min,
                        "maximum": baseline_max,
                    },
                    "range_violation_count": range_violations,
                    "normalized_mean_shift": mean_shift,
                })
            else:
                total, missing = connection.execute(
                    f"SELECT count(*), count(*) FILTER (WHERE {expression} IS NULL) "
                    f"FROM {snapshot_relation} WHERE served AND execution_status = 'succeeded'"
                ).fetchone()
                top = connection.execute(
                    f"SELECT {expression} AS value, count(*) AS count FROM {snapshot_relation} "
                    f"WHERE served AND execution_status = 'succeeded' AND {expression} IS NOT NULL "
                    "GROUP BY value ORDER BY count DESC, value LIMIT 20"
                ).fetchall()
                rows.append({
                    "feature": feature,
                    "kind": "categorical",
                    "row_count": int(total),
                    "missing_count": int(missing),
                    "top_values": [
                        {"value": str(value), "count": int(count)} for value, count in top
                    ],
                    "baseline": {"source": "unavailable"},
                })
        if features and not any(item.get("baseline", {}).get("source") != "unavailable" for item in rows):
            warnings.append(
                "Training feature distribution baseline is unavailable for this model; the report still contains full-window input quality statistics"
            )
        return {
            "scope": "full",
            "feature_count": len(features),
            "features": rows,
            "warnings": warnings,
        }

    @staticmethod
    def _prediction_monitoring(
        connection: Any, snapshot_relation: str, problem_type: str
    ) -> dict[str, Any]:
        warnings: list[str] = []
        if problem_type == "regression":
            count, minimum, maximum, mean = connection.execute(
                f"SELECT count(try_cast(prediction_value AS DOUBLE)), "
                f"min(try_cast(prediction_value AS DOUBLE)), max(try_cast(prediction_value AS DOUBLE)), "
                f"avg(try_cast(prediction_value AS DOUBLE)) FROM {snapshot_relation} "
                "WHERE served AND execution_status = 'succeeded'"
            ).fetchone()
            histogram = []
            if count and minimum is not None and maximum is not None:
                if float(minimum) == float(maximum):
                    histogram = [{"lower": float(minimum), "upper": float(maximum), "count": int(count)}]
                else:
                    width = (float(maximum) - float(minimum)) / 20
                    histogram = [
                        {"lower": float(lower), "upper": float(upper), "count": int(value_count)}
                        for lower, upper, value_count in connection.execute(
                            f"WITH values AS (SELECT try_cast(prediction_value AS DOUBLE) value FROM {snapshot_relation} "
                            "WHERE served AND execution_status = 'succeeded'), bins AS ("
                            f"SELECT least(19, floor((value - {float(minimum)}) / {width}))::INTEGER bin, count(*) count "
                            "FROM values WHERE value IS NOT NULL GROUP BY bin) "
                            f"SELECT {float(minimum)} + bin * {width}, {float(minimum)} + (bin + 1) * {width}, count "
                            "FROM bins ORDER BY bin"
                        ).fetchall()
                    ]
            return {
                "scope": "full", "kind": "regression", "count": int(count or 0),
                "summary": {"minimum": minimum, "maximum": maximum, "mean": mean},
                "histogram": histogram, "warnings": warnings,
            }
        total = int(connection.execute(
            f"SELECT count(*) FROM {snapshot_relation} WHERE served AND execution_status = 'succeeded'"
        ).fetchone()[0])
        values = connection.execute(
            f"SELECT prediction_value, count(*) count FROM {snapshot_relation} "
            "WHERE served AND execution_status = 'succeeded' GROUP BY prediction_value "
            "ORDER BY count DESC, prediction_value LIMIT 100"
        ).fetchall()
        returned = sum(int(count) for _, count in values)
        if returned < total:
            warnings.append("Prediction distribution returns the 100 most frequent classes; remaining classes are grouped as other")
        distribution = [
            {"value": value, "count": int(count), "share": int(count) / total if total else 0.0}
            for value, count in values
        ]
        if returned < total:
            distribution.append({"value": "__other__", "count": total - returned, "share": (total - returned) / total})
        return {
            "scope": "full", "kind": "classification", "count": total,
            "distribution": distribution, "warnings": warnings,
        }

    @staticmethod
    def _time_aggregation(
        connection: Any,
        snapshot_relation: str,
        run: OnlineMonitoringRun,
    ) -> dict[str, Any]:
        granularity = run.aggregation_granularity
        if granularity == "none":
            return {
                "granularity": "none",
                "time_basis": run.time_basis,
                "timezone": "UTC",
                "bucket_count": 0,
                "buckets": [],
            }
        intervals = {
            "hour": "1 hour",
            "day": "1 day",
            "week": "1 week",
            "month": "1 month",
        }
        interval = intervals.get(granularity)
        if interval is None:
            raise ValueError(f"Unsupported monitoring aggregation granularity {granularity!r}")
        rows = connection.execute(
            f"""
            WITH bounds AS (
                SELECT
                    date_trunc('{granularity}', CAST(? AS TIMESTAMPTZ) AT TIME ZONE 'UTC') AS first_bucket,
                    date_trunc('{granularity}', (CAST(? AS TIMESTAMPTZ) - INTERVAL '1 microsecond') AT TIME ZONE 'UTC') AS last_bucket
            ),
            buckets AS (
                SELECT unnest(generate_series(first_bucket, last_bucket, INTERVAL '{interval}')) AS bucket_start
                FROM bounds
            ),
            request_rows AS (
                SELECT
                    request_id,
                    min(scored_at) AS scored_at,
                    max(request_status) AS request_status,
                    bool_or(fallback_used) AS fallback_used,
                    max(request_latency_ms) AS request_latency_ms
                FROM {snapshot_relation}
                GROUP BY request_id
            ),
            request_aggregates AS (
                SELECT
                    date_trunc('{granularity}', scored_at AT TIME ZONE 'UTC') AS bucket_start,
                    count(*) AS request_count,
                    count(*) FILTER (WHERE request_status = 'succeeded') AS succeeded_request_count,
                    count(*) FILTER (WHERE request_status = 'failed') AS failed_request_count,
                    count(*) FILTER (WHERE fallback_used) AS fallback_request_count,
                    avg(request_latency_ms) AS average_latency_ms,
                    quantile_cont(request_latency_ms, 0.95) AS p95_latency_ms,
                    max(request_latency_ms) AS maximum_latency_ms
                FROM request_rows
                GROUP BY 1
            ),
            execution_aggregates AS (
                SELECT
                    date_trunc('{granularity}', scored_at AT TIME ZONE 'UTC') AS bucket_start,
                    count(*) AS execution_count,
                    count(*) FILTER (WHERE served) AS served_prediction_count
                FROM {snapshot_relation}
                GROUP BY 1
            )
            SELECT
                buckets.bucket_start,
                buckets.bucket_start + INTERVAL '{interval}' AS bucket_end,
                coalesce(request_aggregates.request_count, 0),
                coalesce(request_aggregates.succeeded_request_count, 0),
                coalesce(request_aggregates.failed_request_count, 0),
                coalesce(request_aggregates.fallback_request_count, 0),
                request_aggregates.average_latency_ms,
                request_aggregates.p95_latency_ms,
                request_aggregates.maximum_latency_ms,
                coalesce(execution_aggregates.execution_count, 0),
                coalesce(execution_aggregates.served_prediction_count, 0)
            FROM buckets
            LEFT JOIN request_aggregates USING (bucket_start)
            LEFT JOIN execution_aggregates USING (bucket_start)
            ORDER BY buckets.bucket_start
            """,
            [run.since, run.until],
        ).fetchall()
        buckets = []
        for row in rows:
            bucket_start, bucket_end = row[0], row[1]
            if bucket_start.tzinfo is None:
                bucket_start = bucket_start.replace(tzinfo=timezone.utc)
            if bucket_end.tzinfo is None:
                bucket_end = bucket_end.replace(tzinfo=timezone.utc)
            observed_since = max(bucket_start, run.since)
            observed_until = min(bucket_end, run.until)
            if granularity == "hour":
                label = f"{bucket_start:%Y-%m-%d %H}:00–{bucket_start:%H}:59"
            elif granularity == "day":
                label = f"{bucket_start:%Y-%m-%d}"
            elif granularity == "week":
                label = f"{bucket_start:%Y-%m-%d}–{(bucket_end - timedelta(days=1)):%Y-%m-%d}"
            else:
                label = f"{bucket_start:%Y-%m}"
            buckets.append({
                "label": label,
                "bucket_start": bucket_start.isoformat(),
                "bucket_end": bucket_end.isoformat(),
                "observed_since": observed_since.isoformat(),
                "observed_until": observed_until.isoformat(),
                "request_count": int(row[2]),
                "succeeded_request_count": int(row[3]),
                "failed_request_count": int(row[4]),
                "fallback_request_count": int(row[5]),
                "average_latency_ms": float(row[6]) if row[6] is not None else None,
                "p95_latency_ms": float(row[7]) if row[7] is not None else None,
                "maximum_latency_ms": float(row[8]) if row[8] is not None else None,
                "execution_count": int(row[9]),
                "served_prediction_count": int(row[10]),
            })
        return {
            "granularity": granularity,
            "time_basis": run.time_basis,
            "timezone": "UTC",
            "bucket_count": len(buckets),
            "buckets": buckets,
        }

    @staticmethod
    def _score_contract(model: Any) -> dict[str, Any]:
        classes = model.model_parameters.get("classes") or model.training_config.get("classes") or []
        positive = classes[-1] if len(classes) == 2 else None
        return {
            "prediction_score_column": "prediction_score" if model.problem_type != "regression" else None,
            "probability_available": model.problem_type != "regression",
            "positive_class": positive,
        }

    def _register_dataset(
        self,
        *,
        run: OnlineMonitoringRun,
        dataset_id: str,
        name: str,
        path: Path,
        row_count: int,
        role: DataRole,
        artifact_type: ArtifactType,
        metadata: dict[str, Any],
    ) -> Artifact:
        now = datetime.now(timezone.utc)
        asset = self.dataset_repository.get(dataset_id)
        if asset is None:
            asset = DataAsset(
                id=dataset_id,
                owner_id=run.owner_id,
                name=name,
                source_type=SourceType.FILE,
                format="parquet",
                logical_id=dataset_id,
                version_number=1,
                version_stage="final",
                description="Immutable full-scope online monitoring materialization",
                original_filename=path.name,
                location_uri=f"file://{path.as_posix()}",
                file_size_bytes=path.stat().st_size,
                row_count=row_count,
                has_header=None,
                uploaded_by=run.requested_by,
                uploaded_at=now,
                status=DataAssetStatus.READY,
                tags=["online-monitoring", role.value],
                metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            self.dataset_repository.add(asset)
        artifact = self.business_cases.find_artifact(
            run.owner_id, dataset_id, run.business_case_id
        )
        if artifact is None:
            artifact = Artifact(
                id=str(uuid5(NAMESPACE_URL, f"mlapp:artifact:{artifact_type.value}:{dataset_id}")),
                owner_id=run.owner_id,
                type=artifact_type,
                reference_id=dataset_id,
                origin=ArtifactOrigin.PLATFORM_GENERATED,
                business_case_id=run.business_case_id,
                metadata={
                    "location_uri": f"file://{path.as_posix()}",
                    "row_count": row_count,
                    "lineage": {
                        "online_monitoring_run_id": run.id,
                        "deployment_id": run.deployment_id,
                        "actuals_artifact_id": run.actuals_artifact_id,
                        "created_by": run.requested_by,
                    },
                },
                created_by=run.requested_by,
                created_at=now,
            )
            self.business_cases.add_artifact(artifact)
        attachments = self.business_cases.list_data_attachments(run.business_case_id)
        if not any(item.data_asset_id == dataset_id and item.role == role for item in attachments):
            self.business_cases.add_data_attachment(BusinessCaseDataAttachment(
                id=str(uuid5(NAMESPACE_URL, f"mlapp:attachment:{run.business_case_id}:{dataset_id}:{role.value}")),
                owner_id=run.owner_id,
                business_case_id=run.business_case_id,
                artifact_id=artifact.id,
                data_asset_id=dataset_id,
                data_asset_kind=DataArtifactKind.DATASET,
                role=role,
                context_note="Generated by manual online service monitoring",
                primary_key_column="prediction_id" if role == DataRole.SCORING_OUTPUT else "record_id",
                target_column=run.actuals_target_column if role == DataRole.MONITORING_INPUT else "",
                created_by=run.requested_by,
                created_at=now,
            ))
        return artifact

    def _register_report(
        self,
        run: OnlineMonitoringRun,
        report: dict[str, Any],
        snapshot: Artifact,
        joined: Artifact | None,
    ) -> Artifact:
        artifact_id = str(uuid5(NAMESPACE_URL, f"mlapp:online-monitoring-report:{run.id}"))
        existing = self.business_cases.get_artifact(artifact_id)
        if existing:
            return existing
        input_artifact_ids = [snapshot.id]
        input_lineage = [{"input_port_id": "predictions", "artifact_ids": [snapshot.id]}]
        if run.actuals_artifact_id:
            input_artifact_ids.append(run.actuals_artifact_id)
            input_lineage.append({"input_port_id": "actuals", "artifact_ids": [run.actuals_artifact_id]})
        if joined is not None:
            input_artifact_ids.append(joined.id)
            input_lineage.append({"input_port_id": "joined", "artifact_ids": [joined.id]})
        artifact = Artifact(
            id=artifact_id,
            owner_id=run.owner_id,
            type=ArtifactType.REPORT,
            reference_id=run.id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=run.business_case_id,
            metadata={
                "report_name": report["name"],
                "report_type": report["report_type"],
                "report": report,
                "online_monitoring_run_id": run.id,
                "deployment_id": run.deployment_id,
                "lineage": {
                    "input_artifact_ids": input_artifact_ids,
                    "input_lineage": input_lineage,
                    "online_monitoring_run_id": run.id,
                    "deployment_id": run.deployment_id,
                    "created_by": run.requested_by,
                },
            },
            created_by=run.requested_by,
        )
        return self.business_cases.add_artifact(artifact)

    def _active_champion(self, deployment: Any, principal: Principal) -> Any:
        revision = self.repository.get_revision(deployment.active_revision_id)
        if revision is None:
            raise HTTPException(status_code=409, detail="Deployment has no active revision")
        assignment = next((item for item in revision.assignments if item.role.value == "champion"), None)
        if assignment is None:
            raise HTTPException(status_code=409, detail="Deployment has no champion")
        return self.models.get_model_for_inference(assignment.model_id, principal)

    def _representative_model(
        self, deployment: Any, models: dict[str, Any], principal: Principal
    ) -> Any:
        champion = self._active_champion(deployment, principal)
        return models.get(champion.id, champion)

    def _actuals_attachment(
        self, business_case_id: str, dataset_id: str
    ) -> BusinessCaseDataAttachment:
        attachments = [
            item for item in self.business_cases.list_data_attachments(business_case_id)
            if item.role == DataRole.MONITORING_ACTUALS
        ]
        attachment = next((item for item in attachments if item.data_asset_id == dataset_id), None)
        selected = self.dataset_repository.get(dataset_id)
        if attachment is None and selected is not None:
            attachment = next((
                item for item in attachments
                if (
                    (attached := self.dataset_repository.get(item.data_asset_id)) is not None
                    and attached.logical_id == selected.logical_id
                )
            ), None)
        if attachment is None:
            raise HTTPException(
                status_code=409,
                detail="Selected actuals version must be attached to the deployment Business Case with role monitoring_actuals",
            )
        return attachment

    def _ensure_actuals_artifact(
        self,
        actuals: DataAsset,
        business_case_id: str,
        owner_id: str,
        created_by: str,
    ) -> Artifact:
        existing = self.business_cases.find_artifact(
            owner_id, actuals.id, business_case_id
        )
        if existing is not None:
            return existing
        artifact = Artifact(
            id=str(uuid5(NAMESPACE_URL, f"mlapp:actuals-artifact:{business_case_id}:{actuals.id}")),
            owner_id=owner_id,
            type=ArtifactType.DATA_VIEW if actuals.source_type == SourceType.VIEW else ArtifactType.DATASET,
            reference_id=actuals.id,
            origin=ArtifactOrigin.UPLOADED,
            business_case_id=business_case_id,
            metadata={
                "logical_id": actuals.logical_id,
                "version_number": actuals.version_number,
                "registered_for_online_monitoring": True,
            },
            created_by=created_by,
        )
        return self.business_cases.add_artifact(artifact)

    def _deployment(
        self,
        deployment_id: str,
        principal: Principal,
        minimum: BusinessCaseAccessRole,
    ) -> Any:
        deployment = self.repository.get_deployment(deployment_id)
        if deployment is None:
            raise HTTPException(status_code=404, detail="Deployment not found")
        access_policy.require_business_case(principal, deployment.business_case_id, minimum)
        return deployment

    @staticmethod
    def _can_view_report(principal: Principal, business_case_id: str) -> bool:
        role = access_policy.business_case_role(principal, business_case_id)
        return role is not None and BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.REPORT_VIEWER]

    @staticmethod
    def _requester(run: OnlineMonitoringRun) -> Principal | None:
        from app.modules.auth.repository import PostgresUserRepository
        account = PostgresUserRepository().get(run.requested_by)
        if account is None or not account.is_active:
            return None
        return Principal(
            user_id=account.id,
            email=account.email,
            display_name=account.display_name,
            login_name=account.login_name,
            roles=account.roles,
            session_version=account.session_version,
        )

    def _run_directory(self, run: OnlineMonitoringRun) -> Path:
        directory = (
            self.repository_root / "users" / run.owner_id / "online-monitoring" / run.id
        ).resolve()
        try:
            directory.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("Monitoring materialization path is outside the repository root") from exc
        return directory

    def _fail(self, run: OnlineMonitoringRun, message: str) -> OnlineMonitoringRun:
        run.status = MonitoringRunStatus.FAILED
        run.error_message = message[:4000]
        run.completed_at = datetime.now(timezone.utc)
        self.repository.update_monitoring_run(run)
        return run
