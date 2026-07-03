from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.business_cases.schemas import (
    BusinessCaseCreate,
    BusinessCaseUpdate,
    BusinessCaseDataAttachmentCreate,
    BusinessCaseDataAttachmentRead,
    BusinessCaseDataAttachmentUpdate,
    BusinessCaseRead,
)
from app.modules.business_cases.service import BusinessCaseService

router = APIRouter(prefix="/business-cases", tags=["business-cases"])
service = BusinessCaseService()


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
