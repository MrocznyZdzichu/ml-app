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
from app.modules.sharing.domain import BusinessCaseAccessRole, ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import access_policy
from app.modules.auth.repository import PostgresUserRepository
from app.modules.sharing.domain import AuditEvent
from app.modules.sharing.repository import PostgresSharingRepository


business_case_repository = PostgresBusinessCaseRepository()


class BusinessCaseService:
    def __init__(self, repository: BusinessCaseRepository | None = None) -> None:
        self.repository = repository or business_case_repository

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
        allowed = access_policy.accessible_business_case_ids(principal)
        items = self.repository.list_all_business_cases() if allowed is None else [
            item for item in self.repository.list_all_business_cases() if item.id in allowed
        ]
        for item in items:
            role = access_policy.business_case_role(principal, item.id)
            item.access_role = role.value if role else ""
        return items

    def get_business_case(self, business_case_id: str, principal: Principal) -> BusinessCase:
        business_case = self.repository.get_business_case(business_case_id)
        if not business_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business case not found")
        role = access_policy.require_business_case(principal, business_case_id)
        business_case.access_role = role.value
        return business_case

    def update_business_case(
        self,
        business_case_id: str,
        payload: BusinessCaseUpdate,
        principal: Principal,
    ) -> BusinessCase:
        business_case = self.get_business_case(business_case_id, principal)
        role = access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
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
        normalized = name.casefold()
        if any(
            item.id != exclude_id and item.name.strip().casefold() == normalized
            for item in self.repository.list_all_business_cases()
        ):
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
        business_case = self.get_business_case(business_case_id, principal)
        access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.OWNER)
        new_owner = PostgresUserRepository().get(payload.new_owner_id)
        if new_owner is None or not new_owner.is_active:
            raise HTTPException(status_code=404, detail="New owner not found or inactive")
        previous_owner = business_case.owner_id
        business_case.owner_id = new_owner.id
        business_case.updated_by = principal.user_id
        business_case.updated_at = datetime.now(timezone.utc)
        self.repository.update_business_case(business_case)
        PostgresSharingRepository().add_audit(AuditEvent(
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
        business_case = self.get_business_case(business_case_id, principal)
        access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
        # Contributors may attach data they can at least read; administrators bypass this centrally.
        from app.modules.datasets.repository import PostgresDatasetRepository
        asset = PostgresDatasetRepository().get(payload.data_asset_id)
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
        business_case = self.get_business_case(business_case_id, principal)
        access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.READER)
        return self.repository.list_data_attachments(business_case.id)

    def update_data_attachment(
        self,
        business_case_id: str,
        attachment_id: str,
        payload: BusinessCaseDataAttachmentUpdate,
        principal: Principal,
    ) -> BusinessCaseDataAttachment:
        business_case = self.get_business_case(business_case_id, principal)
        access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
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
        business_case = self.get_business_case(business_case_id, principal)
        access_policy.require_business_case(principal, business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
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
