from collections import defaultdict
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.models.domain import ModelArtifact, TrainingJob
from app.modules.models.repository import InMemoryModelRepository, ModelRepository
from app.modules.models.schemas import PromoteModelRequest, TrainingRequest
from app.modules.business_cases.domain import Artifact, ArtifactType
from app.modules.business_cases.repository import PostgresBusinessCaseRepository
from app.modules.pipelines.repository import PostgresPipelineRepository


class ModelService:
    def __init__(
        self,
        repository: ModelRepository | None = None,
        artifacts: PostgresBusinessCaseRepository | None = None,
        pipelines: PostgresPipelineRepository | None = None,
    ) -> None:
        self.repository = repository or InMemoryModelRepository()
        self.artifacts = artifacts or PostgresBusinessCaseRepository()
        self.pipelines = pipelines or PostgresPipelineRepository()

    def start_training(self, payload: TrainingRequest, principal: Principal) -> TrainingJob:
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
        return self.repository.list_training_jobs(principal.user_id)

    def list_models(self, principal: Principal) -> list[ModelArtifact]:
        pipeline_models = []
        for artifact in self.artifacts.list_artifacts(
            principal.user_id,
            ArtifactType.MODEL_VERSION,
        ):
            model = self._artifact_model(artifact)
            if not model.pipeline_id and model.pipeline_run_id:
                run = self.pipelines.get_run(model.pipeline_run_id)
                if run is not None and run.owner_id == principal.user_id:
                    model.pipeline_id = run.pipeline_id
                    model.lineage = {**model.lineage, "pipeline_id": run.pipeline_id}
            self._enrich_batch_scoring_contract(model)
            model.logical_id = model.logical_id or self._logical_model_id(model)
            pipeline_models.append(model)
        known = {item.id for item in pipeline_models}
        models = [
            *pipeline_models,
            *(item for item in self.repository.list_models(principal.user_id) if item.id not in known),
        ]
        self._assign_version_numbers(models)
        return sorted(models, key=lambda item: (item.created_at, item.id), reverse=True)

    def get_model(self, model_id: str, principal: Principal) -> ModelArtifact:
        model = next((item for item in self.list_models(principal) if item.id == model_id), None)
        if model is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        return model

    def list_versions(self, logical_id: str, principal: Principal) -> list[ModelArtifact]:
        versions = [
            item for item in self.list_models(principal)
            if item.logical_id == logical_id
        ]
        if not versions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logical model not found")
        return sorted(versions, key=lambda item: item.version_number)

    def promote_model(
        self,
        model_id: str,
        payload: PromoteModelRequest,
        principal: Principal,
    ) -> ModelArtifact:
        model = self.get_model(model_id, principal)
        model.stage = payload.stage
        return self.repository.update_model(model)

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

    def _enrich_batch_scoring_contract(self, model: ModelArtifact) -> None:
        if model.pipeline_run_id:
            candidates = self.artifacts.list_artifacts(
                model.owner_id,
                ArtifactType.FEATURE_TRANSFORM,
            )
            fitted = next(
                (
                    artifact
                    for artifact in candidates
                    if str(
                        dict(artifact.metadata.get("lineage") or {}).get(
                            "pipeline_run_id"
                        )
                    )
                    == model.pipeline_run_id
                ),
                None,
            )
            if fitted is not None:
                model.fitted_transform_artifact_id = fitted.id

        if not model.pipeline_version_id:
            return
        version = self.pipelines.get_version(model.pipeline_version_id)
        if version is None or version.owner_id != model.owner_id:
            return
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
            elif step.get("type") == "feature_engineering":
                model.feature_engineering_definition = dict(nested)

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
            metrics={
                str(key): float(value)
                for key, value in dict(metadata.get("metrics") or {}).items()
                if isinstance(value, (int, float))
            },
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
