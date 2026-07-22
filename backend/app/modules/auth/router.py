from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.auth.schemas import (
    ApiCredentialCreate,
    ApiCredentialCreated,
    ApiCredentialRead,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.modules.auth.api_credentials import ApiCredentialService
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
service = AuthService()
credential_service = ApiCredentialService()


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


def _credential_read(value, token: str | None = None):
    payload = {
        "id": value.id, "user_id": value.user_id, "name": value.name,
        "expires_at": value.expires_at, "revoked_at": value.revoked_at,
        "last_used_at": value.last_used_at, "created_at": value.created_at,
    }
    return ApiCredentialCreated(**payload, token=token) if token is not None else ApiCredentialRead(**payload)


@router.get("/api-credentials", response_model=list[ApiCredentialRead])
def list_api_credentials(principal: Principal = Depends(require_user)) -> list[ApiCredentialRead]:
    return [_credential_read(item) for item in credential_service.repository.list_for_user(principal.user_id)]


@router.post("/api-credentials", response_model=ApiCredentialCreated, status_code=201)
def create_api_credential(
    payload: ApiCredentialCreate,
    principal: Principal = Depends(require_user),
) -> ApiCredentialCreated:
    credential, token = credential_service.create(payload.name, payload.expires_at, principal)
    return _credential_read(credential, token)


@router.delete("/api-credentials/{credential_id}", status_code=204)
def revoke_api_credential(
    credential_id: str,
    principal: Principal = Depends(require_user),
) -> None:
    credential_service.revoke(credential_id, principal)
