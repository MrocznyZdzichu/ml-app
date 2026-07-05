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
    logical_id: str
    version_number: int
    algorithm: str
    artifact_uri: str
    metrics: dict[str, float]
    stage: ModelStage
    business_case_id: str
    pipeline_id: str
    pipeline_version_id: str
    pipeline_run_id: str
    pipeline_step_id: str
    problem_type: str
    target_column: str
    feature_columns: list[str]
    model_hash: str
    training_config: dict[str, Any]
    model_parameters: dict[str, Any]
    lineage: dict[str, Any]
    fitted_transform_artifact_id: str
    data_engineering_definition: dict[str, Any]
    feature_engineering_definition: dict[str, Any]
    created_at: datetime


class PromoteModelRequest(BaseModel):
    stage: ModelStage


class DatasetLineageRead(BaseModel):
    artifact_id: str
    artifact_type: str
    dataset_id: str
    logical_id: str
    version_number: int
    name: str
    role: str
    stage: str
    format: str
    row_count: int | None
    pipeline_step_id: str
    pipeline_run_id: str
    depth: int
