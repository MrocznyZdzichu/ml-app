"""Access rules shared by API use cases and workers."""

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from app.core.errors import ResourceNotFoundError
from app.core.identity import Principal
from app.modules.sharing.domain import (
    AuditEvent,
    BC_ROLE_RANK,
    RESOURCE_ROLE_RANK,
    BusinessCaseAccessRole,
    ResourceAccessRole,
    ResourceKind,
)


class AccessReader(Protocol):
    def business_case_ids(self) -> set[str]: ...
    def business_case_owner_id(self, business_case_id: str) -> str | None: ...
    def business_case_grants(
        self, user_id: str, business_case_ids: set[str] | None
    ) -> list[tuple[str, BusinessCaseAccessRole]]: ...
    def resource_grants(
        self, user_id: str, kind: ResourceKind, resource_id: str
    ) -> list[BusinessCaseAccessRole | ResourceAccessRole]: ...
    def accessible_dataset_ids(
        self, user_id: str, readable_case_roles: set[BusinessCaseAccessRole]
    ) -> set[str]: ...


class AccessPolicy:
    """Resolve effective roles and audit administrator access."""

    def __init__(self, grants: AccessReader, record_audit: Callable[[AuditEvent], object]) -> None:
        self.grants = grants
        self.record_audit = record_audit

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
        if business_case_ids == set():
            return {}
        if principal.is_administrator:
            ids = self.grants.business_case_ids() if business_case_ids is None else business_case_ids
            return dict.fromkeys(ids, BusinessCaseAccessRole.OWNER)

        roles: dict[str, BusinessCaseAccessRole] = {}
        for case_id, role in self.grants.business_case_grants(principal.user_id, business_case_ids):
            current = roles.get(case_id)
            if current is None or BC_ROLE_RANK[role] > BC_ROLE_RANK[current]:
                roles[case_id] = role
        return roles

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
            raise ResourceNotFoundError("Business case not found")
        if principal.is_administrator:
            owner_id = self.grants.business_case_owner_id(business_case_id)
            if owner_id is not None and owner_id != principal.user_id:
                self.record_audit(AuditEvent(
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
        roles: list[ResourceAccessRole] = []
        for role in self.grants.resource_grants(principal.user_id, kind, resource_id):
            if isinstance(role, ResourceAccessRole):
                roles.append(role)
            elif role == BusinessCaseAccessRole.OWNER:
                roles.append(ResourceAccessRole.OWNER)
            elif BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.CONTRIBUTOR]:
                roles.append(ResourceAccessRole.EDITOR)
            elif role == BusinessCaseAccessRole.READER:
                roles.append(ResourceAccessRole.READER)
        return max(roles, key=RESOURCE_ROLE_RANK.__getitem__, default=None)

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
            raise ResourceNotFoundError("Resource not found")
        if principal.is_administrator and owner_id != principal.user_id:
            self.record_audit(AuditEvent(
                id=str(uuid4()), actor_id=principal.user_id,
                action="administrator.resource_accessed",
                resource_kind=kind.value, resource_id=resource_id,
                new_state={"minimum_role": minimum.value},
            ))
        return role

    def accessible_dataset_ids(self, principal: Principal) -> set[str] | None:
        if principal.is_administrator:
            return None
        readable_case_roles = {
            role for role in BusinessCaseAccessRole
            if BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]
        }
        return self.grants.accessible_dataset_ids(principal.user_id, readable_case_roles)
