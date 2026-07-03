from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PipelineType(str, Enum):
    DATA_PREPARATION = "data_preparation"
    FEATURE_ENGINEERING = "feature_engineering"
    TRAINING = "training"
    BATCH_SCORING = "batch_scoring"
    MONITORING = "monitoring"
    CUSTOM = "custom"


class PipelineStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ABANDONED = "abandoned"
    ARCHIVED = "archived"


class PipelineVersionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PipelineRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineRunTrigger(str, Enum):
    MANUAL = "manual"
    API = "api"
    SCHEDULE = "schedule"


class PipelineStepType(str, Enum):
    SELECT_COLUMNS = "select_columns"
    ADD_IDENTIFIER = "add_identifier"
    RENAME_COLUMNS = "rename_columns"
    CAST_COLUMNS = "cast_columns"
    FILTER_ROWS = "filter_rows"
    SORT_ROWS = "sort_rows"
    DEDUPLICATE = "deduplicate"
    JOIN = "join"
    UNION = "union"
    DERIVE_COLUMN = "derive_column"
    IMPUTE_MISSING = "impute_missing"
    AGGREGATE = "aggregate"
    MAP_CATEGORIES = "map_categories"
    CUSTOM_SQL = "custom_sql"
    ENCODE_CATEGORICAL = "encode_categorical"
    SCALE_NUMERIC = "scale_numeric"
    TRAIN_MODEL = "train_model"
    SCORE_MODEL = "score_model"
    EVALUATE_MODEL = "evaluate_model"
    QUALITY_CHECK = "quality_check"
    CUSTOM = "custom"


@dataclass
class Pipeline:
    id: str
    owner_id: str
    business_case_id: str
    name: str
    description: str = ""
    type: PipelineType = PipelineType.CUSTOM
    status: PipelineStatus = PipelineStatus.DRAFT
    created_by: str = ""
    updated_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latest_published_version_number: int | None = None
    published_version_count: int = 0
    draft_version_number: int | None = None


@dataclass
class PipelineVersion:
    id: str
    owner_id: str
    pipeline_id: str
    business_case_id: str
    version_number: int
    status: PipelineVersionStatus
    definition: dict[str, Any]
    definition_hash: str
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_by: str = ""
    published_at: datetime | None = None


@dataclass
class PipelineRun:
    id: str
    owner_id: str
    pipeline_id: str
    pipeline_version_id: str
    business_case_id: str
    status: PipelineRunStatus
    trigger_type: PipelineRunTrigger
    runtime_parameters: dict[str, Any] = field(default_factory=dict)
    is_dry_run: bool = False
    requested_step_id: str = ""
    input_row_count: int | None = None
    processed_row_count: int | None = None
    output_row_count: int | None = None
    rejected_row_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    output_artifact_ids: list[str] = field(default_factory=list)
    output_manifest: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class PipelineStepRun:
    id: str
    owner_id: str
    pipeline_run_id: str
    pipeline_step_id: str
    step_type: str
    status: PipelineRunStatus
    input_row_count: int | None = None
    processed_row_count: int | None = None
    output_row_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    output_manifest: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
