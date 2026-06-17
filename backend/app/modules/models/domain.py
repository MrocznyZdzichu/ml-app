from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TrainingStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class ModelStage(str, Enum):
    CANDIDATE = "candidate"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


@dataclass
class TrainingJob:
    id: str
    owner_id: str
    dataset_id: str
    target_column: str
    algorithm: str
    feature_columns: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    status: TrainingStatus = TrainingStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModelArtifact:
    id: str
    owner_id: str
    training_job_id: str
    name: str
    version: str
    algorithm: str
    artifact_uri: str
    metrics: dict[str, float] = field(default_factory=dict)
    stage: ModelStage = ModelStage.CANDIDATE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
