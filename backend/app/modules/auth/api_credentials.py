from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import Column, DateTime, MetaData, String, Table, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.core.security import Principal
from app.modules.sharing.domain import AuditEvent
from app.modules.sharing.repository import PostgresSharingRepository


metadata = MetaData(schema="mlapp")
api_credentials_table = Table(
    "api_credentials", metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass
class ApiCredential:
    id: str
    user_id: str
    name: str
    token_hash: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class ApiCredentialRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add(self, credential: ApiCredential) -> ApiCredential:
        self._ensure()
        with self.engine.begin() as connection:
            connection.execute(api_credentials_table.insert().values(**credential.__dict__))
        return credential

    def list_for_user(self, user_id: str) -> list[ApiCredential]:
        self._ensure()
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(api_credentials_table).where(api_credentials_table.c.user_id == user_id)
                .order_by(api_credentials_table.c.created_at.desc())
            )
            return [ApiCredential(**dict(row._mapping)) for row in rows]

    def revoke(self, credential_id: str, user_id: str, revoked_at: datetime) -> bool:
        self._ensure()
        with self.engine.begin() as connection:
            result = connection.execute(
                api_credentials_table.update().where(
                    api_credentials_table.c.id == credential_id,
                    api_credentials_table.c.user_id == user_id,
                ).values(revoked_at=revoked_at)
            )
        return result.rowcount == 1

    def authenticate(self, token: str) -> str | None:
        if not token.startswith("mlapp_pat_"):
            return None
        self._ensure()
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            row = connection.execute(select(api_credentials_table).where(
                api_credentials_table.c.token_hash == digest,
                api_credentials_table.c.revoked_at.is_(None),
            )).first()
            if row is None:
                return None
            expires_at = row._mapping["expires_at"]
            if expires_at is not None and expires_at <= now:
                return None
            connection.execute(
                api_credentials_table.update().where(api_credentials_table.c.id == row._mapping["id"])
                .values(last_used_at=now)
            )
            return str(row._mapping["user_id"])

    def _ensure(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS mlapp"))
            metadata.create_all(connection)
        self._initialized = True


class ApiCredentialService:
    def __init__(self, repository: ApiCredentialRepository | None = None) -> None:
        self.repository = repository or ApiCredentialRepository()

    def create(self, name: str, expires_at: datetime | None, principal: Principal) -> tuple[ApiCredential, str]:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=422, detail="Credential name is required")
        now = datetime.now(timezone.utc)
        if expires_at is not None and expires_at <= now:
            raise HTTPException(status_code=422, detail="Credential expiry must be in the future")
        raw_token = f"mlapp_pat_{secrets.token_urlsafe(32)}"
        credential = ApiCredential(
            id=str(uuid4()), user_id=principal.user_id, name=clean_name,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=expires_at, revoked_at=None, last_used_at=None, created_at=now,
        )
        self.repository.add(credential)
        self._audit(principal, "api_credential.created", credential)
        return credential, raw_token

    def revoke(self, credential_id: str, principal: Principal) -> None:
        now = datetime.now(timezone.utc)
        if not self.repository.revoke(credential_id, principal.user_id, now):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API credential not found")
        self._audit(principal, "api_credential.revoked", ApiCredential(
            id=credential_id, user_id=principal.user_id, name="", token_hash="",
            expires_at=None, revoked_at=now, last_used_at=None, created_at=now,
        ))

    @staticmethod
    def _audit(principal: Principal, action: str, credential: ApiCredential) -> None:
        PostgresSharingRepository().add_audit(AuditEvent(
            id=str(uuid4()), actor_id=principal.user_id, action=action,
            subject_type="api_credential", subject_id=credential.id,
            new_state={"name": credential.name, "expires_at": credential.expires_at.isoformat() if credential.expires_at else None},
        ))
