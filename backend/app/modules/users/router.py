from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.users.schemas import AdminPasswordReset, AdminUserUpdate, UserRead
from app.modules.users.service import UserAdministrationService
from app.shared.pagination import OffsetPage

router = APIRouter(prefix="/users", tags=["users"])
service = UserAdministrationService()


def _user_read(user) -> UserRead:
    return UserRead(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=list(user.roles),
        login_name=user.login_name,
        is_active=user.is_active,
        is_technical=user.is_technical,
        session_version=user.session_version,
        created_at=user.created_at,
    )


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
    return [_user_read(user) for user in service.list_users(principal)]


@router.get("/page", response_model=OffsetPage[UserRead])
def page_users(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    is_active: bool | None = Query(default=None),
    is_technical: bool | None = Query(default=None),
    principal: Principal = Depends(require_user),
) -> OffsetPage[UserRead]:
    users, total = service.page_users(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        is_active=is_active,
        is_technical=is_technical,
    )
    return OffsetPage[UserRead].build(
        items=[_user_read(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: AdminUserUpdate, principal: Principal = Depends(require_user)) -> UserRead:
    user = service.update_user(user_id, payload, principal)
    return _user_read(user)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: str, payload: AdminPasswordReset, principal: Principal = Depends(require_user)) -> None:
    service.reset_password(user_id, payload, principal)
