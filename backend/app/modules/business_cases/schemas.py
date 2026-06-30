from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.business_cases.domain import (
    ArtifactOrigin,
    ArtifactType,
    BusinessCaseStatus,
    DataArtifactKind,
    DataRole,
    ProblemType,
)


class BusinessCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    problem_type: ProblemType = ProblemType.CUSTOM
    status: BusinessCaseStatus = BusinessCaseStatus.DRAFT
    business_owner: str = ""
    primary_metric: str = ""
    target_column: str = ""
    business_goal: str = ""
    success_criteria: str = ""


class BusinessCaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    problem_type: ProblemType = ProblemType.CUSTOM
    status: BusinessCaseStatus = BusinessCaseStatus.DRAFT
    business_owner: str = ""
    primary_metric: str = ""
    target_column: str = ""
    business_goal: str = ""
    success_criteria: str = ""


class BusinessCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    description: str
    problem_type: ProblemType
    status: BusinessCaseStatus
    business_owner: str
    primary_metric: str
    target_column: str
    business_goal: str
    success_criteria: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    type: ArtifactType
    reference_id: str
    origin: ArtifactOrigin
    business_case_id: str | None
    external_notes: str
    metadata: dict[str, Any]
    created_by: str
    created_at: datetime


class BusinessCaseDataAttachmentCreate(BaseModel):
    data_asset_id: str = Field(min_length=1)
    data_asset_kind: DataArtifactKind = DataArtifactKind.DATASET
    role: DataRole
    context_note: str = ""
    primary_key_column: str = ""
    target_column: str = ""
    origin: ArtifactOrigin = ArtifactOrigin.UPLOADED
    external_notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_external_notes_for_blackbox(self) -> "BusinessCaseDataAttachmentCreate":
        if self.origin == ArtifactOrigin.EXTERNAL_REGISTERED and not self.external_notes.strip():
            raise ValueError("external_notes is required for external_registered artifacts")
        return self


class BusinessCaseDataAttachmentUpdate(BaseModel):
    role: DataRole
    context_note: str = ""
    primary_key_column: str = ""
    target_column: str = ""


class BusinessCaseDataAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    business_case_id: str
    artifact_id: str
    data_asset_id: str
    data_asset_kind: DataArtifactKind
    role: DataRole
    context_note: str
    primary_key_column: str
    target_column: str
    created_by: str
    created_at: datetime
