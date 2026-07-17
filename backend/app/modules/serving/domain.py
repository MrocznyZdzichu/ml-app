from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DeploymentStatus(str, Enum):
    REQUESTED = "requested"
    BUILDING = "building"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class BatchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Deployment:
    id: str
    owner_id: str
    model_id: str
    name: str
    image: str
    business_case_id: str = ""
    endpoint_url: str | None = None
    status: DeploymentStatus = DeploymentStatus.REQUESTED
    environment: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
