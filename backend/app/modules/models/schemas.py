from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.models.domain import ModelStage, TrainingStatus


class TrainingRequest(BaseModel):
    dataset_id: str
    target_column: str
    algorithm: str = "random_forest"
    feature_columns: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class TrainingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    dataset_id: str
    target_column: str
    algorithm: str
    feature_columns: list[str]
    parameters: dict[str, Any]
    status: TrainingStatus
    created_at: datetime


class ModelArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    training_job_id: str
    name: str
    version: str
    algorithm: str
    artifact_uri: str
    metrics: dict[str, float]
    stage: ModelStage
    created_at: datetime


class PromoteModelRequest(BaseModel):
    stage: ModelStage
