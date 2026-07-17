from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import (
    Principal,
    create_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.domain import UserAccount
from app.modules.auth.repository import (
    DuplicateEmailError,
    PostgresUserRepository,
    UserRepository,
)
from app.modules.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.modules.sharing.domain import AuditEvent
from app.modules.sharing.repository import PostgresSharingRepository


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
            login_name=email,
            display_name=display_name,
            password_hash=hash_password(payload.password),
            roles=("user",),
        )
        try:
            self.repository.add(user)
        except DuplicateEmailError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            ) from exc
        return self._token_for(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.repository.get_by_login(payload.login)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )
        if user.id == "root":
            PostgresSharingRepository().add_audit(AuditEvent(
                id=str(uuid4()), actor_id=user.id, action="root.login",
                subject_type="user", subject_id=user.id,
            ))
        return self._token_for(user)

    def profile(self, principal: Principal) -> UserProfile:
        user = self.repository.get(principal.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
        return UserProfile(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            login_name=user.login_name,
            roles=list(user.roles),
            is_active=user.is_active,
            uses_initial_password=(user.id == "root" and verify_password("toor", user.password_hash)),
        )

    def change_password(self, payload: PasswordChangeRequest, principal: Principal) -> None:
        user = self.repository.get(principal.user_id)
        if user is None or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is invalid")
        user.password_hash = hash_password(payload.new_password)
        user.session_version += 1
        user.updated_at = datetime.now(timezone.utc)
        self.repository.update(user)
        PostgresSharingRepository().add_audit(AuditEvent(
            id=str(uuid4()), actor_id=user.id, action="user.password_changed",
            subject_type="user", subject_id=user.id,
            new_state={"sessions_invalidated": True},
        ))

    def _token_for(self, user: UserAccount) -> TokenResponse:
        principal = Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            login_name=user.login_name,
            roles=user.roles,
            session_version=user.session_version,
        )
        return TokenResponse(
            access_token=create_access_token(principal),
            user_id=user.id,
            email=user.email,
            login_name=user.login_name,
        )
