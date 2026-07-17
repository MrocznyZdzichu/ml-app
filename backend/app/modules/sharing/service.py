from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.security import Principal
from app.modules.auth.repository import PostgresUserRepository
from app.modules.business_cases.repository import business_case_data_attachments_table
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.sharing.domain import (
    AccessGroup,
    AuditEvent,
    BC_ROLE_RANK,
    BusinessCaseAccessRole,
    BusinessCaseGrant,
    GroupMembership,
    MembershipRole,
    ResourceAccessRole,
    ResourceGrant,
    ResourceKind,
    SubjectType,
)
from app.modules.sharing.policy import AccessPolicy
from app.modules.sharing.repository import DuplicateAccessRecord, PostgresSharingRepository
from app.modules.sharing.schemas import (
    BusinessCaseGrantCreate,
    GroupCreate,
    GroupUpdate,
    MembershipUpsert,
    ResourceGrantCreate,
)


class SharingService:
    def __init__(self, repository: PostgresSharingRepository | None = None) -> None:
        self.repository = repository or PostgresSharingRepository()
        self.policy = AccessPolicy(self.repository, self.repository.engine)
        self.users = PostgresUserRepository(self.repository.engine)
        self.datasets = PostgresDatasetRepository(self.repository.engine)

    def directory_users(self, principal: Principal):
        # Authenticated employees can resolve colleagues for explicit sharing.
        return [user for user in self.users.list_all() if user.is_active and not user.is_technical]

    def create_group(self, payload: GroupCreate, principal: Principal) -> AccessGroup:
        now = datetime.now(timezone.utc)
        group = AccessGroup(
            id=str(uuid4()), name=payload.name.strip(), description=payload.description.strip(),
            is_active=True, owner_id=principal.user_id, created_by=principal.user_id,
            updated_by=principal.user_id, created_at=now, updated_at=now,
        )
        owner_membership = GroupMembership(
            id=str(uuid4()), group_id=group.id, user_id=principal.user_id,
            membership_role=MembershipRole.OWNER, added_by=principal.user_id, created_at=now,
        )
        try:
            self.repository.add_group(group, owner_membership)
        except DuplicateAccessRecord as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        self._audit(principal, "group.created", "group", group.id, new=group.__dict__)
        return group

    def list_groups(self, principal: Principal) -> list[AccessGroup]:
        groups = self.repository.list_groups()
        if principal.is_administrator:
            return groups
        memberships = set(self.repository.group_ids_for_user(principal.user_id))
        return [group for group in groups if group.owner_id == principal.user_id or group.id in memberships]

    def update_group(self, group_id: str, payload: GroupUpdate, principal: Principal) -> AccessGroup:
        group = self._managed_group(group_id, principal)
        previous = dict(group.__dict__)
        group.name = payload.name.strip()
        group.description = payload.description.strip()
        group.is_active = payload.is_active
        group.updated_by = principal.user_id
        group.updated_at = datetime.now(timezone.utc)
        self.repository.update_group(group)
        self._audit(principal, "group.updated", "group", group.id, previous, group.__dict__)
        return group

    def delete_group(self, group_id: str, principal: Principal) -> None:
        group = self._managed_group(group_id, principal)
        self.repository.delete_group(group_id)
        self._audit(principal, "group.deleted", "group", group_id, group.__dict__)

    def list_members(self, group_id: str, principal: Principal) -> list[GroupMembership]:
        self._visible_group(group_id, principal)
        return self.repository.list_memberships(group_id)

    def upsert_member(self, group_id: str, payload: MembershipUpsert, principal: Principal) -> GroupMembership:
        group = self._managed_group(group_id, principal)
        if payload.membership_role == MembershipRole.OWNER:
            raise HTTPException(status_code=422, detail="Group ownership is assigned only when the group is created")
        user = self.users.get(payload.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.is_technical:
            raise HTTPException(status_code=422, detail="Technical accounts cannot be group members")
        if user.id == group.owner_id:
            raise HTTPException(status_code=409, detail="The group owner membership cannot be changed")
        membership = GroupMembership(
            id=str(uuid4()), group_id=group_id, user_id=user.id,
            membership_role=payload.membership_role, added_by=principal.user_id,
        )
        result = self.repository.upsert_membership(membership)
        self._audit(principal, "group.member_upserted", "user", user.id, new={
            "group_id": group_id, "membership_role": payload.membership_role.value,
        })
        return result

    def remove_member(self, group_id: str, user_id: str, principal: Principal) -> None:
        group = self._managed_group(group_id, principal)
        if user_id == group.owner_id:
            raise HTTPException(status_code=409, detail="The group owner cannot be removed")
        self.repository.remove_membership(group_id, user_id)
        self._audit(principal, "group.member_removed", "user", user_id, previous={"group_id": group_id})

    def list_bc_grants(self, business_case_id: str, principal: Principal) -> list[BusinessCaseGrant]:
        self.policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.MANAGER)
        return self.repository.list_bc_grants(business_case_id)

    def grant_business_case(self, business_case_id: str, payload: BusinessCaseGrantCreate, principal: Principal) -> BusinessCaseGrant:
        actor_role = self.policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.MANAGER)
        if payload.access_role == BusinessCaseAccessRole.OWNER and actor_role != BusinessCaseAccessRole.OWNER and not principal.is_administrator:
            raise HTTPException(status_code=403, detail="Only an owner can grant owner access")
        if actor_role == BusinessCaseAccessRole.MANAGER and BC_ROLE_RANK[payload.access_role] > BC_ROLE_RANK[BusinessCaseAccessRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Manager cannot grant this role")
        self._validate_subject(payload.subject_type, payload.subject_id)
        now = datetime.now(timezone.utc)
        grant = BusinessCaseGrant(
            id=str(uuid4()), business_case_id=business_case_id,
            subject_type=payload.subject_type, subject_id=payload.subject_id,
            access_role=payload.access_role, granted_by=principal.user_id,
            created_at=now, updated_at=now, expires_at=payload.expires_at,
        )
        result = self.repository.upsert_bc_grant(grant)
        self._audit(principal, "business_case.grant_upserted", payload.subject_type.value, payload.subject_id,
                    resource_kind="business_case", resource_id=business_case_id,
                    new={"access_role": payload.access_role.value, "expires_at": str(payload.expires_at or "")})
        return result

    def revoke_business_case(self, business_case_id: str, grant_id: str, principal: Principal) -> None:
        self.policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.MANAGER)
        grant = self.repository.get_bc_grant(grant_id)
        if grant is None or grant.business_case_id != business_case_id:
            raise HTTPException(status_code=404, detail="Grant not found")
        self.repository.delete_bc_grant(grant_id)
        self._audit(principal, "business_case.grant_revoked", grant.subject_type.value, grant.subject_id,
                    resource_kind="business_case", resource_id=business_case_id,
                    previous={"access_role": grant.access_role.value})

    def list_resource_grants(self, kind: ResourceKind, resource_id: str, principal: Principal) -> list[ResourceGrant]:
        owner_id = self._resource_owner(kind, resource_id)
        self.policy.require_resource(principal, kind, resource_id, owner_id, ResourceAccessRole.OWNER)
        return self.repository.list_resource_grants(kind, resource_id)

    def grant_resource(self, payload: ResourceGrantCreate, principal: Principal) -> ResourceGrant:
        owner_id = self._resource_owner(payload.resource_kind, payload.resource_id)
        self.policy.require_resource(principal, payload.resource_kind, payload.resource_id, owner_id, ResourceAccessRole.OWNER)
        if payload.resource_kind in {ResourceKind.DATASET, ResourceKind.DATA_VIEW}:
            with self.repository.engine.begin() as connection:
                attachments = connection.execute(select(func.count()).select_from(business_case_data_attachments_table).where(
                    business_case_data_attachments_table.c.data_asset_id == payload.resource_id
                )).scalar_one()
            if attachments:
                raise HTTPException(status_code=409, detail="Objects attached to a Business Case must be shared through that Business Case")
        self._validate_subject(payload.subject_type, payload.subject_id)
        now = datetime.now(timezone.utc)
        grant = ResourceGrant(
            id=str(uuid4()), resource_kind=payload.resource_kind, resource_id=payload.resource_id,
            subject_type=payload.subject_type, subject_id=payload.subject_id,
            access_role=payload.access_role, granted_by=principal.user_id,
            created_at=now, updated_at=now, expires_at=payload.expires_at,
        )
        result = self.repository.upsert_resource_grant(grant)
        self._audit(principal, "resource.grant_upserted", payload.subject_type.value, payload.subject_id,
                    payload.resource_kind.value, payload.resource_id, new={"access_role": payload.access_role.value})
        return result

    def revoke_resource(self, grant_id: str, principal: Principal) -> None:
        grant = self.repository.get_resource_grant(grant_id)
        if grant is None:
            raise HTTPException(status_code=404, detail="Grant not found")
        owner_id = self._resource_owner(grant.resource_kind, grant.resource_id)
        self.policy.require_resource(principal, grant.resource_kind, grant.resource_id, owner_id, ResourceAccessRole.OWNER)
        self.repository.delete_resource_grant(grant_id)
        self._audit(principal, "resource.grant_revoked", grant.subject_type.value, grant.subject_id,
                    grant.resource_kind.value, grant.resource_id, previous={"access_role": grant.access_role.value})

    def audit_events(self, principal: Principal):
        if not principal.is_administrator:
            raise HTTPException(status_code=403, detail="Administrator role required")
        return self.repository.list_audit()

    def _visible_group(self, group_id: str, principal: Principal) -> AccessGroup:
        group = self.repository.get_group(group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        if principal.is_administrator or group.owner_id == principal.user_id or group_id in self.repository.group_ids_for_user(principal.user_id):
            return group
        raise HTTPException(status_code=404, detail="Group not found")

    def _managed_group(self, group_id: str, principal: Principal) -> AccessGroup:
        group = self._visible_group(group_id, principal)
        if principal.is_administrator or group.owner_id == principal.user_id:
            return group
        membership = next((item for item in self.repository.list_memberships(group_id) if item.user_id == principal.user_id), None)
        if membership and membership.membership_role in {MembershipRole.MANAGER, MembershipRole.OWNER}:
            return group
        raise HTTPException(status_code=403, detail="Group manager role required")

    def _validate_subject(self, subject_type: SubjectType, subject_id: str) -> None:
        if subject_type == SubjectType.USER:
            user = self.users.get(subject_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=404, detail="User not found")
        else:
            group = self.repository.get_group(subject_id)
            if group is None or not group.is_active:
                raise HTTPException(status_code=404, detail="Group not found")

    def _resource_owner(self, kind: ResourceKind, resource_id: str) -> str:
        if kind in {ResourceKind.DATASET, ResourceKind.DATA_VIEW}:
            asset = self.datasets.get(resource_id)
            if asset is None:
                raise HTTPException(status_code=404, detail="Resource not found")
            return asset.owner_id
        raise HTTPException(status_code=422, detail="Direct sharing is not available for this resource kind yet")

    def _audit(self, principal: Principal, action: str, subject_type: str, subject_id: str,
               resource_kind: str = "", resource_id: str = "", previous=None, new=None) -> None:
        def serializable(value):
            if value is None:
                return {}
            return {key: (item.value if hasattr(item, "value") else str(item) if isinstance(item, datetime) else item)
                    for key, item in value.items()}
        self.repository.add_audit(AuditEvent(
            id=str(uuid4()), actor_id=principal.user_id, action=action,
            subject_type=subject_type, subject_id=subject_id,
            resource_kind=resource_kind, resource_id=resource_id,
            previous_state=serializable(previous), new_state=serializable(new),
        ))
