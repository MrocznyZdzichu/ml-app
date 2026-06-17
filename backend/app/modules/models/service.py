from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.models.domain import ModelArtifact, TrainingJob
from app.modules.models.repository import InMemoryModelRepository, ModelRepository
from app.modules.models.schemas import PromoteModelRequest, TrainingRequest


class ModelService:
    def __init__(self, repository: ModelRepository | None = None) -> None:
        self.repository = repository or InMemoryModelRepository()

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
        return self.repository.list_models(principal.user_id)

    def get_model(self, model_id: str, principal: Principal) -> ModelArtifact:
        model = self.repository.get_model(model_id)
        if not model or model.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        return model

    def promote_model(
        self,
        model_id: str,
        payload: PromoteModelRequest,
        principal: Principal,
    ) -> ModelArtifact:
        model = self.get_model(model_id, principal)
        model.stage = payload.stage
        return self.repository.update_model(model)
