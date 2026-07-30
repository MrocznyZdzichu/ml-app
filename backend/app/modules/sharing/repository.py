from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.core.database import get_engine
from app.modules.auth.repository import user_accounts_table
from app.modules.business_cases.tables import business_cases_table
from app.modules.sharing.domain import (
    AccessRequestStatus,
    AccessGroup,
    AuditEvent,
    BusinessCaseAccessRequest,
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

business_case_access_requests_table = Table(
    "business_case_access_requests", metadata,
    Column("id", String(64), primary_key=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("requester_id", String(64), nullable=False, index=True),
    Column("requested_role", String(32), nullable=False),
    Column("justification", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=True),
    Column("decided_by", String(64), nullable=False, default=""),
    Column("granted_role", String(32), nullable=True),
    Column("decision_note", Text, nullable=False, default=""),
)
Index(
    "uq_bc_access_requests_pending",
    business_case_access_requests_table.c.business_case_id,
    business_case_access_requests_table.c.requester_id,
    unique=True,
    postgresql_where=text("status = 'pending'"),
)
Index(
    "ix_bc_access_requests_incoming",
    business_case_access_requests_table.c.business_case_id,
    business_case_access_requests_table.c.status,
    business_case_access_requests_table.c.created_at,
)
Index(
    "ix_bc_access_requests_mine",
    business_case_access_requests_table.c.requester_id,
    business_case_access_requests_table.c.created_at,
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


class DuplicateAccessRequest(ValueError):
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

    def page_groups(
        self,
        accessible_group_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        is_active: bool | None = None,
    ) -> tuple[list[AccessGroup], int]:
        self._ensure_initialized()
        if accessible_group_ids is not None and not accessible_group_ids:
            return [], 0
        filters = []
        if accessible_group_ids is not None:
            filters.append(access_groups_table.c.id.in_(accessible_group_ids))
        if is_active is not None:
            filters.append(access_groups_table.c.is_active == is_active)
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                access_groups_table.c.name.ilike(pattern),
                access_groups_table.c.description.ilike(pattern),
            ))
        count_statement = select(func.count()).select_from(access_groups_table)
        page_statement = select(access_groups_table)
        if filters:
            count_statement = count_statement.where(*filters)
            page_statement = page_statement.where(*filters)
        page_statement = (
            page_statement
            .order_by(
                access_groups_table.c.name.asc(),
                access_groups_table.c.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            groups = [
                self._group(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return groups, total

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

    def page_memberships(
        self,
        group_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[GroupMembership], int]:
        self._ensure_initialized()
        filters = [group_memberships_table.c.group_id == group_id]
        count_statement = (
            select(func.count())
            .select_from(group_memberships_table)
            .where(*filters)
        )
        page_statement = (
            select(group_memberships_table)
            .where(*filters)
            .order_by(
                group_memberships_table.c.created_at.asc(),
                group_memberships_table.c.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            memberships = [
                self._membership(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return memberships, total

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
            values = {
                "id": grant.id,
                "business_case_id": grant.business_case_id,
                "subject_type": grant.subject_type.value,
                "subject_id": grant.subject_id,
                "access_role": grant.access_role.value,
                "granted_by": grant.granted_by,
                "created_at": grant.created_at,
                "updated_at": grant.updated_at,
                "expires_at": grant.expires_at,
            }
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
            rows = connection.execute(
                self._bc_grant_select()
                .where(
                    business_case_grants_table.c.business_case_id
                    == business_case_id
                )
                .order_by(business_case_grants_table.c.created_at.asc())
            )
            return [self._bc_grant(row._mapping) for row in rows]

    def page_bc_grants(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[BusinessCaseGrant], int]:
        self._ensure_initialized()
        condition = (
            business_case_grants_table.c.business_case_id == business_case_id
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(
                select(func.count()).select_from(business_case_grants_table).where(condition)
            ).scalar_one())
            rows = connection.execute(
                self._bc_grant_select()
                .where(condition)
                .order_by(
                    business_case_grants_table.c.created_at.asc(),
                    business_case_grants_table.c.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return [self._bc_grant(row._mapping) for row in rows], total

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

    def pending_access_request_statuses(
        self,
        requester_id: str,
        business_case_ids: set[str],
    ) -> dict[str, AccessRequestStatus]:
        self._ensure_initialized()
        if not business_case_ids:
            return {}
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(
                    business_case_access_requests_table.c.business_case_id,
                    business_case_access_requests_table.c.status,
                ).where(
                    business_case_access_requests_table.c.requester_id == requester_id,
                    business_case_access_requests_table.c.business_case_id.in_(business_case_ids),
                    business_case_access_requests_table.c.status == AccessRequestStatus.PENDING.value,
                )
            )
            return {
                str(row.business_case_id): AccessRequestStatus(str(row.status))
                for row in rows
            }

    def add_access_request(
        self,
        request: BusinessCaseAccessRequest,
        audit: AuditEvent,
    ) -> BusinessCaseAccessRequest:
        self._ensure_initialized()
        values = self._access_request_to_record(request)
        try:
            with self.engine.begin() as connection:
                connection.execute(business_case_access_requests_table.insert().values(**values))
                connection.execute(audit_events_table.insert().values(**audit.__dict__))
        except IntegrityError as exc:
            raise DuplicateAccessRequest(
                "A pending access request already exists for this Business Case"
            ) from exc
        return request

    def get_access_request(self, request_id: str) -> BusinessCaseAccessRequest | None:
        self._ensure_initialized()
        statement = self._access_request_select().where(
            business_case_access_requests_table.c.id == request_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._access_request(row._mapping) if row else None

    def page_access_requests(
        self,
        *,
        requester_id: str | None,
        manageable_business_case_ids: set[str] | None,
        status_filter: AccessRequestStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[BusinessCaseAccessRequest], int]:
        self._ensure_initialized()
        if manageable_business_case_ids is not None and not manageable_business_case_ids:
            return [], 0
        filters = []
        if requester_id is not None:
            filters.append(
                business_case_access_requests_table.c.requester_id == requester_id
            )
        if manageable_business_case_ids is not None:
            filters.append(
                business_case_access_requests_table.c.business_case_id.in_(
                    manageable_business_case_ids
                )
            )
        if status_filter is not None:
            filters.append(
                business_case_access_requests_table.c.status == status_filter.value
            )
        count_statement = select(func.count()).select_from(
            business_case_access_requests_table
        )
        page_statement = self._access_request_select()
        if filters:
            count_statement = count_statement.where(*filters)
            page_statement = page_statement.where(*filters)
        page_statement = (
            page_statement
            .order_by(
                business_case_access_requests_table.c.created_at.desc(),
                business_case_access_requests_table.c.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            items = [
                self._access_request(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return items, total

    def decide_access_request(
        self,
        request: BusinessCaseAccessRequest,
        *,
        grant: BusinessCaseGrant | None,
        audit: AuditEvent,
    ) -> bool:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            locked = connection.execute(
                select(business_case_access_requests_table.c.status)
                .where(business_case_access_requests_table.c.id == request.id)
                .with_for_update()
            ).scalar_one_or_none()
            if locked != AccessRequestStatus.PENDING.value:
                return False
            if grant is not None:
                existing = connection.execute(
                    select(business_case_grants_table.c.id).where(
                        business_case_grants_table.c.business_case_id == grant.business_case_id,
                        business_case_grants_table.c.subject_type == grant.subject_type.value,
                        business_case_grants_table.c.subject_id == grant.subject_id,
                    )
                ).scalar_one_or_none()
                grant_values = {
                    "id": grant.id,
                    "business_case_id": grant.business_case_id,
                    "subject_type": grant.subject_type.value,
                    "subject_id": grant.subject_id,
                    "access_role": grant.access_role.value,
                    "granted_by": grant.granted_by,
                    "created_at": grant.created_at,
                    "updated_at": grant.updated_at,
                    "expires_at": grant.expires_at,
                }
                if existing:
                    grant_values["id"] = existing
                    grant_values["created_at"] = connection.execute(
                        select(business_case_grants_table.c.created_at).where(
                            business_case_grants_table.c.id == existing
                        )
                    ).scalar_one()
                    connection.execute(
                        business_case_grants_table.update()
                        .where(business_case_grants_table.c.id == existing)
                        .values(**grant_values)
                    )
                    grant.id = str(existing)
                    grant.created_at = grant_values["created_at"]
                else:
                    connection.execute(
                        business_case_grants_table.insert().values(**grant_values)
                    )
            connection.execute(
                business_case_access_requests_table.update()
                .where(business_case_access_requests_table.c.id == request.id)
                .values(
                    status=request.status.value,
                    decided_at=request.decided_at,
                    decided_by=request.decided_by,
                    granted_role=(
                        request.granted_role.value
                        if request.granted_role is not None
                        else None
                    ),
                    decision_note=request.decision_note,
                )
            )
            connection.execute(audit_events_table.insert().values(**audit.__dict__))
        return True

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

    def page_resource_grants(
        self,
        kind: ResourceKind,
        resource_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ResourceGrant], int]:
        self._ensure_initialized()
        conditions = (
            resource_grants_table.c.resource_kind == kind.value,
            resource_grants_table.c.resource_id == resource_id,
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(
                select(func.count()).select_from(resource_grants_table).where(*conditions)
            ).scalar_one())
            rows = connection.execute(
                select(resource_grants_table)
                .where(*conditions)
                .order_by(
                    resource_grants_table.c.created_at.asc(),
                    resource_grants_table.c.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return [self._resource_grant(row._mapping) for row in rows], total

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
        values.setdefault("subject_name", "")
        values.setdefault("subject_email", "")
        values.setdefault("business_case_name", "")
        return BusinessCaseGrant(**values)

    @staticmethod
    def _bc_grant_select():
        return (
            select(
                business_case_grants_table,
                business_cases_table.c.name.label("business_case_name"),
                func.coalesce(
                    user_accounts_table.c.display_name,
                    access_groups_table.c.name,
                    business_case_grants_table.c.subject_id,
                ).label("subject_name"),
                func.coalesce(user_accounts_table.c.email, "").label(
                    "subject_email"
                ),
            )
            .join(
                business_cases_table,
                business_cases_table.c.id
                == business_case_grants_table.c.business_case_id,
            )
            .outerjoin(
                user_accounts_table,
                and_(
                    business_case_grants_table.c.subject_type
                    == SubjectType.USER.value,
                    user_accounts_table.c.id
                    == business_case_grants_table.c.subject_id,
                ),
            )
            .outerjoin(
                access_groups_table,
                and_(
                    business_case_grants_table.c.subject_type
                    == SubjectType.GROUP.value,
                    access_groups_table.c.id
                    == business_case_grants_table.c.subject_id,
                ),
            )
        )

    @staticmethod
    def _access_request_to_record(request: BusinessCaseAccessRequest) -> dict[str, object]:
        return {
            "id": request.id,
            "business_case_id": request.business_case_id,
            "requester_id": request.requester_id,
            "requested_role": request.requested_role.value,
            "justification": request.justification,
            "status": request.status.value,
            "created_at": request.created_at,
            "decided_at": request.decided_at,
            "decided_by": request.decided_by,
            "granted_role": (
                request.granted_role.value
                if request.granted_role is not None
                else None
            ),
            "decision_note": request.decision_note,
        }

    @staticmethod
    def _access_request_select():
        return (
            select(
                business_case_access_requests_table,
                business_cases_table.c.name.label("business_case_name"),
                user_accounts_table.c.display_name.label("requester_display_name"),
                user_accounts_table.c.email.label("requester_email"),
            )
            .join(
                business_cases_table,
                business_cases_table.c.id
                == business_case_access_requests_table.c.business_case_id,
            )
            .join(
                user_accounts_table,
                user_accounts_table.c.id
                == business_case_access_requests_table.c.requester_id,
            )
        )

    @staticmethod
    def _access_request(record) -> BusinessCaseAccessRequest:
        return BusinessCaseAccessRequest(
            id=str(record["id"]),
            business_case_id=str(record["business_case_id"]),
            requester_id=str(record["requester_id"]),
            requested_role=BusinessCaseAccessRole(str(record["requested_role"])),
            justification=str(record["justification"]),
            status=AccessRequestStatus(str(record["status"])),
            created_at=record["created_at"],
            decided_at=record["decided_at"],
            decided_by=str(record["decided_by"] or ""),
            granted_role=(
                BusinessCaseAccessRole(str(record["granted_role"]))
                if record["granted_role"]
                else None
            ),
            decision_note=str(record["decision_note"] or ""),
            business_case_name=str(record["business_case_name"]),
            requester_display_name=str(record["requester_display_name"]),
            requester_email=str(record["requester_email"]),
        )

    @staticmethod
    def _resource_grant(record) -> ResourceGrant:
        values = dict(record)
        values["resource_kind"] = ResourceKind(values["resource_kind"])
        values["subject_type"] = SubjectType(values["subject_type"])
        values["access_role"] = ResourceAccessRole(values["access_role"])
        return ResourceGrant(**values)
