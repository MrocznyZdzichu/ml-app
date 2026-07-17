from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.sharing.domain import (
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
