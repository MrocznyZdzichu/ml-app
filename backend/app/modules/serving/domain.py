from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DeploymentStatus(str, Enum):
    REQUESTED = "requested"
    BUILDING = "building"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class DeploymentRole(str, Enum):
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    SHADOW = "shadow"
    FALLBACK = "fallback"


class InferenceStatus(str, Enum):
    ACCEPTED = "accepted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BatchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class ReplayStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ModelAssignment:
    model_id: str
    role: DeploymentRole


@dataclass
class Deployment:
    id: str
    owner_id: str
    business_case_id: str
    name: str
    slug: str
    status: DeploymentStatus = DeploymentStatus.RUNNING
    active_revision_id: str = ""
    endpoint_url: str | None = None
    retention_days: int = 365
    created_by: str = ""
    updated_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DeploymentRevision:
    id: str
    deployment_id: str
    version_number: int
    assignments: list[ModelAssignment]
    created_by: str
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InferenceRequest:
    id: str
    deployment_id: str
    deployment_revision_id: str
    requested_by: str
    correlation_id: str
    idempotency_key: str
    status: InferenceStatus
    record_count: int
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    champion_model_id: str = ""
    served_model_id: str = ""
    served_role: str = ""
    fallback_used: bool = False
    latency_ms: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


@dataclass
class ChallengerReplayJob:
    id: str
    deployment_id: str
    deployment_revision_id: str
    challenger_model_id: str
    requested_by: str
    status: ReplayStatus
    source_before: datetime
    source_since: datetime | None = None
    source_until: datetime | None = None
    max_requests: int = 1000
    processed_requests: int = 0
    processed_records: int = 0
    failed_requests: int = 0
    error_message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class BatchScoreJob:
    id: str
    owner_id: str
    deployment_id: str
    input_uri: str
    business_case_id: str = ""
    output_uri: str | None = None
    status: BatchJobStatus = BatchJobStatus.QUEUED
    options: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
