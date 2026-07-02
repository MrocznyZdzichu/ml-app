import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.security import Principal
from app.modules.business_cases.service import BusinessCaseService
from app.modules.pipelines.domain import (
    Pipeline,
    PipelineRun,
    PipelineRunStatus,
    PipelineStatus,
    PipelineStepType,
    PipelineVersion,
    PipelineVersionStatus,
)
from app.modules.pipelines.repository import PipelineRepository, PostgresPipelineRepository
from app.modules.pipelines.run_preview import PipelineRunOutputReader
from app.modules.pipelines.schemas import (
    PipelineCreate,
    PipelineRunCreate,
    PipelineUpdate,
    PipelineVersionUpdate,
)
from app.modules.pipelines.workflow import (
    WorkflowDefinition,
    empty_workflow_definition,
    normalize_workflow_definition,
    validate_workflow_definition,
    workflow_validation_errors,
)


pipeline_repository = PostgresPipelineRepository()


class PipelineService:
    def __init__(
        self,
        repository: PipelineRepository | None = None,
        business_cases: BusinessCaseService | None = None,
        output_reader: PipelineRunOutputReader | None = None,
    ) -> None:
        self.repository = repository or pipeline_repository
        self.business_cases = business_cases or BusinessCaseService()
        self.output_reader = output_reader or PipelineRunOutputReader()

    def create_pipeline(self, payload: PipelineCreate, principal: Principal) -> Pipeline:
        business_case = self.business_cases.get_business_case(payload.business_case_id, principal)
        now = datetime.now(timezone.utc)
        pipeline = Pipeline(
            id=str(uuid4()),
            owner_id=principal.user_id,
            business_case_id=business_case.id,
            name=payload.name.strip(),
            description=payload.description,
            type=payload.type,
            status=PipelineStatus.DRAFT,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_pipeline(pipeline)
        self.repository.add_version(
            PipelineVersion(
                id=str(uuid4()),
                owner_id=principal.user_id,
                pipeline_id=pipeline.id,
                business_case_id=business_case.id,
                version_number=1,
                status=PipelineVersionStatus.DRAFT,
                definition=validate_definition(payload.definition, executable=False),
                definition_hash=definition_hash(payload.definition),
                created_by=principal.user_id,
                created_at=now,
            )
        )
        return pipeline

    def list_pipelines(self, principal: Principal, business_case_id: str | None = None) -> list[Pipeline]:
        if business_case_id:
            self.business_cases.get_business_case(business_case_id, principal)
        return self.repository.list_pipelines(principal.user_id, business_case_id)

    def get_pipeline(self, pipeline_id: str, principal: Principal) -> Pipeline:
        pipeline = self.repository.get_pipeline(pipeline_id)
        if not pipeline or pipeline.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
        return pipeline

    def update_pipeline(
        self,
        pipeline_id: str,
        payload: PipelineUpdate,
        principal: Principal,
    ) -> Pipeline:
        pipeline = self.get_pipeline(pipeline_id, principal)
        pipeline.name = payload.name
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = datetime.now(timezone.utc)
        return self.repository.update_pipeline(pipeline)

    def list_versions(self, pipeline_id: str, principal: Principal) -> list[PipelineVersion]:
        pipeline = self.get_pipeline(pipeline_id, principal)
        return self.repository.list_versions(pipeline.id)

    def update_draft_version(
        self,
        pipeline_id: str,
        payload: PipelineVersionUpdate,
        principal: Principal,
    ) -> PipelineVersion:
        pipeline = self.get_pipeline(pipeline_id, principal)
        version = self.repository.get_draft_version(pipeline.id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline has no editable draft version",
            )
        version.definition = validate_definition(payload.definition, executable=False)
        version.definition_hash = definition_hash(version.definition)
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = datetime.now(timezone.utc)
        self.repository.update_pipeline(pipeline)
        return self.repository.update_version(version)

    def publish_draft_version(self, pipeline_id: str, principal: Principal) -> PipelineVersion:
        pipeline = self.get_pipeline(pipeline_id, principal)
        version = self.repository.get_draft_version(pipeline.id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline has no draft version to publish",
            )
        version.definition = validate_definition(version.definition, executable=True)
        version.definition_hash = definition_hash(version.definition)
        now = datetime.now(timezone.utc)
        version.status = PipelineVersionStatus.PUBLISHED
        version.published_by = principal.user_id
        version.published_at = now
        pipeline.status = PipelineStatus.PUBLISHED
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = now
        self.repository.update_pipeline(pipeline)
        return self.repository.update_version(version)

    def create_next_draft_version(self, pipeline_id: str, principal: Principal) -> PipelineVersion:
        pipeline = self.get_pipeline(pipeline_id, principal)
        if self.repository.get_draft_version(pipeline.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline already has a draft version",
            )
        versions = self.repository.list_versions(pipeline.id)
        latest = versions[-1] if versions else None
        next_number = (latest.version_number + 1) if latest else 1
        definition = latest.definition if latest else empty_workflow_definition()
        version = PipelineVersion(
            id=str(uuid4()),
            owner_id=principal.user_id,
            pipeline_id=pipeline.id,
            business_case_id=pipeline.business_case_id,
            version_number=next_number,
            status=PipelineVersionStatus.DRAFT,
            definition=normalize_definition(definition),
            definition_hash=definition_hash(definition),
            created_by=principal.user_id,
        )
        pipeline.status = PipelineStatus.DRAFT
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = datetime.now(timezone.utc)
        self.repository.update_pipeline(pipeline)
        return self.repository.add_version(version)

    def create_run(self, pipeline_id: str, payload: PipelineRunCreate, principal: Principal) -> PipelineRun:
        pipeline = self.get_pipeline(pipeline_id, principal)
        version = self._resolve_run_version(pipeline, payload.pipeline_version_id)
        if version.status == PipelineVersionStatus.DRAFT and not payload.is_dry_run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draft pipeline versions can only be run as dry-run",
            )
        version.definition = validate_definition(version.definition, executable=True)
        workflow = WorkflowDefinition.model_validate(version.definition)
        if payload.step_id and payload.step_id not in {step.step_id for step in workflow.steps}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pipeline workflow step not found",
            )
        now = datetime.now(timezone.utc)
        run = PipelineRun(
            id=str(uuid4()),
            owner_id=principal.user_id,
            pipeline_id=pipeline.id,
            pipeline_version_id=version.id,
            business_case_id=pipeline.business_case_id,
            status=PipelineRunStatus.QUEUED,
            trigger_type=payload.trigger_type,
            runtime_parameters=dict(payload.runtime_parameters),
            is_dry_run=payload.is_dry_run,
            requested_step_id=payload.step_id or "",
            input_row_count=None,
            processed_row_count=None,
            output_row_count=None,
            rejected_row_count=0,
            warnings=[],
            output_artifact_ids=[],
            created_by=principal.user_id,
            created_at=now,
        )
        self.repository.add_run(run)
        from app.worker.tasks import execute_pipeline_run

        try:
            execute_pipeline_run.delay(run.id)
        except Exception as exc:
            run.status = PipelineRunStatus.FAILED
            run.error_message = f"Pipeline run could not be queued: {exc}"[:4000]
            run.finished_at = datetime.now(timezone.utc)
            self.repository.update_run(run)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "Pipeline execution queue is unavailable", "run_id": run.id},
            ) from exc
        return run

    def get_run(self, pipeline_id: str, run_id: str, principal: Principal) -> PipelineRun:
        pipeline = self.get_pipeline(pipeline_id, principal)
        run = self.repository.get_run(run_id)
        if not run or run.pipeline_id != pipeline.id or run.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")
        return run

    def list_runs(self, principal: Principal, pipeline_id: str | None = None) -> list[PipelineRun]:
        if pipeline_id:
            pipeline = self.get_pipeline(pipeline_id, principal)
            pipeline_id = pipeline.id
        return self.repository.list_runs(pipeline_id, principal.user_id)

    def list_step_runs(
        self,
        pipeline_id: str,
        run_id: str,
        principal: Principal,
    ) -> list:
        run = self.get_run(pipeline_id, run_id, principal)
        return self.repository.list_step_runs(run.id, principal.user_id)

    def preview_run_output(
        self,
        pipeline_id: str,
        run_id: str,
        principal: Principal,
        *,
        output_id: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        run = self.get_run(pipeline_id, run_id, principal)
        return self.output_reader.preview(run, output_id=output_id, limit=limit, offset=offset)

    def profile_run_output(
        self,
        pipeline_id: str,
        run_id: str,
        principal: Principal,
        *,
        output_id: str | None,
        max_columns: int,
        top_n: int,
    ) -> dict[str, Any]:
        run = self.get_run(pipeline_id, run_id, principal)
        return self.output_reader.profile(run, output_id=output_id, max_columns=max_columns, top_n=top_n)

    def list_step_types(self) -> list[dict[str, str]]:
        executable = {
            "select_columns", "add_identifier", "rename_columns", "cast_columns", "filter_rows", "sort_rows",
            "deduplicate", "impute_missing", "derive_column", "aggregate", "join", "union",
            "map_categories",
            "custom_sql",
        }
        return [
            {"id": item.value, "label": item.value.replace("_", " ").title()}
            for item in PipelineStepType
            if item.value in executable
        ]

    def _resolve_run_version(self, pipeline: Pipeline, version_id: str | None) -> PipelineVersion:
        versions = self.repository.list_versions(pipeline.id)
        if version_id:
            version = self.repository.get_version(version_id)
            if not version or version.pipeline_id != pipeline.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline version not found")
            return version
        published = [item for item in versions if item.status == PipelineVersionStatus.PUBLISHED]
        if published:
            return published[-1]
        draft = self.repository.get_draft_version(pipeline.id)
        if draft:
            return draft
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pipeline has no runnable version")


def normalize_definition(definition: dict) -> dict:
    return normalize_workflow_definition(definition)


def validate_definition(definition: dict, executable: bool) -> dict:
    normalized = normalize_definition(definition)
    try:
        return validate_workflow_definition(normalized, executable)
    except ValidationError as exc:
        errors = workflow_validation_errors(exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Invalid pipeline workflow definition", "errors": errors},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Invalid pipeline workflow definition",
                "errors": [{"path": "", "message": str(exc)}],
            },
        ) from exc


def definition_hash(definition: dict) -> str:
    normalized = normalize_definition(definition)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
