from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExportKind(str, Enum):
    DATASET = "dataset"
    ANALYSIS = "analysis"
    MODEL = "model"
    REPORT = "report"


class ExportFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    PICKLE = "pickle"


class ExportStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ExportJob:
    id: str
    owner_id: str
    resource_kind: ExportKind
    resource_id: str
    format: ExportFormat
    status: ExportStatus = ExportStatus.QUEUED
    output_uri: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
