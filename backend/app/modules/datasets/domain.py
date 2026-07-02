from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SourceType(str, Enum):
    FILE = "file"
    DATABASE = "database"
    API = "api"
    VIEW = "view"


class DataAssetStatus(str, Enum):
    DRAFT = "draft"
    PROFILING = "profiling"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass
class DataAsset:
    id: str
    owner_id: str
    name: str
    source_type: SourceType
    format: str
    logical_id: str = ""
    version_number: int = 1
    version_stage: str = "source"
    description: str = ""
    original_filename: str | None = None
    location_uri: str | None = None
    file_size_bytes: int | None = None
    row_count: int | None = None
    has_header: bool | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None
    deleted_by: str | None = None
    deleted_at: datetime | None = None
    status: DataAssetStatus = DataAssetStatus.DRAFT
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.logical_id:
            self.logical_id = self.id
