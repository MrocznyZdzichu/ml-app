from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class UserAccount:
    id: str
    email: str
    display_name: str
    password_hash: str
    login_name: str = ""
    roles: tuple[str, ...] = ("user",)
    is_active: bool = True
    is_technical: bool = False
    session_version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
