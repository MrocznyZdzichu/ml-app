from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.serving.domain import (
    BatchJobStatus,
    DeploymentRole,
    DeploymentStatus,
    InferenceStatus,
    ReplayStatus,
)


class ModelAssignmentPayload(BaseModel):
    model_id: str = Field(min_length=1, max_length=64)
    role: DeploymentRole


class DeploymentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    model_id: str = Field(min_length=1, max_length=64)
    retention_days: int = Field(default=365, ge=1, le=3650)


class DeploymentRevisionCreate(BaseModel):
    assignments: list[ModelAssignmentPayload] = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_roles(self) -> "DeploymentRevisionCreate":
        roles = [item.role for item in self.assignments]
        if roles.count(DeploymentRole.CHAMPION) != 1:
            raise ValueError("A deployment revision must contain exactly one champion")
        if roles.count(DeploymentRole.FALLBACK) > 1:
            raise ValueError("A deployment revision may contain at most one fallback")
        model_ids = [item.model_id for item in self.assignments]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("A model may have only one role in a deployment revision")
        return self


class DeploymentStatusUpdate(BaseModel):
    status: DeploymentStatus
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_operator_status(self) -> "DeploymentStatusUpdate":
        if self.status not in {DeploymentStatus.RUNNING, DeploymentStatus.STOPPED}:
            raise ValueError("A user may set deployment status only to running or stopped")
        return self


class DeploymentRollbackRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ModelAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    role: DeploymentRole


class DeploymentRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    version_number: int
    assignments: list[ModelAssignmentRead]
    created_by: str
    reason: str
    created_at: datetime


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    business_case_id: str
    name: str
    slug: str
    status: DeploymentStatus
    active_revision_id: str
    endpoint_url: str | None
    retention_days: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    active_revision: DeploymentRevisionRead | None = None


class ModelServingUsageRead(BaseModel):
    model_id: str
    deployment_id: str
    deployment_name: str
    deployment_slug: str
    deployment_status: DeploymentStatus
    endpoint_url: str | None
    revision_id: str
    revision_version: int
    role: DeploymentRole


class ScoreRecord(BaseModel):
    record_id: str | None = Field(default=None, max_length=512)
    features: dict[str, Any]


class ScoreRequest(BaseModel):
    instances: list[ScoreRecord] = Field(min_length=1, max_length=1000)


class PredictionRead(BaseModel):
    record_id: str
    prediction: Any
    outputs: dict[str, Any] = Field(default_factory=dict)


class ScoreResponse(BaseModel):
    request_id: str
    correlation_id: str
    deployment_id: str
    deployment_revision_id: str
    model_id: str
    served_role: DeploymentRole
    fallback_used: bool
    predictions: list[PredictionRead]
    warnings: list[str] = Field(default_factory=list)


class InferenceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    deployment_revision_id: str
    requested_by: str
    correlation_id: str
    idempotency_key: str
    status: InferenceStatus
    record_count: int
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    warnings: list[str]
    error_code: str
    error_message: str
    champion_model_id: str
    served_model_id: str
    served_role: str
    fallback_used: bool
    latency_ms: int | None
    created_at: datetime
    completed_at: datetime | None


class InferencePage(BaseModel):
    items: list[InferenceRequestRead]
    next_cursor: str | None = None


class InferenceExecutionItem(BaseModel):
    id: str
    request_id: str
    deployment_id: str
    record_id: str
    model_id: str
    role: DeploymentRole
    input: dict[str, Any]
    output: dict[str, Any]
    status: str
    error_message: str
    latency_ms: int | None
    created_at: datetime


class InferenceDetail(BaseModel):
    request: InferenceRequestRead
    executions: list[InferenceExecutionItem]


class ChallengerReplayCreate(BaseModel):
    challenger_model_id: str = Field(min_length=1, max_length=64)
    since: datetime | None = None
    until: datetime | None = None
    max_requests: int = Field(default=1000, ge=1, le=10000)

    @model_validator(mode="after")
    def validate_range(self) -> "ChallengerReplayCreate":
        if self.since and self.until and self.since >= self.until:
            raise ValueError("Replay since must be earlier than until")
        return self


class ChallengerReplayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    deployment_revision_id: str
    challenger_model_id: str
    requested_by: str
    status: ReplayStatus
    source_before: datetime
    source_since: datetime | None
    source_until: datetime | None
    max_requests: int
    processed_requests: int
    processed_records: int
    failed_requests: int
    error_message: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class BatchScoreRequest(BaseModel):
    input_uri: str
    business_case_id: str = ""
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
