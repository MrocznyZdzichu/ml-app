from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


DataAssetDrillOperator = Literal[
    "contains", "equals", "not_equals", "in", "regex", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "between", "empty", "not_empty",
]


class DataAssetDrillFilter(BaseModel):
    operator: DataAssetDrillOperator
    value: str = ""
    values: list[str] = Field(default_factory=list, max_length=1_000)
    upper_inclusive: bool = False

    @model_validator(mode="after")
    def validate_operator_values(self) -> Self:
        if self.operator == "between" and len(self.values) != 2:
            raise ValueError("Between drill filters require exactly two values")
        return self


class DataAssetDrillRequest(BaseModel):
    filters: dict[str, DataAssetDrillFilter] = Field(min_length=1, max_length=20)
    limit: int = Field(default=50_000, ge=1, le=50_000)


VisualizationKind = Literal["line", "bar", "scatter", "histogram", "boxplot", "kpi"]
VisualizationAggregation = Literal["average", "median", "std", "sum", "count", "min", "max"]
VisualizationTrend = Literal["none", "linear", "spline", "polynomial", "exponential"]
VisualizationFittedTrend = Literal["linear", "spline", "polynomial", "exponential"]


class DataAssetVisualizationRequest(BaseModel):
    kind: VisualizationKind
    x: str = ""
    y: str = ""
    group: str = ""
    aggregations: list[VisualizationAggregation] = Field(default_factory=lambda: ["average"], max_length=7)
    selected_groups: list[str] | None = Field(default=None, max_length=1_000)
    x_epsilon: float = Field(default=0, ge=0, le=1e100)
    y_epsilon: float = Field(default=0, ge=0, le=1e100)
    trend: VisualizationTrend = "none"
    polynomial_degree: int = Field(default=2, ge=2, le=5)
    max_points: int = Field(default=2_000, ge=50, le=10_000)
    bins: int = Field(default=80, ge=20, le=200)


class DataAssetVisualizationPointRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    x: float
    y: float
    x_label: str = Field(alias="xLabel")
    series: str
    group: str | None = None
    aggregation: VisualizationAggregation | None = None
    count: int | None = None
    x_range: tuple[float, float] | None = Field(default=None, alias="xRange")
    y_range: tuple[float, float] | None = Field(default=None, alias="yRange")
    x_range_inclusive: bool = Field(default=False, alias="xRangeInclusive")
    y_range_inclusive: bool = Field(default=False, alias="yRangeInclusive")
    minimum: float | None = None
    q1: float | None = None
    median: float | None = None
    q3: float | None = None
    maximum: float | None = None
    lower_whisker: float | None = Field(default=None, alias="lowerWhisker")
    upper_whisker: float | None = Field(default=None, alias="upperWhisker")
    outlier_count: int | None = Field(default=None, alias="outlierCount")


class DataAssetVisualizationTrendPointRead(BaseModel):
    x: float
    y: float


class DataAssetVisualizationTrendRead(BaseModel):
    series: str
    kind: VisualizationFittedTrend
    valid_count: int
    points: list[DataAssetVisualizationTrendPointRead] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    r_squared: float | None = None
    fit_space: Literal["y", "log_y", "binned_y"]
    approximate: bool = False


class DataAssetVisualizationRead(BaseModel):
    dataset_id: str
    row_count: int
    scanned_row_count: int
    points: list[DataAssetVisualizationPointRead] = Field(default_factory=list)
    trends: list[DataAssetVisualizationTrendRead] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)
    kpi: float | None = None
    valid_count: int = 0
    execution_mode: Literal["full_dataset"] = "full_dataset"
    truncated: bool = False
    approximate: bool = False
    approximation_method: Literal["binned_gaussian_kde"] | None = None


class DataAssetVisualizationGroupsRequest(BaseModel):
    column: str
    limit: int = Field(default=100, ge=1, le=1_000)


class DataAssetVisualizationGroupsRead(BaseModel):
    dataset_id: str
    values: list[str]
    truncated: bool = False
