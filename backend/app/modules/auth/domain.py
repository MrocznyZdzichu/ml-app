from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class UserAccount:
    id: str
    email: str
    display_name: str
    password_hash: str
    roles: tuple[str, ...] = ("owner",)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
