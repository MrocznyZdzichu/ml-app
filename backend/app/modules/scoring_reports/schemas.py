from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScoringReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    prediction_dataset_id: str
    prediction_artifact_id: str
    model_artifact_id: str
    evaluated_row_count: int
    evaluation: dict[str, Any]
    lineage: dict[str, Any]
    created_at: datetime


class DatasetLineageRead(BaseModel):
    artifact_id: str
    artifact_type: str
    dataset_id: str
    logical_id: str
    version_number: int
    name: str
    role: str
    stage: str
    format: str
    row_count: int | None
    pipeline_step_id: str
    pipeline_run_id: str
    depth: int
