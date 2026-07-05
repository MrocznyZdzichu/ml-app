import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.security import Principal
from app.modules.business_cases.service import BusinessCaseService
from app.modules.business_cases.domain import ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.datasets.domain import DataAssetStatus
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.pipelines.domain import (
    Pipeline,
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTrigger,
    PipelineStatus,
    PipelineStepType,
    PipelineVersion,
    PipelineVersionStatus,
)
from app.modules.pipelines.repository import PipelineRepository, PostgresPipelineRepository
from app.modules.pipelines.run_preview import PipelineRunOutputReader
from app.modules.pipelines.schemas import (
    PipelineCreate,
    PipelineCopy,
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
        datasets: DatasetRepository | None = None,
        artifacts: BusinessCaseRepository | None = None,
    ) -> None:
        self.repository = repository or pipeline_repository
        self.business_cases = business_cases or BusinessCaseService()
        self.output_reader = output_reader or PipelineRunOutputReader()
        self.datasets = datasets or PostgresDatasetRepository()
        self.artifacts = artifacts or PostgresBusinessCaseRepository()

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
            template=self._definition_template(payload.definition),
        )
        definition = validate_definition(payload.definition, executable=False)
        draft = PipelineVersion(
            id=str(uuid4()),
            owner_id=principal.user_id,
            pipeline_id=pipeline.id,
            business_case_id=business_case.id,
            version_number=1,
            status=PipelineVersionStatus.DRAFT,
            definition=definition,
            definition_hash=definition_hash(definition),
            created_by=principal.user_id,
            created_at=now,
        )
        self.repository.add_pipeline(pipeline)
        self.repository.add_version(draft)
        self._apply_version_summary(pipeline, [draft])
        return pipeline

    def list_pipelines(self, principal: Principal, business_case_id: str | None = None) -> list[Pipeline]:
        if business_case_id:
            self.business_cases.get_business_case(business_case_id, principal)
        pipelines = self.repository.list_pipelines(principal.user_id, business_case_id)
        versions_by_pipeline: dict[str, list[PipelineVersion]] = {
            pipeline.id: [] for pipeline in pipelines
        }
        for version in self.repository.list_versions_for_pipelines(
            principal.user_id,
            list(versions_by_pipeline),
        ):
            versions_by_pipeline.setdefault(version.pipeline_id, []).append(version)
        for pipeline in pipelines:
            self._apply_version_summary(pipeline, versions_by_pipeline[pipeline.id])
        return pipelines

    def get_pipeline(self, pipeline_id: str, principal: Principal) -> Pipeline:
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        self._apply_version_summary(
            pipeline,
            self.repository.list_versions(pipeline.id),
        )
        return pipeline

    def _get_owned_pipeline(self, pipeline_id: str, principal: Principal) -> Pipeline:
        pipeline = self.repository.get_pipeline(pipeline_id)
        if not pipeline or pipeline.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
        return pipeline

    def _apply_version_summary(
        self,
        pipeline: Pipeline,
        versions: list[PipelineVersion],
    ) -> None:
        published = [
            item for item in versions if item.status == PipelineVersionStatus.PUBLISHED
        ]
        drafts = [
            item for item in versions if item.status == PipelineVersionStatus.DRAFT
        ]
        pipeline.latest_published_version_number = (
            max(item.version_number for item in published) if published else None
        )
        pipeline.published_version_count = len(published)
        pipeline.draft_version_number = (
            max(item.version_number for item in drafts) if drafts else None
        )
        summary_version = (
            max(published, key=lambda item: item.version_number)
            if published
            else max(drafts, key=lambda item: item.version_number, default=None)
        )
        pipeline.template = self._definition_template(
            summary_version.definition if summary_version else {}
        )

    @staticmethod
    def _definition_template(definition: dict[str, Any]) -> str:
        parameters = definition.get("parameters")
        if isinstance(parameters, dict) and parameters.get("template"):
            return str(parameters["template"])
        for step in definition.get("steps") or []:
            if not isinstance(step, dict):
                continue
            config = step.get("config")
            nested = config.get("definition") if isinstance(config, dict) else None
            nested_parameters = nested.get("parameters") if isinstance(nested, dict) else None
            if isinstance(nested_parameters, dict) and nested_parameters.get("template"):
                return str(nested_parameters["template"])
        return "custom"

    def update_pipeline(
        self,
        pipeline_id: str,
        payload: PipelineUpdate,
        principal: Principal,
    ) -> Pipeline:
        pipeline = self.get_pipeline(pipeline_id, principal)
        self._require_active_pipeline(pipeline)
        pipeline.name = payload.name
        if payload.description is not None:
            pipeline.description = payload.description.strip()
        if payload.type is not None:
            pipeline.type = payload.type
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = datetime.now(timezone.utc)
        return self.repository.update_pipeline(pipeline)

    def copy_pipeline(
        self,
        pipeline_id: str,
        payload: PipelineCopy,
        principal: Principal,
    ) -> Pipeline:
        source = self._get_owned_pipeline(pipeline_id, principal)
        versions = self.repository.list_versions(source.id)
        draft = next(
            (item for item in reversed(versions) if item.status == PipelineVersionStatus.DRAFT),
            None,
        )
        source_version = draft or (versions[-1] if versions else None)
        if source_version is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline has no version to copy",
            )

        now = datetime.now(timezone.utc)
        copied = Pipeline(
            id=str(uuid4()),
            owner_id=principal.user_id,
            business_case_id=source.business_case_id,
            name=payload.name,
            description=source.description,
            type=source.type,
            status=PipelineStatus.DRAFT,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
            template=self._definition_template(source_version.definition),
        )
        definition = normalize_definition(deepcopy(source_version.definition))
        draft = PipelineVersion(
            id=str(uuid4()),
            owner_id=principal.user_id,
            pipeline_id=copied.id,
            business_case_id=copied.business_case_id,
            version_number=1,
            status=PipelineVersionStatus.DRAFT,
            definition=definition,
            definition_hash=definition_hash(definition),
            created_by=principal.user_id,
            created_at=now,
        )
        self.repository.add_pipeline(copied)
        self.repository.add_version(draft)
        self._apply_version_summary(copied, [draft])
        return copied

    def delete_pipeline(self, pipeline_id: str, principal: Principal) -> str:
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        if self.repository.delete_pipeline_without_runs(pipeline.id):
            return "deleted"
        pipeline.status = PipelineStatus.DEPRECATED
        pipeline.updated_by = principal.user_id
        pipeline.updated_at = datetime.now(timezone.utc)
        self.repository.update_pipeline(pipeline)
        return "deprecated"

    def list_versions(self, pipeline_id: str, principal: Principal) -> list[PipelineVersion]:
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        return self.repository.list_versions(pipeline.id)

    def update_draft_version(
        self,
        pipeline_id: str,
        payload: PipelineVersionUpdate,
        principal: Principal,
    ) -> PipelineVersion:
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        self._require_active_pipeline(pipeline)
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
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        self._require_active_pipeline(pipeline)
        version = self.repository.get_draft_version(pipeline.id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline has no draft version to publish",
            )
        version.definition = validate_definition(version.definition, executable=True)
        self._validate_external_artifacts(
            WorkflowDefinition.model_validate(version.definition),
            principal,
            pipeline.business_case_id,
        )
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
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        self._require_active_pipeline(pipeline)
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
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        self._require_active_pipeline(pipeline)
        version = self._resolve_run_version(pipeline, payload.pipeline_version_id)
        if version.status == PipelineVersionStatus.DRAFT and not payload.is_dry_run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draft pipeline versions can only be run as dry-run",
            )
        version.definition = validate_definition(version.definition, executable=True)
        workflow = WorkflowDefinition.model_validate(version.definition)
        self._validate_external_artifacts(
            workflow,
            principal,
            pipeline.business_case_id,
        )
        if payload.step_id and payload.step_id not in {step.step_id for step in workflow.steps}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pipeline workflow step not found",
            )
        now = datetime.now(timezone.utc)
        resolved_inputs = self._resolve_input_versions(
            workflow,
            payload.input_versions,
            principal,
            pipeline.business_case_id,
        )
        runtime_parameters = dict(payload.runtime_parameters)
        runtime_parameters["resolved_input_versions"] = resolved_inputs
        run = PipelineRun(
            id=str(uuid4()),
            owner_id=principal.user_id,
            pipeline_id=pipeline.id,
            pipeline_version_id=version.id,
            business_case_id=pipeline.business_case_id,
            status=PipelineRunStatus.QUEUED,
            trigger_type=payload.trigger_type,
            runtime_parameters=runtime_parameters,
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

    def _resolve_input_versions(
        self,
        workflow: WorkflowDefinition,
        requested_versions: dict[str, str],
        principal: Principal,
        business_case_id: str,
    ) -> dict[str, dict[str, Any]]:
        resolved: dict[str, dict[str, Any]] = {}
        attached_asset_ids = {
            attachment.data_asset_id
            for attachment in self.business_cases.list_data_attachments(
                business_case_id,
                principal,
            )
        }
        for step in workflow.steps:
            definition = step.config.get("definition")
            if not isinstance(definition, dict):
                continue
            inputs = definition.get("inputs")
            if not isinstance(inputs, list):
                continue
            for raw_input in inputs:
                if not isinstance(raw_input, dict):
                    continue
                policy = str(raw_input.get("version_policy") or "latest")
                logical_id = str(raw_input.get("dataset_id") or "")
                if not logical_id and policy != "select_at_run_any":
                    continue
                pinned_dataset_id = logical_id
                existing_version = self.datasets.get(logical_id)
                if (
                    policy != "pinned"
                    and existing_version is not None
                    and existing_version.owner_id == principal.user_id
                ):
                    logical_id = existing_version.logical_id
                input_id = str(raw_input.get("input_id") or "")
                binding_key = f"{step.step_id}:{input_id}"
                if policy in {"select_at_run", "select_at_run_any"}:
                    selected_id = requested_versions.get(binding_key) or requested_versions.get(input_id)
                    if not selected_id:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={
                                "message": "A dataset version must be selected before the run",
                                "input_key": binding_key,
                            },
                        )
                    asset = self.datasets.get(selected_id)
                    if (
                        asset is None
                        or asset.owner_id != principal.user_id
                        or asset.status == DataAssetStatus.DELETED
                        or (
                            policy == "select_at_run"
                            and asset.logical_id != logical_id
                        )
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={
                                "message": "Selected dataset version is not available for this input",
                                "input_key": binding_key,
                            },
                        )
                    if policy == "select_at_run_any":
                        attached_logical_ids = {
                            item.logical_id
                            for item_id in attached_asset_ids
                            for item in [self.datasets.get(item_id)]
                            if item is not None
                        }
                        if asset.id not in attached_asset_ids and asset.logical_id not in attached_logical_ids:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail={
                                    "message": (
                                        "Selected scoring dataset must be attached "
                                        "to the pipeline Business Case"
                                    ),
                                    "input_key": binding_key,
                                },
                            )
                        logical_id = asset.logical_id
                elif policy == "pinned":
                    asset = self.datasets.get(pinned_dataset_id)
                    if (
                        asset is None
                        or asset.owner_id != principal.user_id
                        or asset.status == DataAssetStatus.DELETED
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={
                                "message": "Pinned dataset version is not available",
                                "input_key": binding_key,
                            },
                        )
                    logical_id = asset.logical_id
                elif policy == "latest":
                    asset = self.datasets.get_latest_version(principal.user_id, logical_id)
                    if asset is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={
                                "message": "Logical dataset has no active version",
                                "input_key": binding_key,
                            },
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail={"message": f"Unsupported dataset version policy '{policy}'"},
                    )
                resolved[binding_key] = {
                    "input_id": input_id,
                    "step_id": step.step_id,
                    "logical_id": logical_id,
                    "version_policy": policy,
                    "dataset_id": asset.id,
                    "version_number": asset.version_number,
                    "dataset_name": asset.name,
                }
        return resolved

    def _validate_external_artifacts(
        self,
        workflow: WorkflowDefinition,
        principal: Principal,
        business_case_id: str,
    ) -> None:
        references: list[tuple[str, str, ArtifactType]] = []
        for step in workflow.steps:
            definition = step.config.get("definition")
            if not isinstance(definition, dict):
                continue
            if step.type == "feature_engineering" and definition.get("mode") == "transform":
                references.append((
                    step.step_id,
                    str(definition.get("fitted_state_artifact_id") or ""),
                    ArtifactType.FEATURE_TRANSFORM,
                ))
            if step.type == "scoring" and definition.get("purpose") == "batch":
                references.append((
                    step.step_id,
                    str(definition.get("model_artifact_id") or ""),
                    ArtifactType.MODEL_VERSION,
                ))
        for step_id, artifact_id, expected_type in references:
            artifact = self.artifacts.get_artifact(artifact_id)
            if (
                artifact is None
                or artifact.owner_id != principal.user_id
                or artifact.business_case_id != business_case_id
                or artifact.type != expected_type
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "message": (
                            f"Step '{step_id}' references an unavailable "
                            f"{expected_type.value} artifact"
                        )
                    },
                )

    def get_run(self, pipeline_id: str, run_id: str, principal: Principal) -> PipelineRun:
        pipeline = self._get_owned_pipeline(pipeline_id, principal)
        run = self.repository.get_run(run_id)
        if not run or run.pipeline_id != pipeline.id or run.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")
        return run

    def get_run_details(self, pipeline_id: str, run_id: str, principal: Principal) -> dict[str, Any]:
        run = self.get_run(pipeline_id, run_id, principal)
        version = self.repository.get_version(run.pipeline_version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline version not found")
        resolved = run.runtime_parameters.get("resolved_input_versions", {})
        resolved_inputs = list(resolved.values()) if isinstance(resolved, dict) else []
        lineage: list[dict[str, Any]] = []
        for artifact_id in run.output_artifact_ids:
            artifact = self.artifacts.get_artifact(artifact_id)
            if artifact is None or artifact.owner_id != principal.user_id:
                continue
            lineage.append(
                {
                    "artifact_id": artifact.id,
                    "artifact_type": artifact.type.value,
                    "reference_id": artifact.reference_id,
                    "origin": artifact.origin.value,
                    "lineage": dict(artifact.metadata.get("lineage") or {}),
                }
            )
        return {
            "run": run,
            "pipeline_version": {
                "id": version.id,
                "version_number": version.version_number,
                "definition_hash": version.definition_hash,
                "status": version.status.value,
            },
            "resolved_inputs": resolved_inputs,
            "steps": self.repository.list_step_runs(run.id, principal.user_id),
            "outputs": run.output_manifest,
            "lineage": lineage,
        }

    def cancel_run(self, pipeline_id: str, run_id: str, principal: Principal) -> PipelineRun:
        run = self.get_run(pipeline_id, run_id, principal)
        if run.status not in {PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only queued or running pipeline runs can be cancelled",
            )
        run.status = PipelineRunStatus.CANCELLED
        run.finished_at = datetime.now(timezone.utc)
        run.warnings = [*run.warnings, "Cancellation requested; an active DuckDB step stops at the next step boundary"]
        return self.repository.update_run(run)

    def retry_run(self, pipeline_id: str, run_id: str, principal: Principal) -> PipelineRun:
        previous = self.get_run(pipeline_id, run_id, principal)
        if previous.status not in {PipelineRunStatus.FAILED, PipelineRunStatus.CANCELLED}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only failed or cancelled pipeline runs can be retried",
            )
        resolved = previous.runtime_parameters.get("resolved_input_versions", {})
        input_versions = {
            str(key): str(value.get("dataset_id"))
            for key, value in resolved.items()
            if isinstance(value, dict) and value.get("dataset_id")
        } if isinstance(resolved, dict) else {}
        runtime_parameters = {
            key: value
            for key, value in previous.runtime_parameters.items()
            if key != "resolved_input_versions"
        }
        runtime_parameters["retry_of_run_id"] = previous.id
        return self.create_run(
            pipeline_id,
            PipelineRunCreate(
                pipeline_version_id=previous.pipeline_version_id,
                trigger_type=PipelineRunTrigger.MANUAL,
                runtime_parameters=runtime_parameters,
                input_versions=input_versions,
                is_dry_run=previous.is_dry_run,
                step_id=previous.requested_step_id or None,
            ),
            principal,
        )

    def list_runs(
        self,
        principal: Principal,
        pipeline_id: str | None = None,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        if pipeline_id:
            pipeline = self._get_owned_pipeline(pipeline_id, principal)
            pipeline_id = pipeline.id
        return self.repository.list_runs(
            pipeline_id,
            principal.user_id,
            limit=limit,
            offset=offset,
        )

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
        pipeline_step_id: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        run = self.get_run(pipeline_id, run_id, principal)
        return self.output_reader.preview(
            run,
            output_id=output_id,
            pipeline_step_id=pipeline_step_id,
            limit=limit,
            offset=offset,
        )

    def profile_run_output(
        self,
        pipeline_id: str,
        run_id: str,
        principal: Principal,
        *,
        output_id: str | None,
        pipeline_step_id: str | None,
        max_columns: int,
        top_n: int,
    ) -> dict[str, Any]:
        run = self.get_run(pipeline_id, run_id, principal)
        return self.output_reader.profile(
            run,
            output_id=output_id,
            pipeline_step_id=pipeline_step_id,
            max_columns=max_columns,
            top_n=top_n,
        )

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

    @staticmethod
    def _require_active_pipeline(pipeline: Pipeline) -> None:
        if pipeline.status == PipelineStatus.DEPRECATED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deprecated pipelines are read-only and cannot be run",
            )

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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Invalid pipeline workflow definition", "errors": errors},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Invalid pipeline workflow definition",
                "errors": [{"path": "", "message": str(exc)}],
            },
        ) from exc


def definition_hash(definition: dict) -> str:
    normalized = normalize_definition(definition)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
