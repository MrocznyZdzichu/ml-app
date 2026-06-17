from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.exports.domain import ExportFormat, ExportKind, ExportStatus


class ExportRequest(BaseModel):
    resource_kind: ExportKind
    resource_id: str
    format: ExportFormat
    options: dict[str, Any] = Field(default_factory=dict)


class ExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    resource_kind: ExportKind
    resource_id: str
    format: ExportFormat
    status: ExportStatus
    output_uri: str | None
    options: dict[str, Any]
    created_at: datetime
