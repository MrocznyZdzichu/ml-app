"""Set-oriented authorization queries for the PostgreSQL adapter."""

from datetime import datetime, timezone

from sqlalchemy import and_, literal, or_, select, union_all
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.business_cases.tables import business_cases_table, business_case_data_attachments_table
from app.modules.datasets.repository import data_assets_table
from app.modules.sharing.domain import BusinessCaseAccessRole, ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import AccessPolicy
from app.modules.sharing.repository import (
    PostgresSharingRepository,
    access_groups_table,
    business_case_grants_table,
    group_memberships_table,
    resource_grants_table,
)


class PostgresAccessReader:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def business_case_ids(self) -> set[str]:
        with self.engine.connect() as connection:
            return set(connection.scalars(select(business_cases_table.c.id)))

    def business_case_owner_id(self, business_case_id: str) -> str | None:
        with self.engine.connect() as connection:
            return connection.scalar(
                select(business_cases_table.c.owner_id).where(business_cases_table.c.id == business_case_id)
            )

    def business_case_grants(
        self, user_id: str, business_case_ids: set[str] | None
    ) -> list[tuple[str, BusinessCaseAccessRole]]:
        grants = []
        with self.engine.connect() as connection:
            for case_id, raw_role in connection.execute(self._business_case_access_paths(user_id, business_case_ids)):
                try:
                    grants.append((str(case_id), BusinessCaseAccessRole(raw_role)))
                except ValueError:
                    continue
        return grants

    @staticmethod
    def _business_case_access_paths(
        user_id: str,
        business_case_ids: set[str] | None = None,
    ):
        """Build reusable ownership/direct/group access paths without round trips."""
        now = datetime.now(timezone.utc)
        owner_path = select(
            business_cases_table.c.id.label("business_case_id"),
            literal(BusinessCaseAccessRole.OWNER.value).label("access_role"),
        ).where(business_cases_table.c.owner_id == user_id)
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
                business_case_grants_table.c.subject_id == user_id,
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
                group_memberships_table.c.user_id == user_id,
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

    def resource_grants(
        self, user_id: str, kind: ResourceKind, resource_id: str
    ) -> list[BusinessCaseAccessRole | ResourceAccessRole]:
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
            resource_grants_table.c.subject_id == user_id,
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
                group_memberships_table.c.user_id == user_id,
                access_groups_table.c.is_active.is_(True),
                active_grant,
            )
        )
        paths = [user_path, group_path]
        if kind in {ResourceKind.DATASET, ResourceKind.DATA_VIEW}:
            attached_assets = data_assets_table.alias("attached_assets")
            requested_asset = data_assets_table.alias("requested_asset")
            bc_access = self._business_case_access_paths(user_id).subquery(
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
        roles: list[BusinessCaseAccessRole | ResourceAccessRole] = []
        with self.engine.connect() as connection:
            for source, raw_role in connection.execute(union_all(*paths)):
                try:
                    role_type = BusinessCaseAccessRole if source == "business_case" else ResourceAccessRole
                    roles.append(role_type(raw_role))
                except ValueError:
                    continue
        return roles

    def accessible_dataset_ids(
        self, user_id: str, readable_case_roles: set[BusinessCaseAccessRole]
    ) -> set[str]:
        now = datetime.now(timezone.utc)
        resource_kinds = [ResourceKind.DATASET.value, ResourceKind.DATA_VIEW.value]
        active_grant = or_(
            resource_grants_table.c.expires_at.is_(None),
            resource_grants_table.c.expires_at > now,
        )
        owner_path = select(data_assets_table.c.id.label("resource_id")).where(
            data_assets_table.c.owner_id == user_id
        )
        user_path = select(resource_grants_table.c.resource_id).where(
            resource_grants_table.c.resource_kind.in_(resource_kinds),
            resource_grants_table.c.subject_type == "user",
            resource_grants_table.c.subject_id == user_id,
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
                group_memberships_table.c.user_id == user_id,
                access_groups_table.c.is_active.is_(True),
                active_grant,
            )
        )
        attached_assets = data_assets_table.alias("attached_assets")
        family_versions = data_assets_table.alias("family_versions")
        bc_access = self._business_case_access_paths(user_id).subquery(
            "dataset_business_case_access"
        )
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
            .where(bc_access.c.access_role.in_([role.value for role in readable_case_roles]))
        )
        with self.engine.begin() as connection:
            rows = connection.execute(
                union_all(owner_path, user_path, group_path, business_case_path)
            )
            return {str(row[0]) for row in rows}


def postgres_access_policy(repository: PostgresSharingRepository | None = None) -> AccessPolicy:
    repository = repository if repository is not None else PostgresSharingRepository(get_engine())
    return AccessPolicy(PostgresAccessReader(repository.engine), repository.add_audit)


access_policy = postgres_access_policy()
