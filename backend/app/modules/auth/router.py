from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
service = AuthService()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    return service.login(payload)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest) -> TokenResponse:
    return service.register(payload)


@router.get("/me", response_model=UserProfile)
def me(principal: Principal = Depends(require_user)) -> UserProfile:
    return service.profile(principal)


@router.post("/change-password", status_code=204)
def change_password(
    payload: PasswordChangeRequest,
    principal: Principal = Depends(require_user),
) -> None:
    service.change_password(payload, principal)
