from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ScoringReport:
    id: str
    owner_id: str
    name: str
    logical_id: str
    version_number: int
    business_case_id: str
    pipeline_id: str
    pipeline_version_id: str
    pipeline_run_id: str
    pipeline_step_id: str
    problem_type: str
    prediction_dataset_id: str = ""
    prediction_artifact_id: str = ""
    model_artifact_id: str = ""
    evaluated_row_count: int = 0
    evaluation: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
