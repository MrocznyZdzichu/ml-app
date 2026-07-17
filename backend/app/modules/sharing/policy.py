from fastapi import HTTPException, status
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.core.security import Principal
from app.modules.business_cases.repository import (
    PostgresBusinessCaseRepository,
    business_case_data_attachments_table,
)
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.sharing.domain import (
    AuditEvent,
    BC_ROLE_RANK,
    RESOURCE_ROLE_RANK,
    BusinessCaseAccessRole,
    ResourceAccessRole,
    ResourceKind,
)
from uuid import uuid4
from app.modules.sharing.repository import PostgresSharingRepository


class AccessPolicy:
    """One authorization resolver used by HTTP services and background entrypoints."""

    def __init__(
        self,
        repository: PostgresSharingRepository | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.repository = repository or PostgresSharingRepository(engine)
        self.engine = engine or get_engine()
        self.business_cases = PostgresBusinessCaseRepository(self.engine)
        self.datasets = PostgresDatasetRepository(self.engine)

    def business_case_role(
        self, principal: Principal, business_case_id: str
    ) -> BusinessCaseAccessRole | None:
        if principal.is_administrator:
            return BusinessCaseAccessRole.OWNER
        business_case = self.business_cases.get_business_case(business_case_id)
        if business_case is None:
            return None
        if business_case.owner_id == principal.user_id:
            return BusinessCaseAccessRole.OWNER
        group_ids = self.repository.group_ids_for_user(principal.user_id)
        grants = self.repository.bc_grants_for_subjects(principal.user_id, group_ids)
        roles = [grant.access_role for grant in grants if grant.business_case_id == business_case_id]
        return max(roles, key=BC_ROLE_RANK.get) if roles else None

    def require_business_case(
        self,
        principal: Principal,
        business_case_id: str,
        minimum: BusinessCaseAccessRole = BusinessCaseAccessRole.REPORT_VIEWER,
    ) -> BusinessCaseAccessRole:
        role = self.business_case_role(principal, business_case_id)
        if role is None or BC_ROLE_RANK[role] < BC_ROLE_RANK[minimum]:
            # Preserve non-disclosure semantics for inaccessible resources.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business case not found")
        if principal.is_administrator:
            business_case = self.business_cases.get_business_case(business_case_id)
            if business_case is not None and business_case.owner_id != principal.user_id:
                self.repository.add_audit(AuditEvent(
                    id=str(uuid4()), actor_id=principal.user_id,
                    action="administrator.resource_accessed",
                    resource_kind="business_case", resource_id=business_case_id,
                    new_state={"minimum_role": minimum.value},
                ))
        return role

    def accessible_business_case_ids(
        self,
        principal: Principal,
        minimum: BusinessCaseAccessRole = BusinessCaseAccessRole.REPORT_VIEWER,
    ) -> set[str] | None:
        if principal.is_administrator:
            return None
        owned = {item.id for item in self.business_cases.list_business_cases(principal.user_id)}
        groups = self.repository.group_ids_for_user(principal.user_id)
        granted = {
            grant.business_case_id
            for grant in self.repository.bc_grants_for_subjects(principal.user_id, groups)
            if BC_ROLE_RANK[grant.access_role] >= BC_ROLE_RANK[minimum]
        }
        return owned | granted

    def resource_role(
        self,
        principal: Principal,
        kind: ResourceKind,
        resource_id: str,
        owner_id: str = "",
    ) -> ResourceAccessRole | None:
        if principal.is_administrator or owner_id == principal.user_id:
            return ResourceAccessRole.OWNER
        groups = self.repository.group_ids_for_user(principal.user_id)
        direct = self.repository.resource_grants_for_subjects(
            principal.user_id, groups, kind, resource_id
        )
        roles = [grant.access_role for grant in direct]
        if kind in {ResourceKind.DATASET, ResourceKind.DATA_VIEW}:
            with self.engine.begin() as connection:
                bc_ids = [
                    str(row[0]) for row in connection.execute(
                        select(business_case_data_attachments_table.c.business_case_id).where(
                            business_case_data_attachments_table.c.data_asset_id == resource_id
                        )
                    )
                ]
            for business_case_id in bc_ids:
                bc_role = self.business_case_role(principal, business_case_id)
                if bc_role is not None and BC_ROLE_RANK[bc_role] >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]:
                    roles.append(
                        ResourceAccessRole.OWNER
                        if bc_role == BusinessCaseAccessRole.OWNER
                        else ResourceAccessRole.EDITOR
                        if BC_ROLE_RANK[bc_role] >= BC_ROLE_RANK[BusinessCaseAccessRole.CONTRIBUTOR]
                        else ResourceAccessRole.READER
                    )
        return max(roles, key=RESOURCE_ROLE_RANK.get) if roles else None

    def require_resource(
        self,
        principal: Principal,
        kind: ResourceKind,
        resource_id: str,
        owner_id: str,
        minimum: ResourceAccessRole = ResourceAccessRole.READER,
    ) -> ResourceAccessRole:
        role = self.resource_role(principal, kind, resource_id, owner_id)
        if role is None or RESOURCE_ROLE_RANK[role] < RESOURCE_ROLE_RANK[minimum]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        if principal.is_administrator and owner_id != principal.user_id:
            self.repository.add_audit(AuditEvent(
                id=str(uuid4()), actor_id=principal.user_id,
                action="administrator.resource_accessed",
                resource_kind=kind.value, resource_id=resource_id,
                new_state={"minimum_role": minimum.value},
            ))
        return role

    def accessible_dataset_ids(self, principal: Principal) -> set[str] | None:
        if principal.is_administrator:
            return None
        ids = {item.id for item in self.datasets.list_for_owner(principal.user_id)}
        groups = self.repository.group_ids_for_user(principal.user_id)
        for kind in (ResourceKind.DATASET, ResourceKind.DATA_VIEW):
            # Bounded metadata table query: raw dataset rows never pass through this path.
            with self.engine.begin() as connection:
                from app.modules.sharing.repository import resource_grants_table
                subject_filter = (
                    (resource_grants_table.c.subject_type == "user")
                    & (resource_grants_table.c.subject_id == principal.user_id)
                )
                if groups:
                    subject_filter = subject_filter | (
                        (resource_grants_table.c.subject_type == "group")
                        & resource_grants_table.c.subject_id.in_(groups)
                    )
                rows = connection.execute(select(resource_grants_table.c.resource_id).where(
                    resource_grants_table.c.resource_kind == kind.value,
                    subject_filter,
                    or_(resource_grants_table.c.expires_at.is_(None), resource_grants_table.c.expires_at > datetime.now(timezone.utc)),
                ))
                ids.update(str(row[0]) for row in rows)
        bc_ids = self.accessible_business_case_ids(principal, BusinessCaseAccessRole.READER) or set()
        if bc_ids:
            with self.engine.begin() as connection:
                rows = connection.execute(select(business_case_data_attachments_table.c.data_asset_id).where(
                    business_case_data_attachments_table.c.business_case_id.in_(bc_ids)
                ))
                ids.update(str(row[0]) for row in rows)
        return ids


access_policy = AccessPolicy()
