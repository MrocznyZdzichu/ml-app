from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class SubjectType(str, Enum):
    USER = "user"
    GROUP = "group"


class BusinessCaseAccessRole(str, Enum):
    REPORT_VIEWER = "report_viewer"
    READER = "reader"
    CONTRIBUTOR = "contributor"
    MANAGER = "manager"
    OWNER = "owner"


class ResourceAccessRole(str, Enum):
    READER = "reader"
    EDITOR = "editor"
    OWNER = "owner"


class ResourceKind(str, Enum):
    DATASET = "dataset"
    DATA_VIEW = "data_view"
    ANALYSIS = "analysis"
    REPORT = "report"


class MembershipRole(str, Enum):
    MEMBER = "member"
    MANAGER = "manager"
    OWNER = "owner"


@dataclass
class AccessGroup:
    id: str
    name: str
    description: str
    is_active: bool
    owner_id: str
    created_by: str
    updated_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GroupMembership:
    id: str
    group_id: str
    user_id: str
    membership_role: MembershipRole
    added_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BusinessCaseGrant:
    id: str
    business_case_id: str
    subject_type: SubjectType
    subject_id: str
    access_role: BusinessCaseAccessRole
    granted_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


@dataclass
class ResourceGrant:
    id: str
    resource_kind: ResourceKind
    resource_id: str
    subject_type: SubjectType
    subject_id: str
    access_role: ResourceAccessRole
    granted_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


@dataclass
class AuditEvent:
    id: str
    actor_id: str
    action: str
    subject_type: str = ""
    subject_id: str = ""
    resource_kind: str = ""
    resource_id: str = ""
    previous_state: dict[str, Any] = field(default_factory=dict)
    new_state: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


BC_ROLE_RANK = {
    BusinessCaseAccessRole.REPORT_VIEWER: 10,
    BusinessCaseAccessRole.READER: 20,
    BusinessCaseAccessRole.CONTRIBUTOR: 30,
    BusinessCaseAccessRole.MANAGER: 40,
    BusinessCaseAccessRole.OWNER: 50,
}

RESOURCE_ROLE_RANK = {
    ResourceAccessRole.READER: 20,
    ResourceAccessRole.EDITOR: 30,
    ResourceAccessRole.OWNER: 50,
}
