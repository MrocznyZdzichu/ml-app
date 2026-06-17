from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.serving.domain import BatchJobStatus, DeploymentStatus


class DeploymentCreate(BaseModel):
    model_id: str
    name: str
    image: str = "ml-app/model-runtime:latest"
    environment: dict[str, str] = Field(default_factory=dict)


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    model_id: str
    name: str
    image: str
    endpoint_url: str | None
    status: DeploymentStatus
    environment: dict[str, str]
    created_at: datetime


class ScoreRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1)


class ScoreResponse(BaseModel):
    deployment_id: str
    predictions: list[dict[str, Any]]


class BatchScoreRequest(BaseModel):
    input_uri: str
    output_uri: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class BatchScoreJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    deployment_id: str
    input_uri: str
    output_uri: str | None
    status: BatchJobStatus
    options: dict[str, Any]
    created_at: datetime
