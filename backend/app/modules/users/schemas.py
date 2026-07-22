from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    user_id: str
    email: str
    display_name: str
    roles: list[str]
    login_name: str = ""
    is_active: bool = True
    is_technical: bool = False
    session_version: int = 1
    created_at: datetime | None = None


class AdminUserUpdate(BaseModel):
    roles: list[str]
    is_active: bool
    is_technical: bool | None = None


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=6)
