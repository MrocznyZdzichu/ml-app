from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.users.schemas import AdminPasswordReset, AdminUserUpdate, UserRead
from app.modules.users.service import UserAdministrationService

router = APIRouter(prefix="/users", tags=["users"])
service = UserAdministrationService()


@router.get("/me", response_model=UserRead)
def read_current_user(principal: Principal = Depends(require_user)) -> UserRead:
    return UserRead(
        user_id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        roles=list(principal.roles),
        login_name=principal.login_name,
    )


@router.get("", response_model=list[UserRead])
def list_users(principal: Principal = Depends(require_user)) -> list[UserRead]:
    return [UserRead(
        user_id=user.id, email=user.email, display_name=user.display_name,
        roles=list(user.roles), login_name=user.login_name, is_active=user.is_active,
        is_technical=user.is_technical, session_version=user.session_version,
        created_at=user.created_at,
    ) for user in service.list_users(principal)]


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: AdminUserUpdate, principal: Principal = Depends(require_user)) -> UserRead:
    user = service.update_user(user_id, payload, principal)
    return UserRead(
        user_id=user.id, email=user.email, display_name=user.display_name,
        roles=list(user.roles), login_name=user.login_name, is_active=user.is_active,
        is_technical=user.is_technical, session_version=user.session_version,
        created_at=user.created_at,
    )


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: str, payload: AdminPasswordReset, principal: Principal = Depends(require_user)) -> None:
    service.reset_password(user_id, payload, principal)
