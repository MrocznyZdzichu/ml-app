from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.sharing.domain import Permission, ShareableKind


class ShareGrantCreate(BaseModel):
    target_user_id: str
    resource_kind: ShareableKind
    resource_id: str
    permission: Permission = Permission.READ


class ShareGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    target_user_id: str
    resource_kind: ShareableKind
    resource_id: str
    permission: Permission
    created_at: datetime
