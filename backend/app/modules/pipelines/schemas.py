from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.pipelines.domain import (
    PipelineRunStatus,
    PipelineRunTrigger,
    PipelineStatus,
    PipelineStepType,
    PipelineType,
    PipelineVersionStatus,
)


def default_pipeline_definition() -> dict[str, Any]:
    return {
        "contract_version": "2.0",
        "steps": [],
        "outputs": [],
        "parameters": {},
    }


class PipelineCreate(BaseModel):
    business_case_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    type: PipelineType = PipelineType.CUSTOM
    definition: dict[str, Any] = Field(default_factory=default_pipeline_definition)


class PipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    business_case_id: str
    name: str
    description: str
    type: PipelineType
    status: PipelineStatus
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class PipelineVersionUpdate(BaseModel):
    definition: dict[str, Any]


class PipelineVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    pipeline_id: str
    business_case_id: str
    version_number: int
    status: PipelineVersionStatus
    definition: dict[str, Any]
    definition_hash: str
    created_by: str
    created_at: datetime
    published_by: str
    published_at: datetime | None


class PipelineRunCreate(BaseModel):
    pipeline_version_id: str | None = None
    trigger_type: PipelineRunTrigger = PipelineRunTrigger.MANUAL
    runtime_parameters: dict[str, Any] = Field(default_factory=dict)
    is_dry_run: bool = False
    step_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("trigger_type")
    @classmethod
    def reject_non_manual_execution_for_now(cls, value: PipelineRunTrigger) -> PipelineRunTrigger:
        if value != PipelineRunTrigger.MANUAL:
            raise ValueError("Only manual pipeline runs are executable in the current skeleton")
        return value


class PipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    pipeline_id: str
    pipeline_version_id: str
    business_case_id: str
    status: PipelineRunStatus
    trigger_type: PipelineRunTrigger
    runtime_parameters: dict[str, Any]
    is_dry_run: bool
    requested_step_id: str
    input_row_count: int | None
    processed_row_count: int | None
    output_row_count: int | None
    rejected_row_count: int | None
    warnings: list[str]
    output_artifact_ids: list[str]
    output_manifest: list[dict[str, Any]]
    error_message: str
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PipelineRunOutputPreviewRead(BaseModel):
    output_id: str
    row_count: int
    limit: int
    offset: int
    returned_count: int
    records: list[dict[str, Any]]
    has_next: bool
    has_previous: bool
    columns: list[dict[str, Any]]


class PipelineRunOutputTopValueRead(BaseModel):
    value: Any
    count: int
    share: float


class PipelineRunOutputColumnProfileRead(BaseModel):
    name: str
    null_count: int
    non_null_count: int
    approx_distinct_count: int
    top_values: list[PipelineRunOutputTopValueRead]


class PipelineRunOutputProfileRead(BaseModel):
    output_id: str
    row_count: int
    profiled_column_count: int
    total_column_count: int
    columns: list[PipelineRunOutputColumnProfileRead]


class PipelineStepTypeRead(BaseModel):
    id: PipelineStepType
    label: str
