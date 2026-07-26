from fastapi import HTTPException, status
from datetime import datetime, timezone

from sqlalchemy import and_, literal, or_, select, union_all
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.core.security import Principal
from app.modules.business_cases.repository import (
    PostgresBusinessCaseRepository,
    business_cases_table,
    business_case_data_attachments_table,
)
from app.modules.datasets.repository import PostgresDatasetRepository, data_assets_table
from app.modules.sharing.domain import (
    AuditEvent,
    BC_ROLE_RANK,
    RESOURCE_ROLE_RANK,
    BusinessCaseAccessRole,
    ResourceAccessRole,
    ResourceKind,
)
from uuid import uuid4
from app.modules.sharing.repository import (
    PostgresSharingRepository,
    access_groups_table,
    business_case_grants_table,
    group_memberships_table,
    resource_grants_table,
)


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
        return self.business_case_roles(principal, {business_case_id}).get(business_case_id)

    def business_case_roles(
        self,
        principal: Principal,
        business_case_ids: set[str] | None = None,
    ) -> dict[str, BusinessCaseAccessRole]:
        """Resolve effective BC roles in one set-oriented database query."""
        if business_case_ids is not None and not business_case_ids:
            return {}
        if principal.is_administrator:
            if business_case_ids is None:
                with self.engine.begin() as connection:
                    ids = connection.execute(select(business_cases_table.c.id))
                    return {
                        str(row[0]): BusinessCaseAccessRole.OWNER
                        for row in ids
                    }
            return {
                business_case_id: BusinessCaseAccessRole.OWNER
                for business_case_id in business_case_ids
            }

        access_paths = self._business_case_access_paths(principal, business_case_ids)
        roles: dict[str, BusinessCaseAccessRole] = {}
        with self.engine.begin() as connection:
            for business_case_id, raw_role in connection.execute(access_paths):
                try:
                    role = BusinessCaseAccessRole(str(raw_role))
                except ValueError:
                    continue
                current = roles.get(str(business_case_id))
                if current is None or BC_ROLE_RANK[role] > BC_ROLE_RANK[current]:
                    roles[str(business_case_id)] = role
        return roles

    @staticmethod
    def _business_case_access_paths(
        principal: Principal,
        business_case_ids: set[str] | None = None,
    ):
        """Build reusable ownership/direct/group access paths without round trips."""
        now = datetime.now(timezone.utc)
        owner_path = select(
            business_cases_table.c.id.label("business_case_id"),
            literal(BusinessCaseAccessRole.OWNER.value).label("access_role"),
        ).where(business_cases_table.c.owner_id == principal.user_id)
        user_path = (
            select(
                business_case_grants_table.c.business_case_id,
                business_case_grants_table.c.access_role,
            )
            .join(
                business_cases_table,
                business_cases_table.c.id == business_case_grants_table.c.business_case_id,
            )
            .where(
                business_case_grants_table.c.subject_type == "user",
                business_case_grants_table.c.subject_id == principal.user_id,
                or_(
                    business_case_grants_table.c.expires_at.is_(None),
                    business_case_grants_table.c.expires_at > now,
                ),
            )
        )
        group_path = (
            select(
                business_case_grants_table.c.business_case_id,
                business_case_grants_table.c.access_role,
            )
            .join(
                business_cases_table,
                business_cases_table.c.id == business_case_grants_table.c.business_case_id,
            )
            .join(
                group_memberships_table,
                and_(
                    business_case_grants_table.c.subject_type == "group",
                    business_case_grants_table.c.subject_id == group_memberships_table.c.group_id,
                ),
            )
            .join(
                access_groups_table,
                access_groups_table.c.id == group_memberships_table.c.group_id,
            )
            .where(
                group_memberships_table.c.user_id == principal.user_id,
                access_groups_table.c.is_active.is_(True),
                or_(
                    business_case_grants_table.c.expires_at.is_(None),
                    business_case_grants_table.c.expires_at > now,
                ),
            )
        )
        if business_case_ids is not None:
            owner_path = owner_path.where(business_cases_table.c.id.in_(business_case_ids))
            user_path = user_path.where(
                business_case_grants_table.c.business_case_id.in_(business_case_ids)
            )
            group_path = group_path.where(
                business_case_grants_table.c.business_case_id.in_(business_case_ids)
            )
        return union_all(owner_path, user_path, group_path)

    def accessible_business_case_roles(
        self,
        principal: Principal,
        minimum: BusinessCaseAccessRole = BusinessCaseAccessRole.REPORT_VIEWER,
    ) -> dict[str, BusinessCaseAccessRole] | None:
        if principal.is_administrator:
            return None
        return {
            business_case_id: role
            for business_case_id, role in self.business_case_roles(principal).items()
            if BC_ROLE_RANK[role] >= BC_ROLE_RANK[minimum]
        }

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
        roles = self.accessible_business_case_roles(principal, minimum)
        return None if roles is None else set(roles)

    def resource_role(
        self,
        principal: Principal,
        kind: ResourceKind,
        resource_id: str,
        owner_id: str = "",
    ) -> ResourceAccessRole | None:
        if principal.is_administrator or owner_id == principal.user_id:
            return ResourceAccessRole.OWNER
        now = datetime.now(timezone.utc)
        active_grant = or_(
            resource_grants_table.c.expires_at.is_(None),
            resource_grants_table.c.expires_at > now,
        )
        user_path = select(
            literal("resource").label("source"),
            resource_grants_table.c.access_role.label("access_role"),
        ).where(
            resource_grants_table.c.resource_kind == kind.value,
            resource_grants_table.c.resource_id == resource_id,
            resource_grants_table.c.subject_type == "user",
            resource_grants_table.c.subject_id == principal.user_id,
            active_grant,
        )
        group_path = (
            select(
                literal("resource").label("source"),
                resource_grants_table.c.access_role.label("access_role"),
            )
            .join(
                group_memberships_table,
                and_(
                    resource_grants_table.c.subject_type == "group",
                    resource_grants_table.c.subject_id == group_memberships_table.c.group_id,
                ),
            )
            .join(
                access_groups_table,
                access_groups_table.c.id == group_memberships_table.c.group_id,
            )
            .where(
                resource_grants_table.c.resource_kind == kind.value,
                resource_grants_table.c.resource_id == resource_id,
                group_memberships_table.c.user_id == principal.user_id,
                access_groups_table.c.is_active.is_(True),
                active_grant,
            )
        )
        paths = [user_path, group_path]
        if kind in {ResourceKind.DATASET, ResourceKind.DATA_VIEW}:
            attached_assets = data_assets_table.alias("attached_assets")
            requested_asset = data_assets_table.alias("requested_asset")
            bc_access = self._business_case_access_paths(principal).subquery(
                "resource_business_case_access"
            )
            paths.append(
                select(
                    literal("business_case").label("source"),
                    bc_access.c.access_role,
                )
                .select_from(
                    business_case_data_attachments_table
                    .join(
                        attached_assets,
                        attached_assets.c.id
                        == business_case_data_attachments_table.c.data_asset_id,
                    )
                    .join(
                        requested_asset,
                        requested_asset.c.logical_id == attached_assets.c.logical_id,
                    )
                    .join(
                        bc_access,
                        bc_access.c.business_case_id
                        == business_case_data_attachments_table.c.business_case_id,
                    )
                )
                .where(requested_asset.c.id == resource_id)
            )
        roles: list[ResourceAccessRole] = []
        with self.engine.begin() as connection:
            for source, raw_role in connection.execute(union_all(*paths)):
                try:
                    if str(source) == "business_case":
                        bc_role = BusinessCaseAccessRole(str(raw_role))
                        if BC_ROLE_RANK[bc_role] < BC_ROLE_RANK[BusinessCaseAccessRole.READER]:
                            continue
                        roles.append(
                            ResourceAccessRole.OWNER
                            if bc_role == BusinessCaseAccessRole.OWNER
                            else ResourceAccessRole.EDITOR
                            if BC_ROLE_RANK[bc_role]
                            >= BC_ROLE_RANK[BusinessCaseAccessRole.CONTRIBUTOR]
                            else ResourceAccessRole.READER
                        )
                    else:
                        roles.append(ResourceAccessRole(str(raw_role)))
                except ValueError:
                    continue
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
        now = datetime.now(timezone.utc)
        resource_kinds = [ResourceKind.DATASET.value, ResourceKind.DATA_VIEW.value]
        active_grant = or_(
            resource_grants_table.c.expires_at.is_(None),
            resource_grants_table.c.expires_at > now,
        )
        owner_path = select(data_assets_table.c.id.label("resource_id")).where(
            data_assets_table.c.owner_id == principal.user_id
        )
        user_path = select(resource_grants_table.c.resource_id).where(
            resource_grants_table.c.resource_kind.in_(resource_kinds),
            resource_grants_table.c.subject_type == "user",
            resource_grants_table.c.subject_id == principal.user_id,
            active_grant,
        )
        group_path = (
            select(resource_grants_table.c.resource_id)
            .join(
                group_memberships_table,
                and_(
                    resource_grants_table.c.subject_type == "group",
                    resource_grants_table.c.subject_id == group_memberships_table.c.group_id,
                ),
            )
            .join(
                access_groups_table,
                access_groups_table.c.id == group_memberships_table.c.group_id,
            )
            .where(
                resource_grants_table.c.resource_kind.in_(resource_kinds),
                group_memberships_table.c.user_id == principal.user_id,
                access_groups_table.c.is_active.is_(True),
                active_grant,
            )
        )
        attached_assets = data_assets_table.alias("attached_assets")
        family_versions = data_assets_table.alias("family_versions")
        bc_access = self._business_case_access_paths(principal).subquery(
            "dataset_business_case_access"
        )
        readable_bc_roles = [
            role.value
            for role in BusinessCaseAccessRole
            if BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]
        ]
        business_case_path = (
            select(family_versions.c.id.label("resource_id"))
            .select_from(
                family_versions
                .join(
                    attached_assets,
                    attached_assets.c.logical_id == family_versions.c.logical_id,
                )
                .join(
                    business_case_data_attachments_table,
                    business_case_data_attachments_table.c.data_asset_id
                    == attached_assets.c.id,
                )
                .join(
                    bc_access,
                    bc_access.c.business_case_id
                    == business_case_data_attachments_table.c.business_case_id,
                )
            )
            .where(bc_access.c.access_role.in_(readable_bc_roles))
        )
        with self.engine.begin() as connection:
            rows = connection.execute(
                union_all(owner_path, user_path, group_path, business_case_path)
            )
            return {str(row[0]) for row in rows}


access_policy = AccessPolicy()
