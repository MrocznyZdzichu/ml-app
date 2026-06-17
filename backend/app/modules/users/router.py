from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_current_user(principal: Principal = Depends(require_user)) -> UserRead:
    return UserRead(
        user_id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        roles=list(principal.roles),
    )
