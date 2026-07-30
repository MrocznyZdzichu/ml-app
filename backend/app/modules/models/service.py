from collections import defaultdict
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.security import Principal
from app.modules.models.domain import ModelArtifact, ModelStage, TrainingJob
from app.modules.models.repository import InMemoryModelRepository, ModelRepository
from app.modules.models.schemas import PromoteModelRequest, TrainingRequest
from app.modules.business_cases.domain import Artifact, ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.pipelines.domain import PipelineVersion
from app.modules.pipelines.repository import PipelineRepository, PostgresPipelineRepository
from app.modules.sharing.domain import AuditEvent, BC_ROLE_RANK, BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.sharing.domain import ResourceAccessRole, ResourceKind
from app.modules.serving.repository import PostgresServingRepository, ServingRepository
from app.modules.sharing.repository import PostgresSharingRepository


class ModelService:
    def __init__(
        self,
        repository: ModelRepository | None = None,
        artifacts: BusinessCaseRepository | None = None,
        pipelines: PipelineRepository | None = None,
        datasets: DatasetRepository | None = None,
        serving_repository: ServingRepository | None = None,
        audit_repository: PostgresSharingRepository | None = None,
    ) -> None:
        self.repository = repository or InMemoryModelRepository()
        self.artifacts = artifacts or PostgresBusinessCaseRepository()
        self.pipelines = pipelines or PostgresPipelineRepository()
        self.datasets = datasets or PostgresDatasetRepository()
        self.serving_repository = serving_repository or PostgresServingRepository()
        self.audit_repository = audit_repository or PostgresSharingRepository()

    def start_training(self, payload: TrainingRequest, principal: Principal) -> TrainingJob:
        asset = self.datasets.get(payload.dataset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        access_policy.require_resource(
            principal,
            ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
            asset.id,
            asset.owner_id,
            ResourceAccessRole.EDITOR,
        )
        job = TrainingJob(
            id=str(uuid4()),
            owner_id=principal.user_id,
            dataset_id=payload.dataset_id,
            target_column=payload.target_column,
            algorithm=payload.algorithm,
            feature_columns=list(payload.feature_columns),
            parameters=dict(payload.parameters),
        )
        self.repository.add_training_job(job)

        model = ModelArtifact(
            id=str(uuid4()),
            owner_id=principal.user_id,
            training_job_id=job.id,
            name=f"{payload.algorithm}-{payload.target_column}",
            version="0.1.0",
            algorithm=payload.algorithm,
            artifact_uri=f"s3://models/{principal.user_id}/{job.id}/model.joblib",
        )
        self.repository.add_model(model)
        return job

    def list_training_jobs(self, principal: Principal) -> list[TrainingJob]:
        return self.repository.list_all_training_jobs() if principal.is_administrator else self.repository.list_training_jobs(principal.user_id)

    def list_models(self, principal: Principal) -> list[ModelArtifact]:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            case_ids = access_policy.accessible_business_case_ids(
                principal,
                BusinessCaseAccessRole.READER,
            )
            case_owners: set[str] = set()
        else:
            case_ids = None
            case_owners = {principal.user_id}
        pipeline_models = [self._artifact_model(artifact) for artifact in (
            self.artifacts.list_artifacts_for_business_cases(case_ids, ArtifactType.MODEL_VERSION)
            if isinstance(self.artifacts, PostgresBusinessCaseRepository)
            else [item for owner_id in case_owners for item in self.artifacts.list_artifacts(owner_id, ArtifactType.MODEL_VERSION)]
        )]
        run_references = self.pipelines.list_run_references({
            model.pipeline_run_id
            for model in pipeline_models
            if not model.pipeline_id and model.pipeline_run_id
        })
        for model in pipeline_models:
            if model.pipeline_id or not model.pipeline_run_id:
                continue
            run_reference = run_references.get(model.pipeline_run_id)
            if run_reference is not None and run_reference[0] == model.owner_id:
                model.pipeline_id = run_reference[1]
                model.lineage = {**model.lineage, "pipeline_id": run_reference[1]}

        fitted_by_run_step: dict[tuple[str, str], Artifact] = {}
        model_run_ids = {
            model.pipeline_run_id
            for model in pipeline_models
            if model.pipeline_run_id
        }
        if model_run_ids:
            fitted_artifacts = (
                self.artifacts.list_feature_transform_summary_artifacts_for_run_ids(
                    model_run_ids
                )
                if isinstance(self.artifacts, PostgresBusinessCaseRepository)
                else [item for owner_id in case_owners for item in self.artifacts.list_artifacts(owner_id, ArtifactType.FEATURE_TRANSFORM)]
            )
            for artifact in fitted_artifacts:
                lineage = dict(artifact.metadata.get("lineage") or {})
                run_id = str(lineage.get("pipeline_run_id") or "")
                step_id = str(lineage.get("pipeline_step_id") or "")
                if run_id and step_id:
                    fitted_by_run_step.setdefault((run_id, step_id), artifact)

        pipeline_version_ids = {
            model.pipeline_version_id
            for model in pipeline_models
            if model.pipeline_version_id
        }
        versions_by_id = {
            version.id: version
            for version in self.pipelines.list_versions_by_ids(pipeline_version_ids)
        }
        for model in pipeline_models:
            self._enrich_batch_scoring_contract(model, fitted_by_run_step, versions_by_id)
            model.logical_id = model.logical_id or self._logical_model_id(model)
        known = {item.id for item in pipeline_models}
        models = [
            *pipeline_models,
            *(item for item in (
                self.repository.list_all_models() if principal.is_administrator else self.repository.list_models(principal.user_id)
            ) if item.id not in known),
        ]
        self._assign_version_numbers(models)
        return sorted(models, key=lambda item: (item.created_at, item.id), reverse=True)

    def list_model_summaries(self, principal: Principal) -> list[ModelArtifact]:
        """List registry/workflow fields without metrics, trials or fitted-state payloads."""
        if not isinstance(self.artifacts, PostgresBusinessCaseRepository):
            return [
                replace(model, metrics={}, model_parameters={})
                for model in self.list_models(principal)
            ]

        case_ids = access_policy.accessible_business_case_ids(
            principal,
            BusinessCaseAccessRole.READER,
        )
        models = [
            self._artifact_model(artifact)
            for artifact in self.artifacts.list_model_summary_artifacts_for_business_cases(case_ids)
        ]
        self._enrich_model_summary_contracts(models)
        known = {item.id for item in models}
        legacy = [
            replace(item, metrics={}, model_parameters={}) for item in (
                self.repository.list_all_models()
                if principal.is_administrator
                else self.repository.list_models(principal.user_id)
            )
            if item.id not in known
        ]
        models.extend(legacy)
        self._assign_version_numbers(models)
        return sorted(models, key=lambda item: (item.created_at, item.id), reverse=True)

    def page_model_families(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str = "",
        business_case_id: str = "",
        stage: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
    ) -> tuple[list[tuple[ModelArtifact, int]], int]:
        if not isinstance(self.artifacts, PostgresBusinessCaseRepository):
            return self._page_model_families_in_memory(
                self.list_model_summaries(principal),
                limit=limit,
                offset=offset,
                search=search,
                business_case_id=business_case_id,
                stage=stage,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline_type,
            )
        if business_case_id:
            access_policy.require_business_case(
                principal,
                business_case_id,
                BusinessCaseAccessRole.READER,
            )
            case_ids: set[str] | None = {business_case_id}
        else:
            case_ids = access_policy.accessible_business_case_ids(
                principal,
                BusinessCaseAccessRole.READER,
            )
        legacy = (
            self.repository.list_all_models()
            if principal.is_administrator
            else self.repository.list_models(principal.user_id)
        )
        if legacy:
            return self._page_model_families_in_memory(
                self.list_model_summaries(principal),
                limit=limit,
                offset=offset,
                search=search,
                business_case_id=business_case_id,
                stage=stage,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline_type,
            )
        artifact_page, total = self.artifacts.page_model_family_summaries(
            case_ids,
            limit=limit,
            offset=offset,
            search=search,
            stage=stage,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline_type,
        )
        models = [self._artifact_model(artifact) for artifact, _ in artifact_page]
        self._enrich_model_summary_contracts(models)
        result: list[tuple[ModelArtifact, int]] = []
        for model, (_, version_count) in zip(models, artifact_page, strict=True):
            model.logical_id = model.logical_id or self._logical_model_id(model)
            model.version_number = version_count
            model.version = f"v{version_count}"
            result.append((model, version_count))
        return result, total

    def _enrich_model_summary_contracts(
        self,
        models: list[ModelArtifact],
    ) -> None:
        run_references = self.pipelines.list_run_references({
            model.pipeline_run_id
            for model in models
            if not model.pipeline_id and model.pipeline_run_id
        })
        for model in models:
            if model.pipeline_id or not model.pipeline_run_id:
                continue
            run_reference = run_references.get(model.pipeline_run_id)
            if run_reference is not None and run_reference[0] == model.owner_id:
                model.pipeline_id = run_reference[1]
                model.lineage = {**model.lineage, "pipeline_id": run_reference[1]}

        fitted_by_run_step: dict[tuple[str, str], Artifact] = {}
        model_run_ids = {
            model.pipeline_run_id for model in models if model.pipeline_run_id
        }
        for artifact in self.artifacts.list_feature_transform_summary_artifacts_for_run_ids(
            model_run_ids
        ):
            lineage = dict(artifact.metadata.get("lineage") or {})
            run_id = str(lineage.get("pipeline_run_id") or "")
            step_id = str(lineage.get("pipeline_step_id") or "")
            if run_id and step_id:
                fitted_by_run_step.setdefault((run_id, step_id), artifact)

        pipeline_version_ids = {
            model.pipeline_version_id
            for model in models
            if model.pipeline_version_id
        }
        versions_by_id = {
            version.id: version
            for version in self.pipelines.list_versions_by_ids(pipeline_version_ids)
        }
        for model in models:
            self._enrich_batch_scoring_contract(model, fitted_by_run_step, versions_by_id)
            model.logical_id = model.logical_id or self._logical_model_id(model)
            model.metrics = {}
            model.model_parameters = {}

    @staticmethod
    def _page_model_families_in_memory(
        models: list[ModelArtifact],
        *,
        limit: int,
        offset: int,
        search: str,
        business_case_id: str,
        stage: str,
        pipeline_id: str,
        pipeline_type: str = "",
    ) -> tuple[list[tuple[ModelArtifact, int]], int]:
        families: dict[str, list[ModelArtifact]] = {}
        for model in models:
            families.setdefault(model.logical_id or model.id, []).append(model)
        needle = search.strip().casefold()
        result: list[tuple[ModelArtifact, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            if business_case_id and latest.business_case_id != business_case_id:
                continue
            if stage and latest.stage.value != stage:
                continue
            if pipeline_id and latest.pipeline_id != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    latest.name,
                    latest.algorithm,
                    latest.problem_type,
                    latest.version,
                )
            ):
                continue
            result.append((latest, len(versions)))
        result.sort(
            key=lambda item: (item[0].created_at, item[0].id),
            reverse=True,
        )
        return result[offset : offset + limit], len(result)

    def get_model(self, model_id: str, principal: Principal) -> ModelArtifact:
        return self._get_model(model_id, principal, include_display_version=True)

    def get_model_for_inference(self, model_id: str, principal: Principal) -> ModelArtifact:
        """Resolve one immutable inference bundle without registry presentation work."""
        return self._get_model(model_id, principal, include_display_version=False)

    def get_models_for_inference(
        self,
        model_ids: set[str],
        principal: Principal,
    ) -> dict[str, ModelArtifact]:
        """Resolve one active revision's bundles with batched registry reads."""
        if not model_ids:
            return {}
        artifacts = self.artifacts.get_artifacts(model_ids)
        business_case_ids = {
            artifact.business_case_id
            for artifact in artifacts.values()
            if artifact.type == ArtifactType.MODEL_VERSION
            and artifact.business_case_id
        }
        if principal.is_administrator:
            for business_case_id in business_case_ids:
                access_policy.require_business_case(
                    principal,
                    business_case_id,
                    BusinessCaseAccessRole.READER,
                )
            readable_roles = None
        else:
            readable_roles = {
                business_case_id: role
                for business_case_id, role in access_policy.business_case_roles(
                    principal,
                    set(business_case_ids),
                ).items()
                if BC_ROLE_RANK[role]
                >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]
            }

        models: dict[str, ModelArtifact] = {}
        for model_id in model_ids:
            artifact = artifacts.get(model_id)
            if artifact is None or artifact.type != ArtifactType.MODEL_VERSION:
                continue
            if artifact.business_case_id:
                if (
                    readable_roles is not None
                    and artifact.business_case_id not in readable_roles
                ):
                    continue
            elif (
                not principal.is_administrator
                and artifact.owner_id != principal.user_id
            ):
                continue
            models[model_id] = self._artifact_model(artifact)

        missing_ids = model_ids - set(models)
        for model_id in list(missing_ids):
            legacy = self.repository.get_model(model_id)
            if legacy is not None and (
                principal.is_administrator or legacy.owner_id == principal.user_id
            ):
                models[model_id] = legacy
        if set(models) != model_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found",
            )

        pipeline_models = [
            model for model in models.values()
            if model.pipeline_run_id or model.pipeline_version_id
        ]
        run_references = self.pipelines.list_run_references({
            model.pipeline_run_id
            for model in pipeline_models
            if not model.pipeline_id and model.pipeline_run_id
        })
        for model in pipeline_models:
            if model.pipeline_id or not model.pipeline_run_id:
                continue
            reference = run_references.get(model.pipeline_run_id)
            if reference is not None and reference[0] == model.owner_id:
                model.pipeline_id = reference[1]
                model.lineage = {**model.lineage, "pipeline_id": reference[1]}

        versions_by_id = {
            version.id: version
            for version in self.pipelines.list_versions_by_ids({
                model.pipeline_version_id
                for model in pipeline_models
                if model.pipeline_version_id
            })
        }
        transforms: dict[tuple[str, str], Artifact] = {}
        for artifact in self.artifacts.list_feature_transform_summary_artifacts_for_run_ids({
            model.pipeline_run_id
            for model in pipeline_models
            if model.pipeline_run_id
        }):
            lineage = dict(artifact.metadata.get("lineage") or {})
            run_id = str(lineage.get("pipeline_run_id") or "")
            step_id = str(lineage.get("pipeline_step_id") or "")
            if run_id and step_id:
                transforms.setdefault((run_id, step_id), artifact)
        for model in pipeline_models:
            self._enrich_batch_scoring_contract(
                model,
                transforms,
                versions_by_id,
            )
            model.logical_id = model.logical_id or self._logical_model_id(model)
        return models

    def list_serving_candidates(
        self, business_case_id: str, principal: Principal
    ) -> list[ModelArtifact]:
        """Resolve only deployable models from one BC, enriching their inference bundle on demand."""
        access_policy.require_business_case(
            principal, business_case_id, BusinessCaseAccessRole.READER
        )
        summaries = [
            self._artifact_model(artifact)
            for artifact in self.artifacts.list_model_summary_artifacts_for_business_cases(
                {business_case_id}
            )
        ]
        self._assign_version_numbers(summaries)
        deployable = [
            item for item in summaries
            if item.stage in {ModelStage.STAGING, ModelStage.PRODUCTION}
        ]
        candidates: list[ModelArtifact] = []
        for summary in deployable:
            model = self.get_model_for_inference(summary.id, principal)
            model.version = summary.version
            model.version_number = summary.version_number
            model.logical_id = summary.logical_id
            candidates.append(model)
        return candidates

    def page_serving_candidates(
        self,
        business_case_id: str,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str = "",
        model_ids: set[str] | None = None,
    ) -> tuple[list[ModelArtifact], int]:
        """Load inference bundles only for one bounded page of deployable versions."""
        access_policy.require_business_case(
            principal, business_case_id, BusinessCaseAccessRole.READER
        )
        summaries, total = self.artifacts.page_serving_model_summaries(
            business_case_id,
            limit=limit,
            offset=offset,
            search=search,
            model_ids=model_ids,
        )
        candidates: list[ModelArtifact] = []
        for artifact, version_number in summaries:
            model = self.get_model_for_inference(artifact.id, principal)
            model.logical_id = str(
                artifact.metadata.get("logical_model_id") or artifact.id
            )
            model.version_number = version_number
            model.version = f"v{version_number}"
            candidates.append(model)
        return candidates, total

    def _get_model(
        self,
        model_id: str,
        principal: Principal,
        *,
        include_display_version: bool,
    ) -> ModelArtifact:
        artifact = self.artifacts.get_artifact(model_id)
        if artifact is not None and artifact.type == ArtifactType.MODEL_VERSION:
            if artifact.business_case_id:
                access_policy.require_business_case(
                    principal,
                    artifact.business_case_id,
                    BusinessCaseAccessRole.READER,
                )
            elif not principal.is_administrator and artifact.owner_id != principal.user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

            model = self._artifact_model(artifact)
            if not model.pipeline_id and model.pipeline_run_id:
                run = self.pipelines.get_run(model.pipeline_run_id)
                if run is not None and run.owner_id == model.owner_id:
                    model.pipeline_id = run.pipeline_id
                    model.lineage = {**model.lineage, "pipeline_id": run.pipeline_id}

            version = (
                self.pipelines.get_version(model.pipeline_version_id)
                if model.pipeline_version_id else None
            )
            if version is not None and version.owner_id == model.owner_id:
                auto_fe = dict(model.training_config.get("auto_feature_engineering") or {})
                resolved_recipe = auto_fe.get("resolved_recipe")
                uses_autofe_recipe = isinstance(resolved_recipe, dict) and bool(resolved_recipe)
                fitted_step_id = (
                    model.pipeline_step_id
                    if uses_autofe_recipe
                    else self._upstream_feature_step_id(version.definition, model.pipeline_step_id)
                )
                fitted = (
                    self.artifacts.find_feature_transform_artifact(
                        model.business_case_id,
                        model.pipeline_run_id,
                        fitted_step_id,
                    )
                    if model.business_case_id and model.pipeline_run_id and fitted_step_id
                    else None
                )
                self._enrich_batch_scoring_contract(
                    model,
                    {(model.pipeline_run_id, fitted_step_id): fitted} if fitted is not None else {},
                    {version.id: version},
                )

            model.logical_id = model.logical_id or self._logical_model_id(model)
            if include_display_version:
                family = [
                    self._artifact_model(item)
                    for item in self.artifacts.list_model_version_artifacts(model.logical_id)
                ]
                self._assign_version_numbers(family)
                matching_version = next((item for item in family if item.id == model.id), None)
                if matching_version is not None:
                    model.version = matching_version.version
                    model.version_number = matching_version.version_number
            return model

        model = self.repository.get_model(model_id)
        if model is None or (not principal.is_administrator and model.owner_id != principal.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        return model

    def list_versions(self, logical_id: str, principal: Principal) -> list[ModelArtifact]:
        # Version history is a metadata-only read. Do not call list_models here:
        # that path enriches every visible model with fitted transforms and
        # pipeline definitions for scoring, which is unnecessary for a family
        # history modal and becomes increasingly expensive with registry size.
        artifacts = self.artifacts.list_model_version_artifacts(logical_id)
        if principal.is_administrator:
            visible_artifacts = artifacts
        elif isinstance(self.artifacts, PostgresBusinessCaseRepository):
            readable_case_ids = access_policy.accessible_business_case_ids(
                principal,
                BusinessCaseAccessRole.READER,
            ) or set()
            visible_artifacts = [
                artifact for artifact in artifacts
                if artifact.business_case_id in readable_case_ids
            ]
        else:
            visible_artifacts = [
                artifact for artifact in artifacts
                if artifact.owner_id == principal.user_id
            ]
        versions = [self._artifact_model(artifact) for artifact in visible_artifacts]
        for version in versions:
            version.logical_id = version.logical_id or logical_id

        # Keep support for legacy in-memory models, which are not registered as
        # pipeline artifacts. They are already bounded to the current owner.
        legacy_models = (
            self.repository.list_all_models()
            if principal.is_administrator
            else self.repository.list_models(principal.user_id)
        )
        versions.extend(
            model for model in legacy_models
            if (model.logical_id or model.id) == logical_id
            and all(existing.id != model.id for existing in versions)
        )
        if not versions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logical model not found")
        self._assign_version_numbers(versions)
        return sorted(versions, key=lambda item: item.version_number)

    def page_versions(
        self,
        logical_id: str,
        principal: Principal,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ModelArtifact], int]:
        versions = list(reversed(self.list_versions(logical_id, principal)))
        return versions[offset : offset + limit], len(versions)

    def promote_model(
        self,
        model_id: str,
        payload: PromoteModelRequest,
        principal: Principal,
    ) -> ModelArtifact:
        artifact = self.artifacts.get_artifact(model_id)
        if artifact is not None and artifact.type == ArtifactType.MODEL_VERSION:
            if artifact.business_case_id:
                access_policy.require_business_case(
                    principal,
                    artifact.business_case_id,
                    BusinessCaseAccessRole.CONTRIBUTOR,
                )
            self._require_stage_compatible_with_active_serving(model_id, payload.stage)
            previous_stage = str(artifact.metadata.get("stage") or ModelStage.DEVELOPED.value)
            artifact.metadata = {**artifact.metadata, "stage": payload.stage.value}
            try:
                self.artifacts.update_artifact(artifact)
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Model lifecycle changed concurrently with an active serving assignment; retry after updating the service revision",
                ) from exc
            model = self._artifact_model(artifact)
            family = [
                self._artifact_model(item)
                for item in self.artifacts.list_model_version_artifacts(
                    model.logical_id or model.id
                )
            ]
            self._assign_version_numbers(family)
            version = next((item for item in family if item.id == model.id), None)
            if version is not None:
                model.version = version.version
                model.version_number = version.version_number
            self._audit_stage_change(model, previous_stage, payload.stage, principal)
            return model

        model = self.get_model(model_id, principal)
        if model.business_case_id:
            access_policy.require_business_case(
                principal,
                model.business_case_id,
                BusinessCaseAccessRole.CONTRIBUTOR,
            )
        self._require_stage_compatible_with_active_serving(model_id, payload.stage)
        previous_stage = model.stage.value
        model.stage = payload.stage
        updated = self.repository.update_model(model)
        self._audit_stage_change(updated, previous_stage, payload.stage, principal)
        return updated

    def _audit_stage_change(
        self,
        model: ModelArtifact,
        previous_stage: str,
        next_stage: ModelStage,
        principal: Principal,
    ) -> None:
        if previous_stage == next_stage.value:
            return
        self.audit_repository.add_audit(AuditEvent(
            id=str(uuid4()),
            actor_id=principal.user_id,
            action="model.stage_changed",
            subject_type="model_version",
            subject_id=model.id,
            resource_kind="business_case" if model.business_case_id else "model_version",
            resource_id=model.business_case_id or model.id,
            previous_state={"stage": previous_stage},
            new_state={"stage": next_stage.value},
        ))

    def _require_stage_compatible_with_active_serving(
        self,
        model_id: str,
        stage: ModelStage,
    ) -> None:
        usages = self.serving_repository.active_assignments_for_model(model_id)
        incompatible = [
            usage for usage in usages
            if (
                usage["role"] in {"champion", "fallback"}
                and stage != ModelStage.PRODUCTION
            ) or (
                usage["role"] in {"challenger", "shadow"}
                and stage not in {ModelStage.STAGING, ModelStage.PRODUCTION}
            )
        ]
        if not incompatible:
            return
        blockers = ", ".join(
            f"{item['deployment_name']} ({item['role']})" for item in incompatible[:5]
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Model stage cannot be changed to {stage.value} while it is actively assigned to: "
                f"{blockers}. Activate a compatible deployment revision or stop the service first."
            ),
        )

    @staticmethod
    def _logical_model_id(model: ModelArtifact) -> str:
        if not model.pipeline_id or not model.pipeline_step_id:
            return model.id
        return str(uuid5(
            NAMESPACE_URL,
            (
                f"mlapp:model-family:{model.owner_id}:{model.pipeline_id}:"
                f"{model.pipeline_step_id}:model"
            ),
        ))

    @staticmethod
    def _assign_version_numbers(models: list[ModelArtifact]) -> None:
        families: dict[str, list[ModelArtifact]] = defaultdict(list)
        for model in models:
            model.logical_id = model.logical_id or model.id
            families[model.logical_id].append(model)
        for versions in families.values():
            versions.sort(key=lambda item: (item.created_at, item.id))
            for version_number, model in enumerate(versions, start=1):
                model.version_number = version_number
                model.version = f"v{version_number}"

    @staticmethod
    def _enrich_batch_scoring_contract(
        model: ModelArtifact,
        fitted_by_run_step: dict[tuple[str, str], Artifact],
        versions_by_id: dict[str, PipelineVersion],
    ) -> None:
        if not model.pipeline_version_id:
            return
        version = versions_by_id.get(model.pipeline_version_id)
        if version is None or version.owner_id != model.owner_id:
            return
        auto_fe = dict(model.training_config.get("auto_feature_engineering") or {})
        resolved_recipe = auto_fe.get("resolved_recipe")
        uses_autofe_recipe = isinstance(resolved_recipe, dict) and bool(resolved_recipe)
        if uses_autofe_recipe:
            # AutoML creates its fitted state inside the AutoML step itself.
            fitted_step_id = model.pipeline_step_id
            model.feature_engineering_definition = dict(resolved_recipe)
        else:
            # Traditional training consumes a fitted transform created by its
            # upstream Feature Engineering step.
            fitted_step_id = ModelService._upstream_feature_step_id(
                version.definition, model.pipeline_step_id
            )
        fitted = fitted_by_run_step.get((model.pipeline_run_id, fitted_step_id))
        if fitted is not None:
            model.fitted_transform_artifact_id = fitted.id

        for step in version.definition.get("steps", []):
            if not isinstance(step, dict):
                continue
            config = step.get("config")
            nested = (
                config.get("definition")
                if isinstance(config, dict)
                and isinstance(config.get("definition"), dict)
                else {}
            )
            if step.get("type") == "data_engineering":
                model.data_engineering_definition = dict(nested)
            elif step.get("type") == "feature_engineering" and not uses_autofe_recipe:
                model.feature_engineering_definition = dict(nested)

    @staticmethod
    def _upstream_feature_step_id(definition: dict, model_step_id: str) -> str:
        model_step = next(
            (
                step for step in definition.get("steps", [])
                if isinstance(step, dict) and step.get("step_id") == model_step_id
            ),
            {},
        )
        for item in model_step.get("inputs", []):
            if isinstance(item, dict) and item.get("port_id") == "training":
                source = item.get("source") or {}
                if isinstance(source, dict):
                    return str(source.get("step_id") or "")
        return ""

    @staticmethod
    def _artifact_model(artifact: Artifact) -> ModelArtifact:
        metadata = artifact.metadata
        lineage = dict(metadata.get("lineage") or {})
        return ModelArtifact(
            id=artifact.id,
            owner_id=artifact.owner_id,
            training_job_id=str(lineage.get("pipeline_run_id") or ""),
            name=str(metadata.get("model_name") or "Pipeline model"),
            version=f"run-{str(lineage.get('pipeline_run_id') or artifact.reference_id)[:8]}",
            algorithm=str(metadata.get("algorithm") or "unknown"),
            artifact_uri=str(metadata.get("location_uri") or ""),
            logical_id=str(metadata.get("logical_model_id") or ""),
            stage=ModelStage(
                ModelStage.DEVELOPED.value
                if str(metadata.get("stage") or "") == "candidate"
                else str(metadata.get("stage") or ModelStage.DEVELOPED.value)
            ),
            metrics=dict(metadata.get("metrics") or {}),
            business_case_id=artifact.business_case_id or "",
            pipeline_id=str(lineage.get("pipeline_id") or ""),
            pipeline_version_id=str(lineage.get("pipeline_version_id") or ""),
            pipeline_run_id=str(lineage.get("pipeline_run_id") or ""),
            pipeline_step_id=str(lineage.get("pipeline_step_id") or ""),
            problem_type=str(metadata.get("problem_type") or ""),
            target_column=str(metadata.get("target_column") or ""),
            feature_columns=[str(value) for value in metadata.get("feature_columns") or []],
            model_hash=str(metadata.get("model_hash") or ""),
            training_config=dict(metadata.get("training_config") or {}),
            model_parameters=dict(metadata.get("model_parameters") or {}),
            lineage=lineage,
            created_at=artifact.created_at,
        )
