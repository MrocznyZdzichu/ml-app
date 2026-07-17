from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BusinessCaseStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class ProblemType(str, Enum):
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"
    FORECASTING = "forecasting"
    CLUSTERING = "clustering"
    ANOMALY_DETECTION = "anomaly_detection"
    CUSTOM = "custom"


class DataRole(str, Enum):
    SOURCE = "source"
    TRAINING = "training"
    VALIDATION = "validation"
    TEST = "test"
    SCORING_INPUT = "scoring_input"
    SCORING_OUTPUT = "scoring_output"
    MONITORING_INPUT = "monitoring_input"
    MONITORING_ACTUALS = "monitoring_actuals"
    REFERENCE = "reference"


class DataArtifactKind(str, Enum):
    DATASET = "dataset"
    DATA_VIEW = "data_view"


class ArtifactType(str, Enum):
    DATASET = "dataset"
    DATA_VIEW = "data_view"
    FEATURE_TRANSFORM = "feature_transform"
    MODEL_VERSION = "model_version"
    REPORT = "report"
    METRICS = "metrics"
    DEPLOYMENT = "deployment"
    PREDICTION_DATASET = "prediction_dataset"


class ArtifactOrigin(str, Enum):
    PLATFORM_GENERATED = "platform_generated"
    UPLOADED = "uploaded"
    EXTERNAL_REGISTERED = "external_registered"


@dataclass
class BusinessCase:
    id: str
    owner_id: str
    name: str
    description: str = ""
    problem_type: ProblemType = ProblemType.CUSTOM
    status: BusinessCaseStatus = BusinessCaseStatus.DRAFT
    business_owner: str = ""
    primary_metric: str = ""
    target_column: str = ""
    business_goal: str = ""
    success_criteria: str = ""
    created_by: str = ""
    updated_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_role: str = "owner"


@dataclass
class Artifact:
    id: str
    owner_id: str
    type: ArtifactType
    reference_id: str
    origin: ArtifactOrigin
    business_case_id: str | None = None
    external_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BusinessCaseDataAttachment:
    id: str
    owner_id: str
    business_case_id: str
    artifact_id: str
    data_asset_id: str
    data_asset_kind: DataArtifactKind
    role: DataRole
    context_note: str = ""
    primary_key_column: str = ""
    target_column: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
