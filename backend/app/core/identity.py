from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Authenticated application identity independent from the HTTP transport."""

    user_id: str
    email: str
    display_name: str
    login_name: str = ""
    roles: tuple[str, ...] = ("user",)
    session_version: int = 1

    @property
    def is_administrator(self) -> bool:
        return "administrator" in self.roles
