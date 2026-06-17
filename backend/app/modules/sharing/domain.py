from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ShareableKind(str, Enum):
    DATASET = "dataset"
    ANALYSIS = "analysis"
    MODEL = "model"
    DEPLOYMENT = "deployment"


class Permission(str, Enum):
    READ = "read"
    EDIT = "edit"
    OWNER = "owner"


@dataclass
class ShareGrant:
    id: str
    owner_id: str
    target_user_id: str
    resource_kind: ShareableKind
    resource_id: str
    permission: Permission
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
