from typing import Protocol

from app.modules.models.domain import ModelArtifact, TrainingJob


class ModelRepository(Protocol):
    def add_training_job(self, job: TrainingJob) -> TrainingJob:
        ...

    def list_training_jobs(self, owner_id: str) -> list[TrainingJob]:
        ...

    def add_model(self, model: ModelArtifact) -> ModelArtifact:
        ...

    def list_models(self, owner_id: str) -> list[ModelArtifact]:
        ...

    def get_model(self, model_id: str) -> ModelArtifact | None:
        ...

    def update_model(self, model: ModelArtifact) -> ModelArtifact:
        ...


class InMemoryModelRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, TrainingJob] = {}
        self._models: dict[str, ModelArtifact] = {}

    def add_training_job(self, job: TrainingJob) -> TrainingJob:
        self._jobs[job.id] = job
        return job

    def list_training_jobs(self, owner_id: str) -> list[TrainingJob]:
        return [job for job in self._jobs.values() if job.owner_id == owner_id]

    def add_model(self, model: ModelArtifact) -> ModelArtifact:
        self._models[model.id] = model
        return model

    def list_models(self, owner_id: str) -> list[ModelArtifact]:
        return [model for model in self._models.values() if model.owner_id == owner_id]

    def get_model(self, model_id: str) -> ModelArtifact | None:
        return self._models.get(model_id)

    def update_model(self, model: ModelArtifact) -> ModelArtifact:
        self._models[model.id] = model
        return model
