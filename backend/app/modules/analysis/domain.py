from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AnalysisKind(str, Enum):
    DESCRIPTIVE_STATS = "descriptive_stats"
    VISUALIZATION = "visualization"
    FEATURE_EXPLORATION = "feature_exploration"


class AnalysisStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AnalysisJob:
    id: str
    owner_id: str
    dataset_id: str
    kind: AnalysisKind
    title: str
    status: AnalysisStatus = AnalysisStatus.QUEUED
    parameters: dict[str, Any] = field(default_factory=dict)
    artifact_uri: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
