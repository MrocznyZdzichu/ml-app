from __future__ import annotations

import base64
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.security import Principal
from app.modules.models.domain import ModelStage
from app.modules.models.service import ModelService
from app.modules.pipelines.feature_engineering import DuckDbFeatureEngineeringEngine
from app.modules.serving.domain import (
    Deployment,
    ChallengerReplayJob,
    DeploymentRevision,
    DeploymentRole,
    DeploymentStatus,
    InferenceRequest,
    InferenceStatus,
    ModelAssignment,
    ReplayStatus,
)
from app.modules.serving.repository import PostgresServingRepository, ServingRepository
from app.modules.serving.runtime import (
    HttpModelRuntimeGateway,
    RuntimeGateway,
    RuntimeInputError,
    RuntimeUnavailableError,
)
from app.modules.serving.schemas import (
    DeploymentCreate,
    ChallengerReplayCreate,
    DeploymentRevisionCreate,
    DeploymentRevisionRead,
    InferencePage,
    InferenceDetail,
    InferenceExecutionItem,
    InferenceRequestRead,
    PredictionRead,
    ScoreRecord,
    ScoreResponse,
)
from app.modules.sharing.domain import AuditEvent, BC_ROLE_RANK, BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy
from app.modules.sharing.repository import PostgresSharingRepository


logger = logging.getLogger("mlapp.serving")


