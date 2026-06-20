from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.datasets.domain import DataAssetStatus, SourceType


class DatabaseConnection(BaseModel):
    engine: str = Field(examples=["postgresql", "mysql", "sqlserver"])
    host: str
    port: int
    database: str
    username: str
    secret_ref: str | None = None


class ApiConnection(BaseModel):
    base_url: str
    auth_ref: str | None = None


class DataAssetCreate(BaseModel):
    name: str
    source_type: SourceType
    format: str = "csv"
    description: str = ""
    location_uri: str | None = None
    database: DatabaseConnection | None = None
    api: ApiConnection | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_dataset_id: str = Field(min_length=1)
    definition: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class DataAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    source_type: SourceType
    format: str
    description: str
    original_filename: str | None = None
    location_uri: str | None
    file_size_bytes: int | None = None
    row_count: int | None = None
    has_header: bool | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None
    deleted_by: str | None = None
    deleted_at: datetime | None = None
    status: DataAssetStatus
    tags: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DataAssetMetadataUpdate(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataAssetProfileRequest(BaseModel):
    sample_size: int = Field(default=1000, ge=10, le=1_000_000)
    include_correlations: bool = True


class DataAssetProfileRead(BaseModel):
    dataset_id: str
    status: str
    sample_size: int
    include_correlations: bool
    artifact_uri: str | None = None


class FullDescriptiveProfileRequest(BaseModel):
    target_column: str = ""
    target_type: Literal["categorical", "continuous"] = "categorical"
    comparison_column: str = ""
    comparison_type: Literal["categorical", "continuous"] = "categorical"
    include_summary: bool = True
    include_univariate: bool = True
    include_target_relations: bool = True
    include_segments: bool = True
    include_graphic_summaries: bool = True
    row_limit: int = Field(default=50_000, ge=100, le=1_000_000)
    max_target_features: int = Field(default=30, ge=1, le=500)
    max_segment_features: int = Field(default=4, ge=2, le=20)


class DataAssetColumnRead(BaseModel):
    name: str
    type: Literal["text", "number", "date", "boolean", "empty", "mixed", "unsupported"]


class FullDescriptiveProfileRead(BaseModel):
    dataset_id: str
    columns: list[DataAssetColumnRead]
    row_count: int
    profile: dict[str, Any]


class FullDescriptiveProfileJobRead(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    result: FullDescriptiveProfileRead | None = None
    error: str | None = None


class DataAssetPreviewRead(BaseModel):
    dataset_id: str
    columns: list[DataAssetColumnRead]
    records: list[dict[str, Any]]
    row_count: int
    returned_count: int
    limit: int


class DataAssetSqlQueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    limit: int = Field(default=50_000, ge=1, le=50_000)


VisualizationKind = Literal["line", "bar", "scatter", "histogram", "kpi"]
VisualizationAggregation = Literal["average", "median", "std", "sum", "count", "min", "max"]


class DataAssetVisualizationRequest(BaseModel):
    kind: VisualizationKind
    x: str = ""
    y: str = ""
    group: str = ""
    aggregations: list[VisualizationAggregation] = Field(default_factory=lambda: ["average"], max_length=7)
    selected_groups: list[str] | None = None
    max_points: int = Field(default=2_000, ge=50, le=10_000)
    bins: int = Field(default=16, ge=5, le=100)


class DataAssetVisualizationRead(BaseModel):
    dataset_id: str
    row_count: int
    scanned_row_count: int
    points: list[dict[str, Any]] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)
    kpi: float | None = None
    valid_count: int = 0
    execution_mode: Literal["full_dataset"] = "full_dataset"
    truncated: bool = False


class DataAssetVisualizationGroupsRequest(BaseModel):
    column: str
    limit: int = Field(default=100, ge=1, le=1_000)


class DataAssetVisualizationGroupsRead(BaseModel):
    dataset_id: str
    values: list[str]
    truncated: bool = False
