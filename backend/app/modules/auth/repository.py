from typing import Protocol

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.auth.domain import UserAccount


AUTH_SCHEMA = "mlapp"
metadata = MetaData(schema=AUTH_SCHEMA)

user_accounts_table = Table(
    "user_accounts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("email", String(320), nullable=False, unique=True, index=True),
    Column("display_name", String(255), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("roles", JSON, nullable=False, default=list),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class UserRepository(Protocol):
    def add(self, user: UserAccount) -> UserAccount:
        ...

    def get(self, user_id: str) -> UserAccount | None:
        ...

    def get_by_email(self, email: str) -> UserAccount | None:
        ...


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._items: dict[str, UserAccount] = {}
        self._email_index: dict[str, str] = {}

    def add(self, user: UserAccount) -> UserAccount:
        self._items[user.id] = user
        self._email_index[_normalize_email(user.email)] = user.id
        return user

    def get(self, user_id: str) -> UserAccount | None:
        return self._items.get(user_id)

    def get_by_email(self, email: str) -> UserAccount | None:
        user_id = self._email_index.get(_normalize_email(email))
        if not user_id:
            return None
        return self.get(user_id)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class PostgresUserRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add(self, user: UserAccount) -> UserAccount:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(user_accounts_table.insert().values(**self._to_record(user)))
        return user

    def get(self, user_id: str) -> UserAccount | None:
        self._ensure_initialized()
        statement = select(user_accounts_table).where(user_accounts_table.c.id == user_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if not row:
            return None
        return self._from_record(row._mapping)

    def get_by_email(self, email: str) -> UserAccount | None:
        self._ensure_initialized()
        statement = select(user_accounts_table).where(
            user_accounts_table.c.email == _normalize_email(email)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if not row:
            return None
        return self._from_record(row._mapping)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {AUTH_SCHEMA}"))
            metadata.create_all(connection)
        self._initialized = True

    def _to_record(self, user: UserAccount) -> dict[str, object]:
        return {
            "id": user.id,
            "email": _normalize_email(user.email),
            "display_name": user.display_name,
            "password_hash": user.password_hash,
            "roles": list(user.roles),
            "created_at": user.created_at,
        }

    def _from_record(self, record: object) -> UserAccount:
        return UserAccount(
            id=record["id"],
            email=record["email"],
            display_name=record["display_name"],
            password_hash=record["password_hash"],
            roles=tuple(record["roles"] or ["owner"]),
            created_at=record["created_at"],
        )
