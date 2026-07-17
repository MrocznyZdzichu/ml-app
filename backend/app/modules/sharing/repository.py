from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    or_,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.core.database import get_engine
from app.modules.sharing.domain import (
    AccessGroup,
    AuditEvent,
    BusinessCaseAccessRole,
    BusinessCaseGrant,
    GroupMembership,
    MembershipRole,
    ResourceAccessRole,
    ResourceGrant,
    ResourceKind,
    SubjectType,
)


SHARING_SCHEMA = "mlapp"
metadata = MetaData(schema=SHARING_SCHEMA)

access_groups_table = Table(
    "access_groups", metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("created_by", String(64), nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

group_memberships_table = Table(
    "group_memberships", metadata,
    Column("id", String(64), primary_key=True),
    Column("group_id", String(64), nullable=False, index=True),
    Column("user_id", String(64), nullable=False, index=True),
    Column("membership_role", String(32), nullable=False),
    Column("added_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

business_case_grants_table = Table(
    "business_case_grants", metadata,
    Column("id", String(64), primary_key=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("subject_type", String(16), nullable=False),
    Column("subject_id", String(64), nullable=False, index=True),
    Column("access_role", String(32), nullable=False),
    Column("granted_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

resource_grants_table = Table(
    "resource_grants", metadata,
    Column("id", String(64), primary_key=True),
    Column("resource_kind", String(32), nullable=False),
    Column("resource_id", String(64), nullable=False, index=True),
    Column("subject_type", String(16), nullable=False),
    Column("subject_id", String(64), nullable=False, index=True),
    Column("access_role", String(32), nullable=False),
    Column("granted_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

audit_events_table = Table(
    "audit_events", metadata,
    Column("id", String(64), primary_key=True),
    Column("actor_id", String(64), nullable=False, index=True),
    Column("action", String(128), nullable=False),
    Column("subject_type", String(32), nullable=False, default=""),
    Column("subject_id", String(64), nullable=False, default=""),
    Column("resource_kind", String(32), nullable=False, default=""),
    Column("resource_id", String(64), nullable=False, default=""),
    Column("previous_state", JSON, nullable=False, default=dict),
    Column("new_state", JSON, nullable=False, default=dict),
    Column("reason", Text, nullable=False, default=""),
    Column("request_id", String(128), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class DuplicateAccessRecord(ValueError):
    pass


class PostgresSharingRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SHARING_SCHEMA}"))
            metadata.create_all(connection)
        self._initialized = True

    def add_group(self, group: AccessGroup, owner_membership: GroupMembership | None = None) -> AccessGroup:
        self._ensure_initialized()
        try:
            with self.engine.begin() as connection:
                connection.execute(access_groups_table.insert().values(**group.__dict__))
                if owner_membership is not None:
                    connection.execute(group_memberships_table.insert().values(
                        **{**owner_membership.__dict__, "membership_role": owner_membership.membership_role.value}
                    ))
        except IntegrityError as exc:
            raise DuplicateAccessRecord("Group name already exists") from exc
        return group

    def update_group(self, group: AccessGroup) -> AccessGroup:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                access_groups_table.update().where(access_groups_table.c.id == group.id).values(**group.__dict__)
            )
        return group

    def get_group(self, group_id: str) -> AccessGroup | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(select(access_groups_table).where(access_groups_table.c.id == group_id)).first()
        return self._group(row._mapping) if row else None

    def list_groups(self) -> list[AccessGroup]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(access_groups_table).order_by(access_groups_table.c.name.asc()))
            return [self._group(row._mapping) for row in rows]

    def delete_group(self, group_id: str) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(delete(group_memberships_table).where(group_memberships_table.c.group_id == group_id))
            connection.execute(delete(business_case_grants_table).where(
                business_case_grants_table.c.subject_type == SubjectType.GROUP.value,
                business_case_grants_table.c.subject_id == group_id,
            ))
            connection.execute(delete(resource_grants_table).where(
                resource_grants_table.c.subject_type == SubjectType.GROUP.value,
                resource_grants_table.c.subject_id == group_id,
            ))
            connection.execute(delete(access_groups_table).where(access_groups_table.c.id == group_id))

    def upsert_membership(self, membership: GroupMembership) -> GroupMembership:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            existing = connection.execute(select(group_memberships_table.c.id).where(
                group_memberships_table.c.group_id == membership.group_id,
                group_memberships_table.c.user_id == membership.user_id,
            )).scalar_one_or_none()
            values = {**membership.__dict__, "membership_role": membership.membership_role.value}
            if existing:
                values["id"] = existing
                connection.execute(group_memberships_table.update().where(group_memberships_table.c.id == existing).values(**values))
                membership.id = str(existing)
            else:
                connection.execute(group_memberships_table.insert().values(**values))
        return membership

    def remove_membership(self, group_id: str, user_id: str) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(delete(group_memberships_table).where(
                group_memberships_table.c.group_id == group_id,
                group_memberships_table.c.user_id == user_id,
            ))

    def list_memberships(self, group_id: str) -> list[GroupMembership]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(group_memberships_table).where(
                group_memberships_table.c.group_id == group_id
            ).order_by(group_memberships_table.c.created_at.asc()))
            return [self._membership(row._mapping) for row in rows]

    def group_ids_for_user(self, user_id: str) -> list[str]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(group_memberships_table.c.group_id)
                .join(access_groups_table, access_groups_table.c.id == group_memberships_table.c.group_id)
                .where(group_memberships_table.c.user_id == user_id, access_groups_table.c.is_active.is_(True))
            )
            return [str(row[0]) for row in rows]

    def upsert_bc_grant(self, grant: BusinessCaseGrant) -> BusinessCaseGrant:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            existing = connection.execute(select(business_case_grants_table.c.id).where(
                business_case_grants_table.c.business_case_id == grant.business_case_id,
                business_case_grants_table.c.subject_type == grant.subject_type.value,
                business_case_grants_table.c.subject_id == grant.subject_id,
            )).scalar_one_or_none()
            values = {**grant.__dict__, "subject_type": grant.subject_type.value, "access_role": grant.access_role.value}
            if existing:
                values["id"] = existing
                values["created_at"] = connection.execute(select(business_case_grants_table.c.created_at).where(
                    business_case_grants_table.c.id == existing
                )).scalar_one()
                connection.execute(business_case_grants_table.update().where(business_case_grants_table.c.id == existing).values(**values))
                grant.id = str(existing)
                grant.created_at = values["created_at"]
            else:
                connection.execute(business_case_grants_table.insert().values(**values))
        return grant

    def get_bc_grant(self, grant_id: str) -> BusinessCaseGrant | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(select(business_case_grants_table).where(business_case_grants_table.c.id == grant_id)).first()
        return self._bc_grant(row._mapping) if row else None

    def list_bc_grants(self, business_case_id: str) -> list[BusinessCaseGrant]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(business_case_grants_table).where(
                business_case_grants_table.c.business_case_id == business_case_id
            ).order_by(business_case_grants_table.c.created_at.asc()))
            return [self._bc_grant(row._mapping) for row in rows]

    def delete_bc_grant(self, grant_id: str) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(delete(business_case_grants_table).where(business_case_grants_table.c.id == grant_id))

    def bc_grants_for_subjects(self, user_id: str, group_ids: list[str]) -> list[BusinessCaseGrant]:
        self._ensure_initialized()
        now = datetime.now(timezone.utc)
        subject_filter = business_case_grants_table.c.subject_type == SubjectType.USER.value
        subject_filter = and_(subject_filter, business_case_grants_table.c.subject_id == user_id)
        if group_ids:
            subject_filter = or_(subject_filter, and_(
                business_case_grants_table.c.subject_type == SubjectType.GROUP.value,
                business_case_grants_table.c.subject_id.in_(group_ids),
            ))
        with self.engine.begin() as connection:
            rows = connection.execute(select(business_case_grants_table).where(
                subject_filter,
                or_(business_case_grants_table.c.expires_at.is_(None), business_case_grants_table.c.expires_at > now),
            ))
            return [self._bc_grant(row._mapping) for row in rows]

    def upsert_resource_grant(self, grant: ResourceGrant) -> ResourceGrant:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            existing = connection.execute(select(resource_grants_table.c.id).where(
                resource_grants_table.c.resource_kind == grant.resource_kind.value,
                resource_grants_table.c.resource_id == grant.resource_id,
                resource_grants_table.c.subject_type == grant.subject_type.value,
                resource_grants_table.c.subject_id == grant.subject_id,
            )).scalar_one_or_none()
            values = {**grant.__dict__, "resource_kind": grant.resource_kind.value, "subject_type": grant.subject_type.value, "access_role": grant.access_role.value}
            if existing:
                values["id"] = existing
                values["created_at"] = connection.execute(select(resource_grants_table.c.created_at).where(resource_grants_table.c.id == existing)).scalar_one()
                connection.execute(resource_grants_table.update().where(resource_grants_table.c.id == existing).values(**values))
                grant.id = str(existing)
                grant.created_at = values["created_at"]
            else:
                connection.execute(resource_grants_table.insert().values(**values))
        return grant

    def get_resource_grant(self, grant_id: str) -> ResourceGrant | None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            row = connection.execute(select(resource_grants_table).where(resource_grants_table.c.id == grant_id)).first()
        return self._resource_grant(row._mapping) if row else None

    def list_resource_grants(self, kind: ResourceKind, resource_id: str) -> list[ResourceGrant]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(resource_grants_table).where(
                resource_grants_table.c.resource_kind == kind.value,
                resource_grants_table.c.resource_id == resource_id,
            ).order_by(resource_grants_table.c.created_at.asc()))
            return [self._resource_grant(row._mapping) for row in rows]

    def delete_resource_grant(self, grant_id: str) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(delete(resource_grants_table).where(resource_grants_table.c.id == grant_id))

    def resource_grants_for_subjects(self, user_id: str, group_ids: list[str], kind: ResourceKind, resource_id: str) -> list[ResourceGrant]:
        self._ensure_initialized()
        now = datetime.now(timezone.utc)
        subject_filter = and_(resource_grants_table.c.subject_type == SubjectType.USER.value, resource_grants_table.c.subject_id == user_id)
        if group_ids:
            subject_filter = or_(subject_filter, and_(resource_grants_table.c.subject_type == SubjectType.GROUP.value, resource_grants_table.c.subject_id.in_(group_ids)))
        with self.engine.begin() as connection:
            rows = connection.execute(select(resource_grants_table).where(
                resource_grants_table.c.resource_kind == kind.value,
                resource_grants_table.c.resource_id == resource_id,
                subject_filter,
                or_(resource_grants_table.c.expires_at.is_(None), resource_grants_table.c.expires_at > now),
            ))
            return [self._resource_grant(row._mapping) for row in rows]

    def add_audit(self, event: AuditEvent) -> AuditEvent:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(audit_events_table.insert().values(**event.__dict__))
        return event

    def list_audit(self, limit: int = 200) -> list[AuditEvent]:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            rows = connection.execute(select(audit_events_table).order_by(audit_events_table.c.created_at.desc()).limit(limit))
            return [AuditEvent(**dict(row._mapping)) for row in rows]

    @staticmethod
    def _group(record) -> AccessGroup:
        return AccessGroup(**dict(record))

    @staticmethod
    def _membership(record) -> GroupMembership:
        values = dict(record)
        values["membership_role"] = MembershipRole(values["membership_role"])
        return GroupMembership(**values)

    @staticmethod
    def _bc_grant(record) -> BusinessCaseGrant:
        values = dict(record)
        values["subject_type"] = SubjectType(values["subject_type"])
        values["access_role"] = BusinessCaseAccessRole(values["access_role"])
        return BusinessCaseGrant(**values)

    @staticmethod
    def _resource_grant(record) -> ResourceGrant:
        values = dict(record)
        values["resource_kind"] = ResourceKind(values["resource_kind"])
        values["subject_type"] = SubjectType(values["subject_type"])
        values["access_role"] = ResourceAccessRole(values["access_role"])
        return ResourceGrant(**values)
