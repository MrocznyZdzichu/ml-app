from datetime import datetime

from pydantic import AliasChoices, BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = ""


class LoginRequest(BaseModel):
    login: str = Field(
        min_length=1,
        max_length=320,
        validation_alias=AliasChoices("login", "email"),
    )
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    login_name: str


class ApiCredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None


class ApiCredentialRead(BaseModel):
    id: str
    user_id: str
    name: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class ApiCredentialCreated(ApiCredentialRead):
    token: str


class UserProfile(BaseModel):
    user_id: str
    email: str
    display_name: str
    roles: list[str]
    login_name: str
    is_active: bool = True
    uses_initial_password: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)
