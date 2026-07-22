from __future__ import annotations

import base64
import hashlib
import json
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
    InferenceRequestSummaryRead,
    InferenceSummaryPage,
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

    def list_deployments(self, principal: Principal, *, include_archived: bool = False) -> list[Deployment]:
        return [
            deployment for deployment in self.repository.list_all_deployments()
            if self._can_read(principal, deployment.business_case_id)
            and (include_archived or deployment.status != DeploymentStatus.ARCHIVED)
        ]

    def list_model_family_usage(self, logical_id: str, principal: Principal) -> list[dict[str, Any]]:
        usage: list[dict[str, Any]] = []
        for version in self.models.list_versions(logical_id, principal):
            for assignment in self.repository.active_assignments_for_model(version.id):
                usage.append({"model_id": version.id, **assignment})
        return usage

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

    def input_contract(
        self,
        deployment_id: str,
        principal: Principal,
        *,
        challenger_model_id: str = "",
    ) -> dict[str, Any]:
        """Return a bounded UI contract derived from the pinned model metadata."""
        deployment = self.get_deployment(deployment_id, principal)
        revision = self.get_active_revision(deployment)
        if challenger_model_id:
            assignment = next((
                item for item in revision.assignments
                if item.role == DeploymentRole.CHALLENGER
                and item.model_id == challenger_model_id
            ), None)
            if assignment is None:
                raise HTTPException(status_code=404, detail="Challenger is not assigned to the active revision")
        else:
            assignment = next((
                item for item in revision.assignments
                if item.role == DeploymentRole.CHAMPION
            ), None)
            if assignment is None:
                raise HTTPException(status_code=503, detail="Deployment has no champion")
        model = self._model_for_inference(assignment.model_id, principal)
        fields = self._input_fields(model)
        return {
            "deployment_id": deployment.id,
            "deployment_revision_id": revision.id,
            "model_id": model.id,
            "role": assignment.role,
            "fields": fields,
            "example_features": {
                field["name"]: field["default_value"] for field in fields
            },
        }

    def deployment_model_options(
        self,
        deployment_id: str,
        principal: Principal,
    ) -> list[dict[str, Any]]:
        """Expose role eligibility and an opaque compatibility contract to UI clients."""
        deployment = self.get_deployment(deployment_id, principal)
        revision = self.get_active_revision(deployment)
        champion_assignment = next((
            item for item in revision.assignments if item.role == DeploymentRole.CHAMPION
        ), None)
        if champion_assignment is None:
            raise HTTPException(status_code=503, detail="Deployment has no champion")
        champion = self._model_for_inference(champion_assignment.model_id, principal)
        champion_signature = self._inference_contract_signature(champion)
        options = []
        candidate_loader = getattr(self.models, "list_serving_candidates", None)
        candidates = (
            candidate_loader(deployment.business_case_id, principal)
            if callable(candidate_loader)
            else self.models.list_models(principal)
        )
        for model in candidates:
            if (
                model.business_case_id != deployment.business_case_id
                or model.stage not in {ModelStage.STAGING, ModelStage.PRODUCTION}
            ):
                continue
            allowed_roles = [DeploymentRole.CHALLENGER, DeploymentRole.SHADOW]
            if model.stage == ModelStage.PRODUCTION:
                allowed_roles = [
                    DeploymentRole.CHAMPION,
                    DeploymentRole.CHALLENGER,
                    DeploymentRole.SHADOW,
                    DeploymentRole.FALLBACK,
                ]
            signature = self._inference_contract_signature(model)
            options.append({
                "model_id": model.id,
                "name": model.name,
                "version": model.version,
                "business_case_id": model.business_case_id,
                "stage": model.stage.value,
                "contract_signature": signature,
                "compatible_with_active_champion": signature == champion_signature,
                "allowed_roles": allowed_roles,
            })
        return options

    @classmethod
    def _inference_contract_signature(cls, model) -> str:
        canonical = json.dumps(
            cls._inference_contract(model),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _input_fields(self, model) -> list[dict[str, Any]]:
        feature_definition = model.feature_engineering_definition or {}
        raw_features = [
            str(value) for value in (
                feature_definition.get("feature_columns") or model.feature_columns
            )
        ]
        auto_fe = model.training_config.get("auto_feature_engineering") or {}
        decisions = {
            str(item.get("column")): item
            for item in auto_fe.get("column_decisions") or []
            if isinstance(item, dict) and item.get("column")
        }
        suggestions: dict[str, list[str]] = {}
        if model.fitted_transform_artifact_id:
            try:
                suggestions = DuckDbFeatureEngineeringEngine().categorical_suggestions(
                    fitted_state_artifact_id=model.fitted_transform_artifact_id,
                    owner_id=model.owner_id,
                    limit=5,
                )
            except (OSError, ValueError, json.JSONDecodeError):
                logger.warning(
                    "Could not load categorical suggestions model_id=%s fitted_state=%s",
                    model.id,
                    model.fitted_transform_artifact_id,
                )
        fields: list[dict[str, Any]] = []
        for name in raw_features:
            decision = decisions.get(name, {})
            raw_type = str(decision.get("type") or "").upper()
            profile = decision.get("numeric_profile") or {}
            if "BOOL" in raw_type:
                value_type, default = "boolean", False
            elif any(token in raw_type for token in ("INT", "HUGEINT", "UBIGINT")):
                mean = profile.get("mean")
                value_type = "integer"
                default = round(float(mean)) if isinstance(mean, (int, float)) else 0
            elif any(token in raw_type for token in ("DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC")):
                mean = profile.get("mean")
                value_type = "number"
                default = round(float(mean), 6) if isinstance(mean, (int, float)) else 0.0
            elif any(token in raw_type for token in ("DATE", "TIME")):
                value_type, default = "string", "2026-01-01"
            elif decision.get("role") == "categorical" or any(
                token in raw_type for token in ("CHAR", "TEXT", "STRING", "VARCHAR")
            ):
                options = suggestions.get(name, [])
                value_type = "string"
                default = options[0] if options else "example"
            else:
                # Estimator-ready legacy models are numeric unless their
                # persisted training contract says otherwise.
                value_type, default = "number", 0.0
            minimum = profile.get("min") if isinstance(profile.get("min"), (int, float)) else None
            maximum = profile.get("max") if isinstance(profile.get("max"), (int, float)) else None
            description_parts = [raw_type or "type not recorded"]
            if minimum is not None and maximum is not None:
                description_parts.append(f"observed range {minimum:g}–{maximum:g}")
            fields.append({
                "name": name,
                "value_type": value_type,
                "required": True,
                "default_value": default,
                "description": " · ".join(description_parts),
                "minimum": minimum,
                "maximum": maximum,
                "options": suggestions.get(name, []),
            })
        return fields

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
        if deployment.status == DeploymentStatus.ARCHIVED:
            raise HTTPException(status_code=409, detail="An archived deployment cannot be revised")
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

    def set_deployment_status(
        self,
        deployment_id: str,
        next_status: DeploymentStatus,
        reason: str,
        principal: Principal,
    ) -> Deployment:
        deployment = self.get_deployment(deployment_id, principal)
        access_policy.require_business_case(
            principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
        )
        if next_status not in {DeploymentStatus.RUNNING, DeploymentStatus.STOPPED, DeploymentStatus.ARCHIVED}:
            raise HTTPException(status_code=422, detail="Deployment may be started, stopped or archived only")
        previous_status = deployment.status
        if next_status == previous_status:
            return deployment
        if previous_status == DeploymentStatus.ARCHIVED:
            raise HTTPException(status_code=409, detail="An archived deployment cannot be restarted or changed")
        revision = self.get_active_revision(deployment)
        if next_status == DeploymentStatus.RUNNING:
            self._validate_assignments(revision.assignments, deployment.business_case_id, principal)
        deployment.status = next_status
        deployment.updated_by = principal.user_id
        deployment.updated_at = datetime.now(timezone.utc)
        self.repository.set_deployment_status(deployment, revision)
        self._audit(principal, "serving.deployment_status_changed", deployment, {
            "status": previous_status.value,
        }, {"status": next_status.value, "reason": reason})
        return deployment

    def rollback_deployment(
        self,
        deployment_id: str,
        revision_id: str,
        reason: str,
        principal: Principal,
    ) -> DeploymentRevision:
        deployment = self.get_deployment(deployment_id, principal)
        source = self.repository.get_revision(revision_id)
        if source is None or source.deployment_id != deployment.id:
            raise HTTPException(status_code=404, detail="Deployment revision not found")
        if source.id == deployment.active_revision_id:
            raise HTTPException(status_code=409, detail="The selected revision is already active")
        return self.create_revision(
            deployment.id,
            DeploymentRevisionCreate(
                assignments=[
                    {"model_id": item.model_id, "role": item.role}
                    for item in source.assignments
                ],
                reason=f"Rollback to v{source.version_number}: {reason}",
            ),
            principal,
        )

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
        resolved_models: dict[str, Any] = {}
        if not _revision_id:
            try:
                resolved_models = self._validate_assignments(
                    revision.assignments, deployment.business_case_id, principal
                )
            except HTTPException as exc:
                deployment.status = DeploymentStatus.DEGRADED
                deployment.updated_at = datetime.now(timezone.utc)
                self.repository.update_deployment(deployment)
                raise HTTPException(
                    status_code=503,
                    detail="Active deployment revision no longer satisfies model lifecycle or inference contract requirements",
                ) from exc
        assignments = {item.role: item for item in revision.assignments}
        primary_role = DeploymentRole.CHALLENGER if challenger_model_id else DeploymentRole.CHAMPION
        if challenger_model_id:
            challenger = next((item for item in revision.assignments if item.role == DeploymentRole.CHALLENGER and item.model_id == challenger_model_id), None)
            if challenger is None:
                raise HTTPException(status_code=404, detail="Challenger is not assigned to the active revision")
            primary = challenger
        else:
            primary = assignments[DeploymentRole.CHAMPION]

        normalized, warnings = self._normalize_instances(instances)
        normalized_key = idempotency_key.strip()[:255]
        request_hash = self._request_hash(
            revision.id,
            primary.model_id,
            primary_role,
            [
                {"record_id": item.record_id, "features": dict(item.features)}
                for item in instances
            ],
        )
        existing = self.repository.find_idempotent(deployment.id, principal.user_id, normalized_key)
        if existing is not None:
            if not existing.request_hash or existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different request, model, or deployment revision",
                )
            if existing.status == InferenceStatus.SUCCEEDED:
                return ScoreResponse.model_validate(existing.response_payload)
            raise HTTPException(status_code=409, detail=f"Idempotency key belongs to request {existing.id} with status {existing.status.value}")

        request_id = str(uuid4())
        inference = InferenceRequest(
            id=request_id,
            deployment_id=deployment.id,
            deployment_revision_id=revision.id,
            requested_by=principal.user_id,
            correlation_id=(correlation_id.strip() or request_id)[:128],
            idempotency_key=normalized_key,
            request_hash=request_hash,
            status=InferenceStatus.ACCEPTED,
            record_count=len(normalized),
            request_payload={"instances": normalized},
            warnings=warnings,
            champion_model_id=assignments[DeploymentRole.CHAMPION].model_id,
            requested_model_id=primary.model_id,
            requested_role=primary_role.value,
        )
        try:
            self.repository.add_inference(inference)
        except IntegrityError as exc:
            concurrent = self.repository.find_idempotent(
                deployment.id, principal.user_id, normalized_key
            )
            if concurrent is not None and concurrent.request_hash == request_hash:
                raise HTTPException(
                    status_code=409,
                    detail=f"Idempotent request {concurrent.id} is already {concurrent.status.value}; retry shortly",
                ) from exc
            raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Inference audit storage is unavailable") from exc

        started = time.monotonic()
        execution_items: list[dict[str, Any]] = []
        fallback_used = False
        served = primary
        primary_started = time.monotonic()
        try:
            primary_outputs = self._execute(
                primary,
                normalized,
                principal,
                request_id,
                resolved_model=resolved_models.get(primary.model_id),
            )
        except RuntimeInputError as input_error:
            execution_items.extend(self._failed_item_rows(
                inference, normalized, primary, str(input_error), primary_started
            ))
            self._fail_inference(inference, "invalid_input", str(input_error), started, execution_items)
            raise HTTPException(status_code=422, detail=str(input_error)) from input_error
        except RuntimeUnavailableError as primary_error:
            execution_items.extend(self._failed_item_rows(
                inference, normalized, primary, str(primary_error), primary_started
            ))
            fallback = assignments.get(DeploymentRole.FALLBACK) if not challenger_model_id else None
            if not challenger_model_id:
                self._set_runtime_status(
                    deployment, DeploymentStatus.DEGRADED, principal,
                    "Champion runtime became unavailable",
                )
            if fallback is None:
                self._fail_inference(inference, "runtime_unavailable", str(primary_error), started, execution_items)
                raise HTTPException(status_code=503, detail="Champion model runtime is unavailable") from primary_error
            served = fallback
            fallback_used = True
            warnings.append(f"Champion failed technically; fallback {fallback.model_id} served the request")
            fallback_started = time.monotonic()
            try:
                primary_outputs = self._execute(
                    fallback,
                    normalized,
                    principal,
                    request_id,
                    resolved_model=resolved_models.get(fallback.model_id),
                )
            except RuntimeInputError as input_error:
                execution_items.extend(self._failed_item_rows(
                    inference, normalized, fallback, str(input_error), fallback_started
                ))
                self._fail_inference(inference, "invalid_input", str(input_error), started, execution_items)
                raise HTTPException(status_code=422, detail=str(input_error)) from input_error
            except RuntimeUnavailableError as fallback_error:
                execution_items.extend(self._failed_item_rows(
                    inference, normalized, fallback, str(fallback_error), fallback_started
                ))
                self._fail_inference(inference, "fallback_unavailable", str(fallback_error), started, execution_items)
                raise HTTPException(status_code=503, detail="Champion and fallback runtimes are unavailable") from fallback_error

        successful_started = fallback_started if fallback_used else primary_started
        execution_items.extend(self._item_rows(
            inference, normalized, primary_outputs, served,
            round((time.monotonic() - successful_started) * 1000),
        ))
        if not challenger_model_id:
            for shadow in (item for item in revision.assignments if item.role == DeploymentRole.SHADOW):
                shadow_started = time.monotonic()
                try:
                    shadow_outputs = self._execute(
                        shadow,
                        normalized,
                        principal,
                        request_id,
                        resolved_model=resolved_models.get(shadow.model_id),
                    )
                    execution_items.extend(self._item_rows(
                        inference, normalized, shadow_outputs, shadow,
                        round((time.monotonic() - shadow_started) * 1000),
                    ))
                except (RuntimeUnavailableError, RuntimeInputError) as exc:
                    warnings.append(f"Shadow model {shadow.model_id} failed: {exc}")
                    execution_items.extend(self._failed_item_rows(
                        inference, normalized, shadow, str(exc), shadow_started
                    ))

        predictions = [
            PredictionRead(
                prediction_id=f"{inference.id}:{served.model_id}:{index}",
                record_id=item["record_id"],
                prediction=output.get("prediction"),
                outputs={key: value for key, value in output.items() if key != "prediction"},
            )
            for index, (item, output) in enumerate(zip(normalized, primary_outputs, strict=True))
        ]
        if (
            not challenger_model_id
            and not fallback_used
            and deployment.status == DeploymentStatus.DEGRADED
        ):
            self._set_runtime_status(
                deployment, DeploymentStatus.RUNNING, principal,
                "Champion runtime recovered during a successful request",
            )
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

    def inference_history_summary(
        self,
        deployment_id: str,
        principal: Principal,
        *,
        limit: int = 50,
        cursor: str = "",
        record_id: str = "",
    ) -> InferenceSummaryPage:
        deployment = self.get_deployment(deployment_id, principal)
        parsed_cursor = self._decode_cursor(cursor) if cursor else None
        rows = self.repository.list_inference_summaries(
            deployment.id, limit + 1, parsed_cursor, record_id or None
        )
        has_more = len(rows) > limit
        page = [InferenceRequestSummaryRead.model_validate(item) for item in rows[:limit]]
        next_cursor = self._encode_cursor(page[-1]) if has_more and page else None
        return InferenceSummaryPage(items=page, next_cursor=next_cursor)

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
        try:
            deployment = self.get_deployment(job.deployment_id, principal)
            access_policy.require_business_case(
                principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR
            )
        except Exception as exc:
            job.status = ReplayStatus.FAILED
            job.error_message = f"Replay authorization failed before execution: {exc}"[:4000]
            job.completed_at = datetime.now(timezone.utc)
            return self.repository.update_replay(job)
        job.status = ReplayStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self.repository.update_replay(job)
        try:
            sources = self.repository.replay_sources(job)
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
        *,
        resolved_model: Any | None = None,
    ) -> list[dict[str, Any]]:
        try:
            model = resolved_model or self._model_for_inference(assignment.model_id, principal)
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
    ) -> dict[str, Any]:
        models = []
        for assignment in assignments:
            model = self._model_for_inference(assignment.model_id, principal)
            if model.business_case_id != business_case_id:
                raise HTTPException(status_code=409, detail="Every assigned model must belong to the deployment Business Case")
            self._require_stage(model.stage, assignment.role)
            models.append(model)
        champion = models[[item.role for item in assignments].index(DeploymentRole.CHAMPION)]
        expected = self._inference_contract(champion)
        incompatible = [model.id for model in models if self._inference_contract(model) != expected]
        if incompatible:
            raise HTTPException(status_code=409, detail=f"Models have incompatible inference contracts: {', '.join(incompatible)}")
        return {model.id: model for model in models}

    def _model_for_inference(self, model_id: str, principal: Principal):
        resolver = getattr(self.models, "get_model_for_inference", self.models.get_model)
        return resolver(model_id, principal)

    @staticmethod
    def _inference_contract(model) -> tuple[Any, ...]:
        feature_definition = model.feature_engineering_definition or {}
        raw_features = feature_definition.get("feature_columns") or model.feature_columns
        classes = (
            model.model_parameters.get("classes")
            or model.training_config.get("classes")
            or []
        )
        output_schema = model.training_config.get("prediction_output_schema") or {}
        return (
            model.problem_type,
            model.target_column,
            tuple(raw_features),
            tuple(str(item) for item in classes),
            json.dumps(output_schema, sort_keys=True, separators=(",", ":")),
        )

    @staticmethod
    def _require_stage(stage: ModelStage, role: DeploymentRole) -> None:
        allowed = {ModelStage.PRODUCTION} if role in {DeploymentRole.CHAMPION, DeploymentRole.FALLBACK} else {ModelStage.STAGING, ModelStage.PRODUCTION}
        if stage not in allowed:
            raise HTTPException(status_code=409, detail=f"Model stage {stage.value} cannot be assigned as {role.value}")

    @staticmethod
    def _request_hash(
        revision_id: str,
        model_id: str,
        role: DeploymentRole,
        instances: list[dict[str, Any]],
    ) -> str:
        canonical = json.dumps({
            "revision_id": revision_id,
            "model_id": model_id,
            "role": role.value,
            "instances": instances,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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
        latency_ms: int,
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
            "status": "succeeded",
            "error_message": "",
            "latency_ms": latency_ms,
            "created_at": inference.created_at,
        } for index, (instance, output) in enumerate(zip(instances, outputs, strict=True))]

    @staticmethod
    def _failed_item_rows(
        inference: InferenceRequest,
        instances: list[dict[str, Any]],
        assignment: ModelAssignment,
        error_message: str,
        started: float,
    ) -> list[dict[str, Any]]:
        latency_ms = round((time.monotonic() - started) * 1000)
        return [{
            "id": f"{inference.id}:{assignment.model_id}:{index}",
            "request_id": inference.id,
            "deployment_id": inference.deployment_id,
            "record_id": instance["record_id"],
            "model_id": assignment.model_id,
            "role": assignment.role.value,
            "input": instance["features"],
            "output": {},
            "status": "failed",
            "error_message": error_message[:4000],
            "latency_ms": latency_ms,
            "created_at": inference.created_at,
        } for index, instance in enumerate(instances)]

    def _fail_inference(
        self,
        inference: InferenceRequest,
        code: str,
        message: str,
        started: float,
        execution_items: list[dict[str, Any]] | None = None,
    ) -> None:
        inference.status = InferenceStatus.FAILED
        inference.error_code = code
        inference.error_message = message[:4000]
        inference.latency_ms = round((time.monotonic() - started) * 1000)
        inference.completed_at = datetime.now(timezone.utc)
        try:
            self.repository.complete_inference(inference, execution_items or [])
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

    def _set_runtime_status(
        self,
        deployment: Deployment,
        next_status: DeploymentStatus,
        principal: Principal,
        reason: str,
    ) -> None:
        if deployment.status == next_status:
            return
        previous = deployment.status
        deployment.status = next_status
        deployment.updated_by = principal.user_id
        deployment.updated_at = datetime.now(timezone.utc)
        try:
            self.repository.update_deployment(deployment)
            self._audit(principal, "serving.runtime_status_changed", deployment, {
                "status": previous.value,
            }, {"status": next_status.value, "reason": reason})
        except Exception:
            deployment.status = previous
            logger.exception(
                "Could not persist runtime deployment status deployment_id=%s status=%s",
                deployment.id,
                next_status.value,
            )

    @staticmethod
    def _encode_cursor(item: InferenceRequest | InferenceRequestSummaryRead) -> str:
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
