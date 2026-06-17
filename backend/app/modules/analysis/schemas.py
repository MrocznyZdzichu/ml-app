from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.analysis.domain import AnalysisKind, AnalysisStatus


class AnalysisCreate(BaseModel):
    dataset_id: str
    kind: AnalysisKind
    title: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    dataset_id: str
    kind: AnalysisKind
    title: str
    status: AnalysisStatus
    parameters: dict[str, Any]
    artifact_uri: str | None
    created_at: datetime


class InlineRecordsRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1)


class ColumnStats(BaseModel):
    count: int
    missing: int
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    unique: int | None = None


class DescriptiveStatsResponse(BaseModel):
    row_count: int
    columns: dict[str, ColumnStats]