class ServingService:
    def __init__(
        self,
        repository: ServingRepository | None = None,
        runtime: RuntimeGateway | None = None,
        models: ModelService | None = None,
    ) -> None:
        self.repository = repository or PostgresServingRepository()
        self.runtime = runtime or HttpModelRuntimeGateway()
        self.models = models or ModelService()

    def create_deployment(self, payload: DeploymentCreate, principal: Principal) -> Deployment:
        champion = self.models.get_model(payload.model_id, principal)
        if not champion.business_case_id:
            raise HTTPException(status_code=409, detail="Online serving requires a Business Case model")
        access_policy.require_business_case(
            principal, champion.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        self._require_stage(champion.stage, DeploymentRole.CHAMPION)
        now = datetime.now(timezone.utc)
        deployment_id = str(uuid4())
        revision_id = str(uuid4())
        slug = self._unique_slug(payload.name)
        deployment = Deployment(
            id=deployment_id,
            owner_id=champion.owner_id,
            business_case_id=champion.business_case_id,
            name=payload.name.strip(),
            slug=slug,
            status=DeploymentStatus.RUNNING,
            active_revision_id=revision_id,
            endpoint_url=f"/api/v1/serving/deployments/{slug}/predictions",
            retention_days=payload.retention_days,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        revision = DeploymentRevision(
            id=revision_id,
            deployment_id=deployment_id,
            version_number=1,
            assignments=[ModelAssignment(model_id=champion.id, role=DeploymentRole.CHAMPION)],
            created_by=principal.user_id,
            reason="Initial champion",
            created_at=now,
        )
        try:
            self.repository.add_deployment(deployment, revision)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Deployment name or endpoint already exists") from exc
        self._audit(principal, "serving.deployment_created", deployment, {}, {
            "name": deployment.name,
            "active_revision_id": revision.id,
            "champion_model_id": champion.id,
        })
        return deployment

    def list_deployments(self, principal: Principal) -> list[Deployment]:
        return [
            deployment for deployment in self.repository.list_all_deployments()
            if self._can_read(principal, deployment.business_case_id)
        ]

    def get_deployment(self, deployment_id_or_slug: str, principal: Principal) -> Deployment:
        deployment = self.repository.get_deployment(deployment_id_or_slug)
        if not deployment:
            raise HTTPException(status_code=404, detail="Deployment not found")
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.READER
        )
        return deployment

    def get_active_revision(self, deployment: Deployment) -> DeploymentRevision:
        revision = self.repository.get_revision(deployment.active_revision_id)
        if revision is None or revision.deployment_id != deployment.id:
            raise HTTPException(status_code=503, detail="Deployment has no valid active revision")
        return revision

    def list_revisions(self, deployment_id: str, principal: Principal) -> list[DeploymentRevision]:
        deployment = self.get_deployment(deployment_id, principal)
        return self.repository.list_revisions(deployment.id)

    def create_revision(
        self,
        deployment_id: str,
        payload: DeploymentRevisionCreate,
        principal: Principal,
    ) -> DeploymentRevision:
        deployment = self.get_deployment(deployment_id, principal)
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        assignments = [ModelAssignment(model_id=item.model_id, role=item.role) for item in payload.assignments]
        self._validate_assignments(assignments, deployment.business_case_id, principal)
        revisions = self.repository.list_revisions(deployment.id)
        revision = DeploymentRevision(
            id=str(uuid4()),
            deployment_id=deployment.id,
            version_number=max((item.version_number for item in revisions), default=0) + 1,
            assignments=assignments,
            created_by=principal.user_id,
            reason=payload.reason,
        )
        previous_revision_id = deployment.active_revision_id
        deployment.active_revision_id = revision.id
        deployment.updated_by = principal.user_id
        deployment.updated_at = revision.created_at
        deployment.status = DeploymentStatus.RUNNING
        try:
            self.repository.add_revision(revision, deployment)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Concurrent deployment revision conflict; retry") from exc
        self._audit(principal, "serving.revision_activated", deployment, {
            "active_revision_id": previous_revision_id,
        }, {
            "active_revision_id": revision.id,
            "version_number": revision.version_number,
            "assignments": [
                {"model_id": item.model_id, "role": item.role.value} for item in assignments
            ],
        })
        return revision

    def score(
        self,
        deployment_id_or_slug: str,
        instances: list[ScoreRecord],
        principal: Principal,
        *,
        correlation_id: str = "",
        idempotency_key: str = "",
        challenger_model_id: str = "",
        _revision_id: str = "",
    ) -> ScoreResponse:
        deployment = self.get_deployment(deployment_id_or_slug, principal)
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        if deployment.status not in {DeploymentStatus.RUNNING, DeploymentStatus.DEGRADED}:
            raise HTTPException(status_code=503, detail=f"Deployment is {deployment.status.value}")
        revision = self.repository.get_revision(_revision_id) if _revision_id else self.get_active_revision(deployment)
        if revision is None or revision.deployment_id != deployment.id:
            raise HTTPException(status_code=409, detail="Pinned deployment revision is unavailable")
        assignments = {item.role: item for item in revision.assignments}
        primary_role = DeploymentRole.CHALLENGER if challenger_model_id else DeploymentRole.CHAMPION
        if challenger_model_id:
            challenger = next((item for item in revision.assignments if item.role == DeploymentRole.CHALLENGER and item.model_id == challenger_model_id), None)
            if challenger is None:
                raise HTTPException(status_code=404, detail="Challenger is not assigned to the active revision")
            primary = challenger
        else:
            primary = assignments[DeploymentRole.CHAMPION]

        existing = self.repository.find_idempotent(deployment.id, principal.user_id, idempotency_key)
        if existing is not None:
            if existing.status == InferenceStatus.SUCCEEDED:
                return ScoreResponse.model_validate(existing.response_payload)
            raise HTTPException(status_code=409, detail=f"Idempotency key belongs to request {existing.id} with status {existing.status.value}")

        request_id = str(uuid4())
        normalized, warnings = self._normalize_instances(instances)
        inference = InferenceRequest(
            id=request_id,
            deployment_id=deployment.id,
            deployment_revision_id=revision.id,
            requested_by=principal.user_id,
            correlation_id=(correlation_id.strip() or request_id)[:128],
            idempotency_key=idempotency_key.strip()[:255],
            status=InferenceStatus.ACCEPTED,
            record_count=len(normalized),
            request_payload={"instances": normalized},
            warnings=warnings,
            champion_model_id=assignments[DeploymentRole.CHAMPION].model_id,
        )
        try:
            self.repository.add_inference(inference)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Inference audit storage is unavailable") from exc

        started = time.monotonic()
        execution_items: list[dict[str, Any]] = []
        fallback_used = False
        served = primary
        try:
            primary_outputs = self._execute(primary, normalized, principal, request_id)
        except RuntimeInputError as input_error:
            self._fail_inference(inference, "invalid_input", str(input_error), started)
            raise HTTPException(status_code=422, detail=str(input_error)) from input_error
        except RuntimeUnavailableError as primary_error:
            fallback = assignments.get(DeploymentRole.FALLBACK) if not challenger_model_id else None
            if fallback is None:
                self._fail_inference(inference, "runtime_unavailable", str(primary_error), started)
                raise HTTPException(status_code=503, detail="Champion model runtime is unavailable") from primary_error
            served = fallback
            fallback_used = True
            warnings.append(f"Champion failed technically; fallback {fallback.model_id} served the request")
            try:
                primary_outputs = self._execute(fallback, normalized, principal, request_id)
            except RuntimeInputError as input_error:
                self._fail_inference(inference, "invalid_input", str(input_error), started)
                raise HTTPException(status_code=422, detail=str(input_error)) from input_error
            except RuntimeUnavailableError as fallback_error:
                self._fail_inference(inference, "fallback_unavailable", str(fallback_error), started)
                raise HTTPException(status_code=503, detail="Champion and fallback runtimes are unavailable") from fallback_error

        execution_items.extend(self._item_rows(inference, normalized, primary_outputs, served))
        if not challenger_model_id:
            for shadow in (item for item in revision.assignments if item.role == DeploymentRole.SHADOW):
                try:
                    shadow_outputs = self._execute(shadow, normalized, principal, request_id)
                    execution_items.extend(self._item_rows(inference, normalized, shadow_outputs, shadow))
                except (RuntimeUnavailableError, RuntimeInputError) as exc:
                    warnings.append(f"Shadow model {shadow.model_id} failed: {exc}")

        predictions = [
            PredictionRead(
                record_id=item["record_id"],
                prediction=output.get("prediction"),
                outputs={key: value for key, value in output.items() if key != "prediction"},
            )
            for item, output in zip(normalized, primary_outputs, strict=True)
        ]
        response = ScoreResponse(
            request_id=inference.id,
            correlation_id=inference.correlation_id,
            deployment_id=deployment.id,
            deployment_revision_id=revision.id,
            model_id=served.model_id,
            served_role=served.role if fallback_used else primary_role,
            fallback_used=fallback_used,
            predictions=predictions,
            warnings=warnings,
        )
        inference.status = InferenceStatus.SUCCEEDED
        inference.response_payload = response.model_dump(mode="json")
        inference.warnings = warnings
        inference.served_model_id = served.model_id
        inference.served_role = response.served_role.value
        inference.fallback_used = fallback_used
        inference.latency_ms = round((time.monotonic() - started) * 1000)
        inference.completed_at = datetime.now(timezone.utc)
        try:
            self.repository.complete_inference(inference, execution_items)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Prediction completed but its audit history could not be persisted") from exc
        try:
            self.repository.prune_expired(
                deployment.id,
                datetime.now(timezone.utc) - timedelta(days=deployment.retention_days),
            )
        except Exception:
            logger.exception("Inference retention cleanup failed deployment_id=%s", deployment.id)
        return response

    def inference_history(
        self,
        deployment_id: str,
        principal: Principal,
        *,
        limit: int = 50,
        cursor: str = "",
        record_id: str = "",
    ) -> InferencePage:
        deployment = self.get_deployment(deployment_id, principal)
        parsed_cursor = self._decode_cursor(cursor) if cursor else None
        rows = self.repository.list_inference(deployment.id, limit + 1, parsed_cursor, record_id or None)
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = self._encode_cursor(page[-1]) if has_more and page else None
        return InferencePage(
            items=[InferenceRequestRead.model_validate(item) for item in page],
            next_cursor=next_cursor,
        )

    def inference_detail(
        self,
        deployment_id: str,
        request_id: str,
        principal: Principal,
    ) -> InferenceDetail:
        deployment = self.get_deployment(deployment_id, principal)
        inference = self.repository.get_inference(request_id)
        if inference is None or inference.deployment_id != deployment.id:
            raise HTTPException(status_code=404, detail="Inference request not found")
        return InferenceDetail(
            request=InferenceRequestRead.model_validate(inference),
            executions=[InferenceExecutionItem.model_validate(item) for item in self.repository.inference_items(request_id)],
        )

    def create_replay(
        self,
        deployment_id: str,
        payload: ChallengerReplayCreate,
        principal: Principal,
    ) -> ChallengerReplayJob:
        deployment = self.get_deployment(deployment_id, principal)
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        revision = self.get_active_revision(deployment)
        assigned = any(
            item.role == DeploymentRole.CHALLENGER and item.model_id == payload.challenger_model_id
            for item in revision.assignments
        )
        if not assigned:
            raise HTTPException(status_code=409, detail="Replay model must be a challenger in the active revision")
        now = datetime.now(timezone.utc)
        job = ChallengerReplayJob(
            id=str(uuid4()), deployment_id=deployment.id,
            deployment_revision_id=revision.id,
            challenger_model_id=payload.challenger_model_id,
            requested_by=principal.user_id, status=ReplayStatus.QUEUED,
            source_before=now, source_since=payload.since, source_until=payload.until,
            max_requests=payload.max_requests, created_at=now,
        )
        self.repository.add_replay(job)
        self._audit(principal, "serving.challenger_replay_queued", deployment, {}, {
            "job_id": job.id, "challenger_model_id": job.challenger_model_id,
            "deployment_revision_id": revision.id, "max_requests": job.max_requests,
        })
        from app.worker.tasks import replay_challenger
        replay_challenger.delay(job.id)
        return job

    def list_replays(self, deployment_id: str, principal: Principal) -> list[ChallengerReplayJob]:
        deployment = self.get_deployment(deployment_id, principal)
        return self.repository.list_replays(deployment.id)

    def run_replay(self, job_id: str) -> ChallengerReplayJob:
        from app.modules.auth.repository import PostgresUserRepository

        job = self.repository.get_replay(job_id)
        if job is None:
            raise ValueError("Challenger replay job not found")
        if job.status == ReplayStatus.SUCCEEDED:
            return job
        account = PostgresUserRepository().get(job.requested_by)
        if account is None or not account.is_active:
            job.status = ReplayStatus.FAILED
            job.error_message = "Replay requester is no longer active"
            job.completed_at = datetime.now(timezone.utc)
            return self.repository.update_replay(job)
        principal = Principal(
            user_id=account.id, email=account.email, display_name=account.display_name,
            login_name=account.login_name, roles=account.roles, session_version=account.session_version,
        )
        deployment = self.get_deployment(job.deployment_id, principal)
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        job.status = ReplayStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self.repository.update_replay(job)
        sources = self.repository.replay_sources(job)
        try:
            for index, source in enumerate(sources, start=1):
                try:
                    instances = [ScoreRecord.model_validate(item) for item in source.request_payload.get("instances", [])]
                    self.score(
                        deployment.id, instances, principal,
                        challenger_model_id=job.challenger_model_id,
                        correlation_id=f"replay:{job.id}:{source.id}",
                        idempotency_key=f"replay:{job.id}:{source.id}",
                        _revision_id=job.deployment_revision_id,
                    )
                    job.processed_requests += 1
                    job.processed_records += len(instances)
                except Exception:
                    job.failed_requests += 1
                    if not job.error_message:
                        job.error_message = f"Replay request {source.id} failed; inspect its inference log entry"
                if index % 25 == 0:
                    self.repository.update_replay(job)
            job.status = (
                ReplayStatus.FAILED
                if sources and job.processed_requests == 0 and job.failed_requests > 0
                else ReplayStatus.SUCCEEDED
            )
        except Exception as exc:
            job.status = ReplayStatus.FAILED
            job.error_message = str(exc)[:4000]
        job.completed_at = datetime.now(timezone.utc)
        return self.repository.update_replay(job)

    def _execute(
        self,
        assignment: ModelAssignment,
        instances: list[dict[str, Any]],
        principal: Principal,
        request_id: str,
    ) -> list[dict[str, Any]]:
        try:
            model = self.models.get_model(assignment.model_id, principal)
        except Exception as exc:
            raise RuntimeUnavailableError(
                f"Pinned model {assignment.model_id} is unavailable"
            ) from exc
        records = [dict(item["features"]) for item in instances]
        if model.fitted_transform_artifact_id:
            if not model.feature_engineering_definition:
                raise RuntimeInputError(
                    "Model registry is missing the feature recipe required by its pinned fitted transform"
                )
            try:
                records = DuckDbFeatureEngineeringEngine().transform_online_records(
                    definition=model.feature_engineering_definition,
                    fitted_state_artifact_id=model.fitted_transform_artifact_id,
                    owner_id=model.owner_id,
                    records=records,
                    output_columns=model.feature_columns,
                )
            except ValueError as exc:
                raise RuntimeInputError(f"Pinned feature transform rejected scoring input: {exc}") from exc
            except Exception as exc:
                logger.exception("Pinned feature transform failed request_id=%s model_id=%s", request_id, model.id)
                raise RuntimeUnavailableError("Pinned feature transform execution failed") from exc
        return self.runtime.score(
            model_artifact_uri=model.artifact_uri,
            model_hash=model.model_hash,
            records=records,
            request_id=request_id,
        )

    def _validate_assignments(
        self,
        assignments: list[ModelAssignment],
        business_case_id: str,
        principal: Principal,
    ) -> None:
        models = []
        for assignment in assignments:
            model = self.models.get_model(assignment.model_id, principal)
            if model.business_case_id != business_case_id:
                raise HTTPException(status_code=409, detail="Every assigned model must belong to the deployment Business Case")
            self._require_stage(model.stage, assignment.role)
            models.append(model)
        champion = models[[item.role for item in assignments].index(DeploymentRole.CHAMPION)]
        expected = (champion.problem_type, tuple(champion.feature_columns))
        incompatible = [model.id for model in models if (model.problem_type, tuple(model.feature_columns)) != expected]
        if incompatible:
            raise HTTPException(status_code=409, detail=f"Models have incompatible inference contracts: {', '.join(incompatible)}")

    @staticmethod
    def _require_stage(stage: ModelStage, role: DeploymentRole) -> None:
        allowed = {ModelStage.PRODUCTION} if role in {DeploymentRole.CHAMPION, DeploymentRole.FALLBACK} else {ModelStage.STAGING, ModelStage.PRODUCTION}
        if stage not in allowed:
            raise HTTPException(status_code=409, detail=f"Model stage {stage.value} cannot be assigned as {role.value}")

    @staticmethod
    def _normalize_instances(instances: list[ScoreRecord]) -> tuple[list[dict[str, Any]], list[str]]:
        missing = 0
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in instances:
            record_id = (item.record_id or "").strip()
            if not record_id:
                missing += 1
                record_id = f"generated-{uuid4()}"
            if record_id in seen:
                raise HTTPException(status_code=422, detail=f"Duplicate record_id in request: {record_id}")
            seen.add(record_id)
            normalized.append({"record_id": record_id, "features": dict(item.features)})
        warnings = []
        if missing:
            warnings.append(
                f"{missing} record(s) had no stable record_id; future effectiveness monitoring cannot reliably join actuals"
            )
        return normalized, warnings

    @staticmethod
    def _item_rows(
        inference: InferenceRequest,
        instances: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        assignment: ModelAssignment,
    ) -> list[dict[str, Any]]:
        return [{
            "id": f"{inference.id}:{assignment.model_id}:{index}",
            "request_id": inference.id,
            "deployment_id": inference.deployment_id,
            "record_id": instance["record_id"],
            "model_id": assignment.model_id,
            "role": assignment.role.value,
            "input": instance["features"],
            "output": output,
            "created_at": inference.created_at,
        } for index, (instance, output) in enumerate(zip(instances, outputs, strict=True))]

    def _fail_inference(self, inference: InferenceRequest, code: str, message: str, started: float) -> None:
        inference.status = InferenceStatus.FAILED
        inference.error_code = code
        inference.error_message = message[:4000]
        inference.latency_ms = round((time.monotonic() - started) * 1000)
        inference.completed_at = datetime.now(timezone.utc)
        try:
            self.repository.complete_inference(inference, [])
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Inference and audit storage are unavailable") from exc

    def _unique_slug(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "model-service"
        slug = base[:220]
        suffix = 1
        while self.repository.get_deployment(slug) is not None:
            suffix += 1
            slug = f"{base[:210]}-{suffix}"
        return slug

    @staticmethod
    def _encode_cursor(item: InferenceRequest) -> str:
        raw = f"{item.created_at.isoformat()}|{item.id}".encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8")
            created_at, request_id = raw.rsplit("|", 1)
            return datetime.fromisoformat(created_at), request_id
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid history cursor") from exc

    @staticmethod
    def _can_read(principal: Principal, business_case_id: str) -> bool:
        role = access_policy.business_case_role(principal, business_case_id)
        return role is not None and BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]

    @staticmethod
    def _audit(principal: Principal, action: str, deployment: Deployment, previous: dict[str, Any], new: dict[str, Any]) -> None:
        PostgresSharingRepository().add_audit(AuditEvent(
            id=str(uuid4()),
            actor_id=principal.user_id,
            action=action,
            subject_type="deployment",
            subject_id=deployment.id,
            resource_kind="business_case",
            resource_id=deployment.business_case_id,
            previous_state=previous,
            new_state=new,
        ))
