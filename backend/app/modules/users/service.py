from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal, hash_password
from app.modules.auth.domain import UserAccount
from app.modules.auth.repository import PostgresUserRepository
from app.modules.sharing.domain import AuditEvent
from app.modules.sharing.repository import PostgresSharingRepository
from app.modules.users.schemas import AdminPasswordReset, AdminUserUpdate


PLATFORM_ROLES = {"user", "governance_steward", "administrator"}


class UserAdministrationService:
    def __init__(self) -> None:
        self.users = PostgresUserRepository()
        self.audit = PostgresSharingRepository(self.users.engine)

    @staticmethod
    def require_admin(principal: Principal) -> None:
        if not principal.is_administrator:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")

    def list_users(self, principal: Principal) -> list[UserAccount]:
        self.require_admin(principal)
        return self.users.list_all()

    def update_user(self, user_id: str, payload: AdminUserUpdate, principal: Principal) -> UserAccount:
        self.require_admin(principal)
        user = self.users.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        roles = set(payload.roles)
        if not roles or "user" not in roles or not roles <= PLATFORM_ROLES:
            raise HTTPException(status_code=422, detail="Roles must contain user and only supported platform roles")
        if user.id == "root" and (not payload.is_active or "administrator" not in roles):
            raise HTTPException(status_code=409, detail="Root cannot be disabled or demoted")
        previous = {"roles": list(user.roles), "is_active": user.is_active}
        changed = set(user.roles) != roles or user.is_active != payload.is_active
        user.roles = tuple(role for role in ("user", "governance_steward", "administrator") if role in roles)
        user.is_active = payload.is_active
        user.updated_at = datetime.now(timezone.utc)
        if changed:
            user.session_version += 1
        self.users.update(user)
        self._audit(principal, "user.updated", user.id, previous, {
            "roles": list(user.roles), "is_active": user.is_active,
        })
        return user

    def reset_password(self, user_id: str, payload: AdminPasswordReset, principal: Principal) -> None:
        self.require_admin(principal)
        user = self.users.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = hash_password(payload.new_password)
        user.session_version += 1
        user.updated_at = datetime.now(timezone.utc)
        self.users.update(user)
        self._audit(principal, "user.password_reset", user.id, {}, {"sessions_invalidated": True})

    def _audit(self, principal: Principal, action: str, subject_id: str, previous: dict, new: dict) -> None:
        self.audit.add_audit(AuditEvent(
            id=str(uuid4()), actor_id=principal.user_id, action=action,
            subject_type="user", subject_id=subject_id,
            previous_state=previous, new_state=new,
        ))
