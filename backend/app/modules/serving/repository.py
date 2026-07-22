from __future__ import annotations

from datetime import datetime
from collections.abc import Iterator
from typing import Any, Protocol

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, and_, case, func, or_, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.serving.domain import (
    BatchScoreJob,
    ChallengerReplayJob,
    Deployment,
    DeploymentRevision,
    DeploymentRole,
    DeploymentStatus,
    InferenceRequest,
    InferenceStatus,
    ModelAssignment,
    MonitoringRunStatus,
    OnlineMonitoringRun,
    ReplayStatus,
)


SERVING_SCHEMA = "mlapp"
metadata = MetaData(schema=SERVING_SCHEMA)

deployments_table = Table(
    "serving_deployments", metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("slug", String(255), nullable=False, unique=True),
    Column("status", String(32), nullable=False),
    Column("active_revision_id", String(64), nullable=False, default=""),
    Column("endpoint_url", Text, nullable=True),
    Column("retention_days", Integer, nullable=False, default=365),
    Column("created_by", String(64), nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

deployment_revisions_table = Table(
    "serving_deployment_revisions", metadata,
    Column("id", String(64), primary_key=True),
    Column("deployment_id", String(64), nullable=False, index=True),
    Column("version_number", Integer, nullable=False),
    Column("assignments", JSON, nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

active_model_assignments_table = Table(
    "serving_active_model_assignments", metadata,
    Column("deployment_id", String(64), primary_key=True),
    Column("model_id", String(64), primary_key=True),
    Column("revision_id", String(64), nullable=False, index=True),
    Column("role", String(32), nullable=False),
)

inference_requests_table = Table(
    "serving_inference_requests", metadata,
    Column("id", String(64), primary_key=True),
    Column("deployment_id", String(64), nullable=False, index=True),
    Column("deployment_revision_id", String(64), nullable=False, index=True),
    Column("requested_by", String(64), nullable=False, index=True),
    Column("correlation_id", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False, default=""),
    Column("request_hash", String(64), nullable=False, default=""),
    Column("status", String(32), nullable=False),
    Column("record_count", Integer, nullable=False),
    Column("request_payload", JSON, nullable=False),
    Column("response_payload", JSON, nullable=False, default=dict),
    Column("warnings", JSON, nullable=False, default=list),
    Column("error_code", String(128), nullable=False, default=""),
    Column("error_message", Text, nullable=False, default=""),
    Column("champion_model_id", String(64), nullable=False, default=""),
    Column("requested_model_id", String(64), nullable=False, default=""),
    Column("requested_role", String(32), nullable=False, default="champion"),
    Column("served_model_id", String(64), nullable=False, default=""),
    Column("served_role", String(32), nullable=False, default=""),
    Column("fallback_used", Boolean, nullable=False, default=False),
    Column("latency_ms", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)

inference_items_table = Table(
    "serving_inference_items", metadata,
    Column("id", String(128), primary_key=True),
    Column("request_id", String(64), nullable=False, index=True),
    Column("deployment_id", String(64), nullable=False, index=True),
    Column("record_id", String(512), nullable=False, index=True),
    Column("model_id", String(64), nullable=False),
    Column("role", String(32), nullable=False),
    Column("input", JSON, nullable=False),
    Column("output", JSON, nullable=False),
    Column("status", String(32), nullable=False, default="succeeded"),
    Column("error_message", Text, nullable=False, default=""),
    Column("latency_ms", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

challenger_replay_jobs_table = Table(
    "serving_challenger_replay_jobs", metadata,
    Column("id", String(64), primary_key=True),
    Column("deployment_id", String(64), nullable=False, index=True),
    Column("deployment_revision_id", String(64), nullable=False),
    Column("challenger_model_id", String(64), nullable=False),
    Column("requested_by", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("source_before", DateTime(timezone=True), nullable=False),
    Column("source_since", DateTime(timezone=True), nullable=True),
    Column("source_until", DateTime(timezone=True), nullable=True),
    Column("max_requests", Integer, nullable=False),
    Column("processed_requests", Integer, nullable=False, default=0),
    Column("processed_records", Integer, nullable=False, default=0),
    Column("failed_requests", Integer, nullable=False, default=0),
    Column("error_message", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)

monitoring_runs_table = Table(
    "serving_monitoring_runs", metadata,
    Column("id", String(64), primary_key=True),
    Column("deployment_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("requested_by", String(64), nullable=False, index=True),
    Column("status", String(32), nullable=False, index=True),
    Column("since", DateTime(timezone=True), nullable=False),
    Column("until", DateTime(timezone=True), nullable=False),
    Column("source_before", DateTime(timezone=True), nullable=False),
    Column("actuals_dataset_id", String(64), nullable=False),
    Column("actuals_artifact_id", String(64), nullable=False, default=""),
    Column("join_strategy", String(32), nullable=False, default="auto"),
    Column("actuals_prediction_id_column", String(255), nullable=False, default="prediction_id"),
    Column("actuals_request_id_column", String(255), nullable=False, default="request_id"),
    Column("actuals_record_id_column", String(255), nullable=False, default=""),
    Column("actuals_target_column", String(255), nullable=False, default=""),
    Column("problem_type", String(64), nullable=False, default=""),
    Column("target_column", String(255), nullable=False, default=""),
    Column("time_basis", String(32), nullable=False, default="scored_at"),
    Column("processed_request_count", Integer, nullable=False, default=0),
    Column("processed_row_count", Integer, nullable=False, default=0),
    Column("matched_row_count", Integer, nullable=False, default=0),
    Column("missing_actuals_count", Integer, nullable=False, default=0),
    Column("unmatched_actuals_count", Integer, nullable=False, default=0),
    Column("snapshot_dataset_id", String(64), nullable=False, default=""),
    Column("joined_dataset_id", String(64), nullable=False, default=""),
    Column("report_artifact_id", String(64), nullable=False, default=""),
    Column("report", JSON, nullable=False, default=dict),
    Column("warnings", JSON, nullable=False, default=list),
    Column("error_message", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)


class ServingRepository(Protocol):
    def add_deployment(self, deployment: Deployment, revision: DeploymentRevision) -> Deployment: ...
    def update_deployment(self, deployment: Deployment) -> Deployment: ...
    def list_all_deployments(self) -> list[Deployment]: ...
    def get_deployment(self, deployment_id_or_slug: str) -> Deployment | None: ...
    def add_revision(self, revision: DeploymentRevision, deployment: Deployment) -> DeploymentRevision: ...
    def get_revision(self, revision_id: str) -> DeploymentRevision | None: ...
    def list_revisions(self, deployment_id: str) -> list[DeploymentRevision]: ...
    def active_assignments_for_model(self, model_id: str) -> list[dict[str, Any]]: ...
    def clear_active_assignments(self, deployment_id: str) -> None: ...
    def restore_active_assignments(self, deployment: Deployment, revision: DeploymentRevision) -> None: ...
    def set_deployment_status(self, deployment: Deployment, revision: DeploymentRevision) -> Deployment: ...
    def add_inference(self, inference: InferenceRequest) -> InferenceRequest: ...
    def get_inference(self, request_id: str) -> InferenceRequest | None: ...
    def find_idempotent(self, deployment_id: str, requested_by: str, key: str) -> InferenceRequest | None: ...
    def complete_inference(self, inference: InferenceRequest, items: list[dict[str, Any]]) -> InferenceRequest: ...
    def list_inference(self, deployment_id: str, limit: int, cursor: tuple[datetime, str] | None, record_id: str | None = None) -> list[InferenceRequest]: ...
    def inference_items(self, request_id: str) -> list[dict[str, Any]]: ...
    def prune_expired(self, deployment_id: str, cutoff: datetime) -> int: ...
    def add_replay(self, job: ChallengerReplayJob) -> ChallengerReplayJob: ...
    def get_replay(self, job_id: str) -> ChallengerReplayJob | None: ...
    def update_replay(self, job: ChallengerReplayJob) -> ChallengerReplayJob: ...
    def list_replays(self, deployment_id: str) -> list[ChallengerReplayJob]: ...
    def replay_sources(self, job: ChallengerReplayJob) -> list[InferenceRequest]: ...
    def add_monitoring_run(self, run: OnlineMonitoringRun) -> OnlineMonitoringRun: ...
    def get_monitoring_run(self, run_id: str) -> OnlineMonitoringRun | None: ...
    def update_monitoring_run(self, run: OnlineMonitoringRun) -> OnlineMonitoringRun: ...
    def list_monitoring_runs(self, deployment_id: str | None = None, limit: int = 200) -> list[OnlineMonitoringRun]: ...
    def iter_monitoring_items(
        self, deployment_id: str, since: datetime, until: datetime, source_before: datetime
    ) -> Iterator[dict[str, Any]]: ...
    def monitoring_request_stats(
        self, deployment_id: str, since: datetime, until: datetime, source_before: datetime
    ) -> dict[str, Any]: ...


class PostgresServingRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add_deployment(self, deployment: Deployment, revision: DeploymentRevision) -> Deployment:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(deployments_table.insert().values(**self._deployment_record(deployment)))
            connection.execute(deployment_revisions_table.insert().values(**self._revision_record(revision)))
            self._replace_active_assignments(connection, deployment.id, revision)
        return deployment

    def update_deployment(self, deployment: Deployment) -> Deployment:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                deployments_table.update().where(deployments_table.c.id == deployment.id)
                .values(**self._deployment_record(deployment))
            )
        return deployment

    def list_all_deployments(self) -> list[Deployment]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(deployments_table).order_by(deployments_table.c.updated_at.desc()))
            return [self._deployment(row._mapping) for row in rows]

    def get_deployment(self, deployment_id_or_slug: str) -> Deployment | None:
        self._ensure_initialized()
        statement = select(deployments_table).where(or_(
            deployments_table.c.id == deployment_id_or_slug,
            deployments_table.c.slug == deployment_id_or_slug,
        ))
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._deployment(row._mapping) if row else None

    def add_revision(self, revision: DeploymentRevision, deployment: Deployment) -> DeploymentRevision:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            current = connection.execute(
                select(deployments_table.c.active_revision_id).where(deployments_table.c.id == deployment.id).with_for_update()
            ).scalar_one_or_none()
            if current is None:
                raise LookupError("Deployment no longer exists")
            connection.execute(deployment_revisions_table.insert().values(**self._revision_record(revision)))
            connection.execute(
                deployments_table.update().where(deployments_table.c.id == deployment.id).values(
                    active_revision_id=revision.id,
                    updated_by=deployment.updated_by,
                    updated_at=deployment.updated_at,
                    status=deployment.status.value,
                )
            )
            self._replace_active_assignments(connection, deployment.id, revision)
        return revision

    def get_revision(self, revision_id: str) -> DeploymentRevision | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(deployment_revisions_table).where(deployment_revisions_table.c.id == revision_id)
            ).first()
        return self._revision(row._mapping) if row else None

    def list_revisions(self, deployment_id: str) -> list[DeploymentRevision]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(deployment_revisions_table)
                .where(deployment_revisions_table.c.deployment_id == deployment_id)
                .order_by(deployment_revisions_table.c.version_number.desc())
            )
            return [self._revision(row._mapping) for row in rows]

    def active_assignments_for_model(self, model_id: str) -> list[dict[str, Any]]:
        self._ensure_initialized()
        statement = (
            select(
                active_model_assignments_table.c.deployment_id,
                active_model_assignments_table.c.revision_id,
                active_model_assignments_table.c.role,
                deployments_table.c.name.label("deployment_name"),
                deployments_table.c.slug.label("deployment_slug"),
                deployments_table.c.status.label("deployment_status"),
                deployments_table.c.endpoint_url,
                deployment_revisions_table.c.version_number.label("revision_version"),
            )
            .join(deployments_table, deployments_table.c.id == active_model_assignments_table.c.deployment_id)
            .join(deployment_revisions_table, deployment_revisions_table.c.id == active_model_assignments_table.c.revision_id)
            .where(active_model_assignments_table.c.model_id == model_id)
        )
        with self.engine.begin() as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]

    def clear_active_assignments(self, deployment_id: str) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                active_model_assignments_table.delete().where(
                    active_model_assignments_table.c.deployment_id == deployment_id
                )
            )

    def restore_active_assignments(self, deployment: Deployment, revision: DeploymentRevision) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            self._replace_active_assignments(connection, deployment.id, revision)

    def set_deployment_status(self, deployment: Deployment, revision: DeploymentRevision) -> Deployment:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            if deployment.status in {DeploymentStatus.STOPPED, DeploymentStatus.ARCHIVED}:
                connection.execute(
                    active_model_assignments_table.delete().where(
                        active_model_assignments_table.c.deployment_id == deployment.id
                    )
                )
            else:
                self._replace_active_assignments(connection, deployment.id, revision)
            connection.execute(
                deployments_table.update().where(deployments_table.c.id == deployment.id).values(
                    status=deployment.status.value,
                    updated_by=deployment.updated_by,
                    updated_at=deployment.updated_at,
                )
            )
        return deployment

    @staticmethod
    def _replace_active_assignments(connection, deployment_id: str, revision: DeploymentRevision) -> None:
        connection.execute(
            active_model_assignments_table.delete().where(
                active_model_assignments_table.c.deployment_id == deployment_id
            )
        )
        if revision.assignments:
            connection.execute(active_model_assignments_table.insert(), [
                {
                    "deployment_id": deployment_id,
                    "revision_id": revision.id,
                    "model_id": assignment.model_id,
                    "role": assignment.role.value,
                }
                for assignment in revision.assignments
            ])

    def add_inference(self, inference: InferenceRequest) -> InferenceRequest:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(inference_requests_table.insert().values(**self._inference_record(inference)))
        return inference

    def get_inference(self, request_id: str) -> InferenceRequest | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(inference_requests_table).where(inference_requests_table.c.id == request_id)
            ).first()
        return self._inference(row._mapping) if row else None

    def find_idempotent(self, deployment_id: str, requested_by: str, key: str) -> InferenceRequest | None:
        if not key:
            return None
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(select(inference_requests_table).where(
                inference_requests_table.c.deployment_id == deployment_id,
                inference_requests_table.c.requested_by == requested_by,
                inference_requests_table.c.idempotency_key == key,
            )).first()
        return self._inference(row._mapping) if row else None

    def complete_inference(self, inference: InferenceRequest, items: list[dict[str, Any]]) -> InferenceRequest:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            result = connection.execute(
                inference_requests_table.update().where(inference_requests_table.c.id == inference.id)
                .values(**self._inference_record(inference))
            )
            if result.rowcount != 1:
                raise LookupError("Inference request no longer exists")
            if items:
                connection.execute(inference_items_table.insert(), items)
        return inference

    def list_inference(
        self,
        deployment_id: str,
        limit: int,
        cursor: tuple[datetime, str] | None,
        record_id: str | None = None,
    ) -> list[InferenceRequest]:
        self._ensure_initialized()
        statement = select(inference_requests_table).where(
            inference_requests_table.c.deployment_id == deployment_id
        )
        if cursor:
            created_at, request_id = cursor
            statement = statement.where(or_(
                inference_requests_table.c.created_at < created_at,
                and_(inference_requests_table.c.created_at == created_at, inference_requests_table.c.id < request_id),
            ))
        if record_id:
            statement = statement.where(inference_requests_table.c.id.in_(
                select(inference_items_table.c.request_id).where(
                    inference_items_table.c.deployment_id == deployment_id,
                    inference_items_table.c.record_id == record_id,
                )
            ))
        statement = statement.order_by(
            inference_requests_table.c.created_at.desc(), inference_requests_table.c.id.desc()
        ).limit(limit)
        with self.engine.begin() as connection:
            return [self._inference(row._mapping) for row in connection.execute(statement)]

    def inference_items(self, request_id: str) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(inference_items_table).where(inference_items_table.c.request_id == request_id)
                .order_by(inference_items_table.c.role.asc(), inference_items_table.c.record_id.asc())
            )
            return [dict(row._mapping) for row in rows]

    def prune_expired(self, deployment_id: str, cutoff: datetime) -> int:
        self._ensure_initialized()
        expired_ids = select(inference_requests_table.c.id).where(
            inference_requests_table.c.deployment_id == deployment_id,
            inference_requests_table.c.created_at < cutoff,
        )
        with self.engine.begin() as connection:
            connection.execute(
                inference_items_table.delete().where(inference_items_table.c.request_id.in_(expired_ids))
            )
            result = connection.execute(
                inference_requests_table.delete().where(
                    inference_requests_table.c.deployment_id == deployment_id,
                    inference_requests_table.c.created_at < cutoff,
                )
            )
        return int(result.rowcount or 0)

    def add_replay(self, job: ChallengerReplayJob) -> ChallengerReplayJob:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(challenger_replay_jobs_table.insert().values(**self._replay_record(job)))
        return job

    def get_replay(self, job_id: str) -> ChallengerReplayJob | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(challenger_replay_jobs_table).where(challenger_replay_jobs_table.c.id == job_id)
            ).first()
        return self._replay(row._mapping) if row else None

    def update_replay(self, job: ChallengerReplayJob) -> ChallengerReplayJob:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                challenger_replay_jobs_table.update().where(challenger_replay_jobs_table.c.id == job.id)
                .values(**self._replay_record(job))
            )
        return job

    def list_replays(self, deployment_id: str) -> list[ChallengerReplayJob]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(challenger_replay_jobs_table)
                .where(challenger_replay_jobs_table.c.deployment_id == deployment_id)
                .order_by(challenger_replay_jobs_table.c.created_at.desc()).limit(100)
            )
            return [self._replay(row._mapping) for row in rows]

    def replay_sources(self, job: ChallengerReplayJob) -> list[InferenceRequest]:
        self._ensure_initialized()
        statement = select(inference_requests_table).where(
            inference_requests_table.c.deployment_id == job.deployment_id,
            inference_requests_table.c.status == InferenceStatus.SUCCEEDED.value,
            inference_requests_table.c.served_role.in_([DeploymentRole.CHAMPION.value, DeploymentRole.FALLBACK.value]),
            inference_requests_table.c.created_at < job.source_before,
        )
        if job.source_since:
            statement = statement.where(inference_requests_table.c.created_at >= job.source_since)
        if job.source_until:
            statement = statement.where(inference_requests_table.c.created_at < job.source_until)
        statement = statement.order_by(inference_requests_table.c.created_at.asc()).limit(job.max_requests)
        with self.engine.begin() as connection:
            return [self._inference(row._mapping) for row in connection.execute(statement)]

    def add_monitoring_run(self, run: OnlineMonitoringRun) -> OnlineMonitoringRun:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(monitoring_runs_table.insert().values(**self._monitoring_record(run)))
        return run

    def get_monitoring_run(self, run_id: str) -> OnlineMonitoringRun | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(monitoring_runs_table).where(monitoring_runs_table.c.id == run_id)
            ).first()
        return self._monitoring_run(row._mapping) if row else None

    def update_monitoring_run(self, run: OnlineMonitoringRun) -> OnlineMonitoringRun:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            result = connection.execute(
                monitoring_runs_table.update().where(monitoring_runs_table.c.id == run.id)
                .values(**self._monitoring_record(run))
            )
            if result.rowcount != 1:
                raise LookupError("Online monitoring run no longer exists")
        return run

    def list_monitoring_runs(
        self,
        deployment_id: str | None = None,
        limit: int = 200,
    ) -> list[OnlineMonitoringRun]:
        self._ensure_initialized()
        statement = select(monitoring_runs_table)
        if deployment_id:
            statement = statement.where(monitoring_runs_table.c.deployment_id == deployment_id)
        statement = statement.order_by(
            monitoring_runs_table.c.created_at.desc(), monitoring_runs_table.c.id.desc()
        ).limit(limit)
        with self.engine.begin() as connection:
            return [self._monitoring_run(row._mapping) for row in connection.execute(statement)]

    def iter_monitoring_items(
        self,
        deployment_id: str,
        since: datetime,
        until: datetime,
        source_before: datetime,
    ) -> Iterator[dict[str, Any]]:
        """Stream the full public-endpoint execution cohort with bounded memory."""
        self._ensure_initialized()
        statement = (
            select(
                inference_items_table.c.id.label("prediction_id"),
                inference_items_table.c.request_id,
                inference_items_table.c.record_id,
                inference_items_table.c.model_id,
                inference_items_table.c.role,
                inference_items_table.c.input,
                inference_items_table.c.output,
                inference_items_table.c.status,
                inference_items_table.c.error_message,
                inference_items_table.c.latency_ms.label("execution_latency_ms"),
                inference_requests_table.c.deployment_revision_id,
                inference_requests_table.c.served_model_id,
                inference_requests_table.c.served_role,
                inference_requests_table.c.fallback_used,
                inference_requests_table.c.created_at.label("scored_at"),
                inference_requests_table.c.completed_at,
                inference_requests_table.c.status.label("request_status"),
                inference_requests_table.c.latency_ms.label("request_latency_ms"),
            )
            .join(
                inference_requests_table,
                inference_requests_table.c.id == inference_items_table.c.request_id,
            )
            .where(
                inference_requests_table.c.deployment_id == deployment_id,
                inference_requests_table.c.requested_role == DeploymentRole.CHAMPION.value,
                inference_requests_table.c.created_at >= since,
                inference_requests_table.c.created_at < until,
                inference_requests_table.c.created_at < source_before,
            )
            .order_by(
                inference_requests_table.c.created_at.asc(),
                inference_requests_table.c.id.asc(),
                inference_items_table.c.id.asc(),
            )
            .execution_options(stream_results=True, yield_per=1000)
        )
        with self.engine.connect() as connection:
            result = connection.execute(statement)
            while True:
                rows = result.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    value = dict(row._mapping)
                    value["input"] = dict(value.get("input") or {})
                    value["output"] = dict(value.get("output") or {})
                    value["served"] = (
                        value["status"] == "succeeded"
                        and value["model_id"] == value["served_model_id"]
                        and value["role"] == value["served_role"]
                    )
                    yield value

    def monitoring_request_stats(
        self,
        deployment_id: str,
        since: datetime,
        until: datetime,
        source_before: datetime,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        filters = (
            inference_requests_table.c.deployment_id == deployment_id,
            inference_requests_table.c.requested_role == DeploymentRole.CHAMPION.value,
            inference_requests_table.c.created_at >= since,
            inference_requests_table.c.created_at < until,
            inference_requests_table.c.created_at < source_before,
        )
        statement = select(
            func.count().label("request_count"),
            func.coalesce(func.sum(inference_requests_table.c.record_count), 0).label("record_count"),
            func.coalesce(func.sum(case((inference_requests_table.c.status == InferenceStatus.SUCCEEDED.value, 1), else_=0)), 0).label("succeeded_request_count"),
            func.coalesce(func.sum(case((inference_requests_table.c.status == InferenceStatus.FAILED.value, 1), else_=0)), 0).label("failed_request_count"),
            func.coalesce(func.sum(case((inference_requests_table.c.fallback_used.is_(True), 1), else_=0)), 0).label("fallback_request_count"),
            func.avg(inference_requests_table.c.latency_ms).label("average_latency_ms"),
            func.max(inference_requests_table.c.latency_ms).label("maximum_latency_ms"),
        ).where(*filters)
        with self.engine.begin() as connection:
            row = dict(connection.execute(statement).one()._mapping)
            if connection.dialect.name == "postgresql":
                latency = connection.execute(select(
                    func.percentile_cont(0.50).within_group(inference_requests_table.c.latency_ms),
                    func.percentile_cont(0.95).within_group(inference_requests_table.c.latency_ms),
                    func.percentile_cont(0.99).within_group(inference_requests_table.c.latency_ms),
                ).where(*filters, inference_requests_table.c.latency_ms.is_not(None))).one()
                row.update({
                    "p50_latency_ms": latency[0],
                    "p95_latency_ms": latency[1],
                    "p99_latency_ms": latency[2],
                })
            else:
                row.update({"p50_latency_ms": None, "p95_latency_ms": None, "p99_latency_ms": None})
            errors = connection.execute(
                select(inference_requests_table.c.error_code, func.count().label("count"))
                .where(*filters, inference_requests_table.c.error_code != "")
                .group_by(inference_requests_table.c.error_code)
                .order_by(func.count().desc())
                .limit(20)
            )
            row["error_codes"] = [
                {"code": str(item.error_code), "count": int(item.count)} for item in errors
            ]
        return {
            key: (float(value) if key.endswith("latency_ms") and value is not None else int(value or 0) if key.endswith("count") else value)
            for key, value in row.items()
        }

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SERVING_SCHEMA}"))
            metadata.create_all(connection)
        self._initialized = True

    @staticmethod
    def _deployment_record(value: Deployment) -> dict[str, Any]:
        data = dict(value.__dict__)
        data["status"] = value.status.value
        return data

    @staticmethod
    def _deployment(record: Any) -> Deployment:
        data = dict(record)
        data["status"] = DeploymentStatus(data["status"])
        return Deployment(**data)

    @staticmethod
    def _revision_record(value: DeploymentRevision) -> dict[str, Any]:
        return {
            **value.__dict__,
            "assignments": [{"model_id": item.model_id, "role": item.role.value} for item in value.assignments],
        }

    @staticmethod
    def _revision(record: Any) -> DeploymentRevision:
        data = dict(record)
        data["assignments"] = [
            ModelAssignment(model_id=item["model_id"], role=DeploymentRole(item["role"]))
            for item in data["assignments"]
        ]
        return DeploymentRevision(**data)

    @staticmethod
    def _inference_record(value: InferenceRequest) -> dict[str, Any]:
        data = dict(value.__dict__)
        data["status"] = value.status.value
        return data

    @staticmethod
    def _inference(record: Any) -> InferenceRequest:
        data = dict(record)
        data["status"] = InferenceStatus(data["status"])
        data["request_payload"] = dict(data["request_payload"] or {})
        data["response_payload"] = dict(data["response_payload"] or {})
        data["warnings"] = list(data["warnings"] or [])
        return InferenceRequest(**data)

    @staticmethod
    def _replay_record(value: ChallengerReplayJob) -> dict[str, Any]:
        data = dict(value.__dict__)
        data["status"] = value.status.value
        return data

    @staticmethod
    def _replay(record: Any) -> ChallengerReplayJob:
        data = dict(record)
        data["status"] = ReplayStatus(data["status"])
        return ChallengerReplayJob(**data)

    @staticmethod
    def _monitoring_record(value: OnlineMonitoringRun) -> dict[str, Any]:
        data = dict(value.__dict__)
        data["status"] = value.status.value
        return data

    @staticmethod
    def _monitoring_run(record: Any) -> OnlineMonitoringRun:
        data = dict(record)
        data["status"] = MonitoringRunStatus(data["status"])
        data["report"] = dict(data.get("report") or {})
        data["warnings"] = list(data.get("warnings") or [])
        return OnlineMonitoringRun(**data)


# Backwards-compatible name for tests that explicitly inject a repository.
InMemoryServingRepository = PostgresServingRepository
