from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import (
    Principal,
    create_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.domain import UserAccount
from app.modules.auth.repository import PostgresUserRepository, UserRepository
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserProfile


class AuthService:
    """Owns account registration, password verification, and token issuance."""

    def __init__(self, repository: UserRepository | None = None) -> None:
        self.repository = repository or PostgresUserRepository()

    def register(self, payload: RegisterRequest) -> TokenResponse:
        email = payload.email.lower()
        if self.repository.get_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        display_name = payload.display_name.strip() or email.split("@")[0]
        user = UserAccount(
            id=str(uuid4()),
            email=email,
            display_name=display_name,
            password_hash=hash_password(payload.password),
        )
        self.repository.add(user)
        return self._token_for(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.repository.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        return self._token_for(user)

    def profile(self, principal: Principal) -> UserProfile:
        return UserProfile(
            user_id=principal.user_id,
            email=principal.email,
            display_name=principal.display_name,
            roles=list(principal.roles),
        )

    def _token_for(self, user: UserAccount) -> TokenResponse:
        principal = Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            roles=user.roles,
        )
        return TokenResponse(
            access_token=create_access_token(principal),
            user_id=user.id,
            email=user.email,
        )
