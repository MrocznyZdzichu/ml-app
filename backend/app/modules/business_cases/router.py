from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.business_cases.schemas import (
    BusinessCaseCreate,
    BusinessCaseUpdate,
    BusinessCaseDataAttachmentCreate,
    BusinessCaseDataAttachmentRead,
    BusinessCaseDataAttachmentUpdate,
    BusinessCaseRead,
    BusinessCaseOwnershipTransfer,
)
from app.modules.business_cases.service import BusinessCaseService
from app.modules.business_cases.lineage import ArtifactDependencyResolver
from app.modules.sharing.domain import BC_ROLE_RANK, BusinessCaseAccessRole

router = APIRouter(prefix="/business-cases", tags=["business-cases"])
service = BusinessCaseService()
dependency_resolver = ArtifactDependencyResolver()


@router.get("/dependencies/{reference_id}")
def get_artifact_dependencies(
    reference_id: str,
    artifact_type: str | None = Query(default=None, max_length=64),
    principal: Principal = Depends(require_user),
) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for business_case in service.list_business_cases(principal):
        role = BusinessCaseAccessRole(business_case.access_role)
        if BC_ROLE_RANK[role] < BC_ROLE_RANK[BusinessCaseAccessRole.READER]:
            continue
        for edge in dependency_resolver.resolve(
            owner_id=business_case.owner_id,
            reference_id=reference_id,
            artifact_type=artifact_type,
        ):
            if edge.get("business_case_id") and edge["business_case_id"] != business_case.id:
                continue
            key = (
                str(edge.get("direction", "")), str(edge.get("role", "")),
                str(edge.get("artifact_type", "")), str(edge.get("reference_id", "")),
            )
            if key not in seen:
                seen.add(key)
                edges.append(edge)
    return edges


@router.post("", response_model=BusinessCaseRead, status_code=201)
def create_business_case(
    payload: BusinessCaseCreate,
    principal: Principal = Depends(require_user),
) -> BusinessCaseRead:
    return BusinessCaseRead.model_validate(service.create_business_case(payload, principal))


@router.get("", response_model=list[BusinessCaseRead])
def list_business_cases(principal: Principal = Depends(require_user)) -> list[BusinessCaseRead]:
    return [BusinessCaseRead.model_validate(item) for item in service.list_business_cases(principal)]


@router.get("/{business_case_id}", response_model=BusinessCaseRead)
def get_business_case(
    business_case_id: str,
    principal: Principal = Depends(require_user),
) -> BusinessCaseRead:
    return BusinessCaseRead.model_validate(service.get_business_case(business_case_id, principal))


@router.patch("/{business_case_id}", response_model=BusinessCaseRead)
def update_business_case(
    business_case_id: str,
    payload: BusinessCaseUpdate,
    principal: Principal = Depends(require_user),
) -> BusinessCaseRead:
    return BusinessCaseRead.model_validate(service.update_business_case(business_case_id, payload, principal))


@router.post("/{business_case_id}/transfer-ownership", response_model=BusinessCaseRead)
def transfer_business_case_ownership(
    business_case_id: str,
    payload: BusinessCaseOwnershipTransfer,
    principal: Principal = Depends(require_user),
) -> BusinessCaseRead:
    return BusinessCaseRead.model_validate(service.transfer_ownership(business_case_id, payload, principal))


@router.post("/{business_case_id}/data-attachments", response_model=BusinessCaseDataAttachmentRead, status_code=201)
def attach_data_asset(
    business_case_id: str,
    payload: BusinessCaseDataAttachmentCreate,
    principal: Principal = Depends(require_user),
) -> BusinessCaseDataAttachmentRead:
    return BusinessCaseDataAttachmentRead.model_validate(
        service.attach_data_asset(business_case_id, payload, principal)
    )


@router.get("/{business_case_id}/data-attachments", response_model=list[BusinessCaseDataAttachmentRead])
def list_data_attachments(
    business_case_id: str,
    principal: Principal = Depends(require_user),
) -> list[BusinessCaseDataAttachmentRead]:
    return [
        BusinessCaseDataAttachmentRead.model_validate(item)
        for item in service.list_data_attachments(business_case_id, principal)
    ]


@router.patch("/{business_case_id}/data-attachments/{attachment_id}", response_model=BusinessCaseDataAttachmentRead)
def update_data_attachment(
    business_case_id: str,
    attachment_id: str,
    payload: BusinessCaseDataAttachmentUpdate,
    principal: Principal = Depends(require_user),
) -> BusinessCaseDataAttachmentRead:
    return BusinessCaseDataAttachmentRead.model_validate(
        service.update_data_attachment(business_case_id, attachment_id, payload, principal)
    )


@router.delete("/{business_case_id}/data-attachments/{attachment_id}")
def delete_data_attachment(
    business_case_id: str,
    attachment_id: str,
    principal: Principal = Depends(require_user),
) -> dict[str, bool]:
    service.delete_data_attachment(business_case_id, attachment_id, principal)
    return {"deleted": True}
