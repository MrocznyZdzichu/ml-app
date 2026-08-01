from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.sharing.domain import AccessRequestStatus, ResourceKind
from app.modules.sharing.schemas import (
    AuditEventRead,
    BusinessCaseAccessRequestCreate,
    BusinessCaseAccessRequestDecision,
    BusinessCaseAccessRequestRead,
    BusinessCaseAccessRequestReject,
    BusinessCaseGrantCreate,
    BusinessCaseGrantRead,
    DirectoryUserRead,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    MembershipRead,
    MembershipUpsert,
    ResourceGrantCreate,
    ResourceGrantRead,
)
from app.modules.sharing.service import SharingService
from app.shared.pagination import OffsetPage
from app.core.container import get_container

router = APIRouter(prefix="/sharing", tags=["sharing"])
service: SharingService = get_container().sharing


@router.get("/directory/users", response_model=list[DirectoryUserRead])
def directory_users(principal: Principal = Depends(require_user)):
    return [DirectoryUserRead(id=u.id, login_name=u.login_name, email=u.email, display_name=u.display_name, is_active=u.is_active)
            for u in service.directory_users(principal)]


@router.get("/directory/users/page", response_model=OffsetPage[DirectoryUserRead])
def page_directory_users(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    principal: Principal = Depends(require_user),
) -> OffsetPage[DirectoryUserRead]:
    users, total = service.page_directory_users(
        principal,
        limit=limit,
        offset=offset,
        search=search,
    )
    return OffsetPage[DirectoryUserRead].build(
        items=[
            DirectoryUserRead(
                id=user.id,
                login_name=user.login_name,
                email=user.email,
                display_name=user.display_name,
                is_active=user.is_active,
            )
            for user in users
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/groups", response_model=GroupRead, status_code=201)
def create_group(payload: GroupCreate, principal: Principal = Depends(require_user)):
    return service.create_group(payload, principal)


@router.get("/groups", response_model=list[GroupRead])
def list_groups(principal: Principal = Depends(require_user)):
    return service.list_groups(principal)


@router.get("/groups/page", response_model=OffsetPage[GroupRead])
def page_groups(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    is_active: bool | None = Query(default=None),
    principal: Principal = Depends(require_user),
) -> OffsetPage[GroupRead]:
    groups, total = service.page_groups(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        is_active=is_active,
    )
    return OffsetPage[GroupRead].build(
        items=[GroupRead.model_validate(group) for group in groups],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group(group_id: str, payload: GroupUpdate, principal: Principal = Depends(require_user)):
    return service.update_group(group_id, payload, principal)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: str, principal: Principal = Depends(require_user)):
    service.delete_group(group_id, principal)


@router.get("/groups/{group_id}/members", response_model=list[MembershipRead])
def list_members(group_id: str, principal: Principal = Depends(require_user)):
    return service.list_members(group_id, principal)


@router.get(
    "/groups/{group_id}/members/page",
    response_model=OffsetPage[MembershipRead],
)
def page_members(
    group_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> OffsetPage[MembershipRead]:
    memberships, total = service.page_members(
        group_id,
        principal,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[MembershipRead].build(
        items=[
            MembershipRead.model_validate(membership)
            for membership in memberships
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/groups/{group_id}/members", response_model=MembershipRead)
def upsert_member(group_id: str, payload: MembershipUpsert, principal: Principal = Depends(require_user)):
    return service.upsert_member(group_id, payload, principal)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
def remove_member(group_id: str, user_id: str, principal: Principal = Depends(require_user)):
    service.remove_member(group_id, user_id, principal)


@router.get("/business-cases/{business_case_id}/grants", response_model=list[BusinessCaseGrantRead])
def list_bc_grants(business_case_id: str, principal: Principal = Depends(require_user)):
    return service.list_bc_grants(business_case_id, principal)


@router.get(
    "/business-cases/{business_case_id}/grants/page",
    response_model=OffsetPage[BusinessCaseGrantRead],
)
def page_bc_grants(
    business_case_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> OffsetPage[BusinessCaseGrantRead]:
    items, total = service.page_bc_grants(
        business_case_id,
        principal,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[BusinessCaseGrantRead].build(
        [BusinessCaseGrantRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/business-cases/{business_case_id}/grants", response_model=BusinessCaseGrantRead)
def grant_bc(business_case_id: str, payload: BusinessCaseGrantCreate, principal: Principal = Depends(require_user)):
    return service.grant_business_case(business_case_id, payload, principal)


@router.delete("/business-cases/{business_case_id}/grants/{grant_id}", status_code=204)
def revoke_bc(business_case_id: str, grant_id: str, principal: Principal = Depends(require_user)):
    service.revoke_business_case(business_case_id, grant_id, principal)


@router.post(
    "/business-cases/{business_case_id}/access-requests",
    response_model=BusinessCaseAccessRequestRead,
    status_code=201,
)
def create_business_case_access_request(
    business_case_id: str,
    payload: BusinessCaseAccessRequestCreate,
    principal: Principal = Depends(require_user),
) -> BusinessCaseAccessRequestRead:
    return BusinessCaseAccessRequestRead.model_validate(
        service.create_business_case_access_request(
            business_case_id,
            payload,
            principal,
        )
    )


@router.get(
    "/access-requests/page",
    response_model=OffsetPage[BusinessCaseAccessRequestRead],
)
def page_business_case_access_requests(
    box: str = Query(default="incoming", max_length=32),
    request_status: AccessRequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> OffsetPage[BusinessCaseAccessRequestRead]:
    items, total = service.page_business_case_access_requests(
        principal,
        box=box,
        status_filter=request_status,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[BusinessCaseAccessRequestRead].build(
        [BusinessCaseAccessRequestRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/access-requests/{request_id}/approve",
    response_model=BusinessCaseAccessRequestRead,
)
def approve_business_case_access_request(
    request_id: str,
    payload: BusinessCaseAccessRequestDecision,
    principal: Principal = Depends(require_user),
) -> BusinessCaseAccessRequestRead:
    return BusinessCaseAccessRequestRead.model_validate(
        service.approve_business_case_access_request(
            request_id,
            payload,
            principal,
        )
    )


@router.post(
    "/access-requests/{request_id}/reject",
    response_model=BusinessCaseAccessRequestRead,
)
def reject_business_case_access_request(
    request_id: str,
    payload: BusinessCaseAccessRequestReject,
    principal: Principal = Depends(require_user),
) -> BusinessCaseAccessRequestRead:
    return BusinessCaseAccessRequestRead.model_validate(
        service.reject_business_case_access_request(
            request_id,
            payload,
            principal,
        )
    )


@router.get("/resources/{resource_kind}/{resource_id}/grants", response_model=list[ResourceGrantRead])
def list_resource_grants(resource_kind: ResourceKind, resource_id: str, principal: Principal = Depends(require_user)):
    return service.list_resource_grants(resource_kind, resource_id, principal)


@router.get(
    "/resources/{resource_kind}/{resource_id}/grants/page",
    response_model=OffsetPage[ResourceGrantRead],
)
def page_resource_grants(
    resource_kind: ResourceKind,
    resource_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> OffsetPage[ResourceGrantRead]:
    items, total = service.page_resource_grants(
        resource_kind,
        resource_id,
        principal,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[ResourceGrantRead].build(
        [ResourceGrantRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/resources/grants", response_model=ResourceGrantRead)
def grant_resource(payload: ResourceGrantCreate, principal: Principal = Depends(require_user)):
    return service.grant_resource(payload, principal)


@router.delete("/resources/grants/{grant_id}", status_code=204)
def revoke_resource(grant_id: str, principal: Principal = Depends(require_user)):
    service.revoke_resource(grant_id, principal)


@router.get("/audit", response_model=list[AuditEventRead])
def audit_events(principal: Principal = Depends(require_user)):
    return service.audit_events(principal)
