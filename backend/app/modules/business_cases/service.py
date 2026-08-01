from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.security import Principal
from app.modules.business_cases.domain import (
    Artifact,
    ArtifactOrigin,
    ArtifactType,
    BusinessCase,
    BusinessCaseCatalogEntry,
    BusinessCaseDataAttachment,
    DataArtifactKind,
)
from app.modules.business_cases.repository import BusinessCaseRepository, PostgresBusinessCaseRepository
from app.modules.business_cases.schemas import (
    BusinessCaseCreate,
    BusinessCaseUpdate,
    BusinessCaseDataAttachmentCreate,
    BusinessCaseDataAttachmentUpdate,
    BusinessCaseOwnershipTransfer,
)
from app.modules.sharing.domain import BC_ROLE_RANK, BusinessCaseAccessRole, ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import access_policy
from app.modules.auth.repository import PostgresUserRepository, UserRepository
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.sharing.domain import AuditEvent
from app.modules.sharing.repository import PostgresSharingRepository
from app.modules.business_cases.admin_deletion import (
    BusinessCaseCascadeDeletion,
    PostgresBusinessCaseAdminDeletion,
)


business_case_repository = PostgresBusinessCaseRepository()


class BusinessCaseService:
    def __init__(
        self,
        repository: BusinessCaseRepository | None = None,
        users: UserRepository | None = None,
        datasets: DatasetRepository | None = None,
        audit_repository: PostgresSharingRepository | None = None,
    ) -> None:
        self.repository = repository or business_case_repository
        self.users = users or PostgresUserRepository()
        self.datasets = datasets or PostgresDatasetRepository()
        self.audit_repository = audit_repository or PostgresSharingRepository()

    def delete_business_case_as_root(
        self, business_case_id: str, principal: Principal
    ) -> BusinessCaseCascadeDeletion:
        """Permanently delete one BC and its case-owned state for test cleanup."""
        if principal.user_id != "root" or not principal.is_administrator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the protected root administrator can permanently delete a Business Case",
            )
        if not isinstance(self.repository, PostgresBusinessCaseRepository):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Permanent Business Case deletion requires the PostgreSQL repository",
            )
        deletion = PostgresBusinessCaseAdminDeletion(self.repository.engine).delete(business_case_id)
        if not deletion.deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business case not found")
        self.audit_repository.add_audit(AuditEvent(
            id=str(uuid4()), actor_id=principal.user_id, action="business_case.permanently_deleted",
            subject_type="business_case", subject_id=business_case_id,
            resource_kind="business_case", resource_id=business_case_id,
            new_state={"deleted": deletion.deleted},
            reason="Root administrator permanent cascade deletion",
        ))
        deletion_service = PostgresBusinessCaseAdminDeletion(self.repository.engine)
        deletion_service.delete_storage(deletion)
        return deletion

    def create_business_case(self, payload: BusinessCaseCreate, principal: Principal) -> BusinessCase:
        name = payload.name.strip()
        self._require_unique_name(name)
        now = datetime.now(timezone.utc)
        business_case = BusinessCase(
            id=str(uuid4()),
            owner_id=principal.user_id,
            name=name,
            description=payload.description,
            problem_type=payload.problem_type,
            status=payload.status,
            business_owner=payload.business_owner,
            primary_metric=payload.primary_metric,
            target_column=payload.target_column,
            business_goal=payload.business_goal,
            success_criteria=payload.success_criteria,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            return self.repository.add_business_case(business_case)
        except IntegrityError as exc:
            raise self._name_conflict(name) from exc

    def list_business_cases(self, principal: Principal) -> list[BusinessCase]:
        roles = access_policy.accessible_business_case_roles(principal)
        items = (
            self.repository.list_all_business_cases()
            if roles is None
            else self.repository.list_business_cases_by_ids(set(roles))
        )
        for item in items:
            role = BusinessCaseAccessRole.OWNER if roles is None else roles.get(item.id)
            item.access_role = role.value if role else ""
        return items

    def page_business_cases(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str = "",
        manageable_only: bool = False,
    ) -> tuple[list[BusinessCase], int]:
        roles = access_policy.accessible_business_case_roles(principal)
        if manageable_only and roles is not None:
            roles = {
                business_case_id: role
                for business_case_id, role in roles.items()
                if BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.MANAGER]
            }
        items, total = self.repository.page_business_cases(
            None if roles is None else set(roles),
            limit=limit,
            offset=offset,
            search=search,
        )
        for item in items:
            role = BusinessCaseAccessRole.OWNER if roles is None else roles.get(item.id)
            item.access_role = role.value if role else ""
        return items, total

    def page_business_case_catalog(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCaseCatalogEntry], int]:
        items, total = self.repository.page_business_case_catalog(
            limit=limit,
            offset=offset,
            search=search,
        )
        business_case_ids = {item.id for item in items}
        roles = access_policy.business_case_roles(principal, business_case_ids)
        pending_requests = self.audit_repository.pending_access_request_statuses(
            principal.user_id,
            business_case_ids,
        )
        return [
            BusinessCaseCatalogEntry(
                id=item.id,
                name=item.name,
                status=item.status,
                access_role=roles[item.id].value if item.id in roles else "",
                request_status=(
                    pending_requests[item.id].value
                    if item.id in pending_requests
                    else ""
                ),
            )
            for item in items
        ], total

    def get_business_case(
        self,
        business_case_id: str,
        principal: Principal,
        *,
        minimum: BusinessCaseAccessRole = BusinessCaseAccessRole.REPORT_VIEWER,
    ) -> BusinessCase:
        business_case = self.repository.get_business_case(business_case_id)
        if not business_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business case not found")
        role = access_policy.require_business_case(principal, business_case_id, minimum)
        business_case.access_role = role.value
        return business_case

    def update_business_case(
        self,
        business_case_id: str,
        payload: BusinessCaseUpdate,
        principal: Principal,
    ) -> BusinessCase:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.CONTRIBUTOR,
        )
        role = BusinessCaseAccessRole(business_case.access_role)
        if (
            payload.status.value == "archived" or business_case.status.value == "archived"
        ) and role != BusinessCaseAccessRole.OWNER:
            raise HTTPException(status_code=403, detail="Only an owner can archive or modify an archived Business Case")
        name = payload.name.strip()
        self._require_unique_name(name, exclude_id=business_case.id)
        business_case.name = name
        business_case.description = payload.description
        business_case.problem_type = payload.problem_type
        business_case.status = payload.status
        business_case.business_owner = payload.business_owner
        business_case.primary_metric = payload.primary_metric
        business_case.target_column = payload.target_column
        business_case.business_goal = payload.business_goal
        business_case.success_criteria = payload.success_criteria
        business_case.updated_by = principal.user_id
        business_case.updated_at = datetime.now(timezone.utc)
        try:
            return self.repository.update_business_case(business_case)
        except IntegrityError as exc:
            raise self._name_conflict(name) from exc

    def _require_unique_name(self, name: str, *, exclude_id: str = "") -> None:
        if self.repository.business_case_name_exists(name, exclude_id=exclude_id):
            raise self._name_conflict(name)

    @staticmethod
    def _name_conflict(name: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Business Case name {name!r} is already in use",
        )

    def transfer_ownership(
        self,
        business_case_id: str,
        payload: BusinessCaseOwnershipTransfer,
        principal: Principal,
    ) -> BusinessCase:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.OWNER,
        )
        new_owner = self.users.get(payload.new_owner_id)
        if new_owner is None or not new_owner.is_active:
            raise HTTPException(status_code=404, detail="New owner not found or inactive")
        previous_owner = business_case.owner_id
        business_case.owner_id = new_owner.id
        business_case.updated_by = principal.user_id
        business_case.updated_at = datetime.now(timezone.utc)
        self.repository.update_business_case(business_case)
        self.audit_repository.add_audit(AuditEvent(
            id=str(uuid4()), actor_id=principal.user_id, action="business_case.ownership_transferred",
            subject_type="user", subject_id=new_owner.id,
            resource_kind="business_case", resource_id=business_case.id,
            previous_state={"owner_id": previous_owner}, new_state={"owner_id": new_owner.id},
            reason=payload.reason,
        ))
        business_case.access_role = BusinessCaseAccessRole.OWNER.value
        return business_case

    def attach_data_asset(
        self,
        business_case_id: str,
        payload: BusinessCaseDataAttachmentCreate,
        principal: Principal,
    ) -> BusinessCaseDataAttachment:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.CONTRIBUTOR,
        )
        # Contributors may attach data they can at least read; administrators bypass this centrally.
        asset = self.datasets.get(payload.data_asset_id)
        if asset is not None:
            access_policy.require_resource(
                principal,
                ResourceKind.DATA_VIEW if payload.data_asset_kind == DataArtifactKind.DATA_VIEW else ResourceKind.DATASET,
                payload.data_asset_id,
                asset.owner_id,
                ResourceAccessRole.READER,
            )
        artifact_type = ArtifactType.DATA_VIEW if payload.data_asset_kind == DataArtifactKind.DATA_VIEW else ArtifactType.DATASET
        artifact = Artifact(
            id=str(uuid4()),
            owner_id=business_case.owner_id,
            type=artifact_type,
            reference_id=payload.data_asset_id,
            origin=payload.origin,
            business_case_id=business_case.id,
            external_notes=payload.external_notes,
            metadata=dict(payload.metadata),
            created_by=principal.user_id,
        )
        self.repository.add_artifact(artifact)
        attachment = BusinessCaseDataAttachment(
            id=str(uuid4()),
            owner_id=business_case.owner_id,
            business_case_id=business_case.id,
            artifact_id=artifact.id,
            data_asset_id=payload.data_asset_id,
            data_asset_kind=payload.data_asset_kind,
            role=payload.role,
            context_note=payload.context_note,
            primary_key_column=payload.primary_key_column,
            target_column=payload.target_column,
            created_by=principal.user_id,
        )
        return self.repository.add_data_attachment(attachment)

    def list_data_attachments(
        self,
        business_case_id: str,
        principal: Principal,
    ) -> list[BusinessCaseDataAttachment]:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.READER,
        )
        return self.repository.list_data_attachments(business_case.id)

    def page_data_attachments(
        self,
        business_case_id: str,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str = "",
        role: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        deleted_only: bool = False,
    ) -> tuple[list[BusinessCaseDataAttachment], int]:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.READER,
        )
        return self.repository.page_data_attachments(
            business_case.id,
            limit=limit,
            offset=offset,
            search=search,
            role=role,
            pipeline_id=pipeline_id,
            pipeline_type=pipeline_type,
            uploaded_only=uploaded_only,
            deleted_only=deleted_only,
        )

    def update_data_attachment(
        self,
        business_case_id: str,
        attachment_id: str,
        payload: BusinessCaseDataAttachmentUpdate,
        principal: Principal,
    ) -> BusinessCaseDataAttachment:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.CONTRIBUTOR,
        )
        attachment = self._get_owned_data_attachment(business_case.id, attachment_id, principal)
        attachment.role = payload.role
        attachment.context_note = payload.context_note
        attachment.primary_key_column = payload.primary_key_column
        attachment.target_column = payload.target_column
        return self.repository.update_data_attachment(attachment)

    def delete_data_attachment(
        self,
        business_case_id: str,
        attachment_id: str,
        principal: Principal,
    ) -> None:
        business_case = self.get_business_case(
            business_case_id,
            principal,
            minimum=BusinessCaseAccessRole.CONTRIBUTOR,
        )
        self._get_owned_data_attachment(business_case.id, attachment_id, principal)
        self.repository.delete_data_attachment(attachment_id)

    def _get_owned_data_attachment(
        self,
        business_case_id: str,
        attachment_id: str,
        principal: Principal,
    ) -> BusinessCaseDataAttachment:
        attachment = self.repository.get_data_attachment(attachment_id)
        if (
            not attachment
            or attachment.business_case_id != business_case_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business case data attachment not found")
        return attachment

    def register_platform_artifact(
        self,
        *,
        owner_id: str,
        reference_id: str,
        artifact_type: ArtifactType,
        business_case_id: str | None,
        created_by: str,
        metadata: dict,
    ) -> Artifact:
        existing = self.repository.find_artifact(owner_id, reference_id, business_case_id)
        if existing:
            return existing
        artifact = Artifact(
            id=str(uuid4()),
            owner_id=owner_id,
            type=artifact_type,
            reference_id=reference_id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=business_case_id,
            metadata=metadata,
            created_by=created_by,
        )
        return self.repository.add_artifact(artifact)
