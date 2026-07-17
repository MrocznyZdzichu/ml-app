from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.sharing.domain import ResourceKind
from app.modules.sharing.schemas import (
    AuditEventRead,
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

router = APIRouter(prefix="/sharing", tags=["sharing"])
service = SharingService()


@router.get("/directory/users", response_model=list[DirectoryUserRead])
def directory_users(principal: Principal = Depends(require_user)):
    return [DirectoryUserRead(id=u.id, login_name=u.login_name, email=u.email, display_name=u.display_name, is_active=u.is_active)
            for u in service.directory_users(principal)]


@router.post("/groups", response_model=GroupRead, status_code=201)
def create_group(payload: GroupCreate, principal: Principal = Depends(require_user)):
    return service.create_group(payload, principal)


@router.get("/groups", response_model=list[GroupRead])
def list_groups(principal: Principal = Depends(require_user)):
    return service.list_groups(principal)


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group(group_id: str, payload: GroupUpdate, principal: Principal = Depends(require_user)):
    return service.update_group(group_id, payload, principal)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: str, principal: Principal = Depends(require_user)):
    service.delete_group(group_id, principal)


@router.get("/groups/{group_id}/members", response_model=list[MembershipRead])
def list_members(group_id: str, principal: Principal = Depends(require_user)):
    return service.list_members(group_id, principal)


@router.put("/groups/{group_id}/members", response_model=MembershipRead)
def upsert_member(group_id: str, payload: MembershipUpsert, principal: Principal = Depends(require_user)):
    return service.upsert_member(group_id, payload, principal)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
def remove_member(group_id: str, user_id: str, principal: Principal = Depends(require_user)):
    service.remove_member(group_id, user_id, principal)


@router.get("/business-cases/{business_case_id}/grants", response_model=list[BusinessCaseGrantRead])
def list_bc_grants(business_case_id: str, principal: Principal = Depends(require_user)):
    return service.list_bc_grants(business_case_id, principal)


@router.put("/business-cases/{business_case_id}/grants", response_model=BusinessCaseGrantRead)
def grant_bc(business_case_id: str, payload: BusinessCaseGrantCreate, principal: Principal = Depends(require_user)):
    return service.grant_business_case(business_case_id, payload, principal)


@router.delete("/business-cases/{business_case_id}/grants/{grant_id}", status_code=204)
def revoke_bc(business_case_id: str, grant_id: str, principal: Principal = Depends(require_user)):
    service.revoke_business_case(business_case_id, grant_id, principal)


@router.get("/resources/{resource_kind}/{resource_id}/grants", response_model=list[ResourceGrantRead])
def list_resource_grants(resource_kind: ResourceKind, resource_id: str, principal: Principal = Depends(require_user)):
    return service.list_resource_grants(resource_kind, resource_id, principal)


@router.put("/resources/grants", response_model=ResourceGrantRead)
def grant_resource(payload: ResourceGrantCreate, principal: Principal = Depends(require_user)):
    return service.grant_resource(payload, principal)


@router.delete("/resources/grants/{grant_id}", status_code=204)
def revoke_resource(grant_id: str, principal: Principal = Depends(require_user)):
    service.revoke_resource(grant_id, principal)


@router.get("/audit", response_model=list[AuditEventRead])
def audit_events(principal: Principal = Depends(require_user)):
    return service.audit_events(principal)
