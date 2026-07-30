from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.sharing.domain import (
    AccessRequestStatus,
    BusinessCaseAccessRole,
    MembershipRole,
    ResourceAccessRole,
    ResourceKind,
    SubjectType,
)


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class GroupUpdate(GroupCreate):
    is_active: bool = True


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    is_active: bool
    owner_id: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class MembershipUpsert(BaseModel):
    user_id: str
    membership_role: MembershipRole = MembershipRole.MEMBER


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    group_id: str
    user_id: str
    membership_role: MembershipRole
    added_by: str
    created_at: datetime


class BusinessCaseGrantCreate(BaseModel):
    subject_type: SubjectType
    subject_id: str
    access_role: BusinessCaseAccessRole
    expires_at: datetime | None = None


class BusinessCaseGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    business_case_id: str
    subject_type: SubjectType
    subject_id: str
    access_role: BusinessCaseAccessRole
    granted_by: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    subject_name: str = ""
    subject_email: str = ""
    business_case_name: str = ""


class BusinessCaseAccessRequestCreate(BaseModel):
    requested_role: BusinessCaseAccessRole = BusinessCaseAccessRole.READER
    justification: str = Field(min_length=1, max_length=2000)

    @field_validator("justification")
    @classmethod
    def require_non_blank_justification(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("justification cannot be blank")
        return normalized


class BusinessCaseAccessRequestDecision(BaseModel):
    access_role: BusinessCaseAccessRole
    decision_note: str = Field(default="", max_length=2000)


class BusinessCaseAccessRequestReject(BaseModel):
    decision_note: str = Field(default="", max_length=2000)


class BusinessCaseAccessRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    business_case_id: str
    requester_id: str
    requested_role: BusinessCaseAccessRole
    justification: str
    status: AccessRequestStatus
    created_at: datetime
    decided_at: datetime | None
    decided_by: str
    granted_role: BusinessCaseAccessRole | None
    decision_note: str
    business_case_name: str
    requester_display_name: str
    requester_email: str


class ResourceGrantCreate(BaseModel):
    resource_kind: ResourceKind
    resource_id: str
    subject_type: SubjectType
    subject_id: str
    access_role: ResourceAccessRole
    expires_at: datetime | None = None


class ResourceGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    resource_kind: ResourceKind
    resource_id: str
    subject_type: SubjectType
    subject_id: str
    access_role: ResourceAccessRole
    granted_by: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


class DirectoryUserRead(BaseModel):
    id: str
    login_name: str
    email: str
    display_name: str
    is_active: bool


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str
    action: str
    subject_type: str
    subject_id: str
    resource_kind: str
    resource_id: str
    previous_state: dict
    new_state: dict
    reason: str
    request_id: str
    created_at: datetime
