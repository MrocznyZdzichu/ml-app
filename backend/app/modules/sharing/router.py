from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.sharing.schemas import ShareGrantCreate, ShareGrantRead
from app.modules.sharing.service import SharingService

router = APIRouter(prefix="/sharing", tags=["sharing"])
service = SharingService()


@router.post("/grants", response_model=ShareGrantRead, status_code=201)
def share_resource(
    payload: ShareGrantCreate,
    principal: Principal = Depends(require_user),
) -> ShareGrantRead:
    return ShareGrantRead.model_validate(service.share(payload, principal))


@router.get("/grants", response_model=list[ShareGrantRead])
def list_grants(principal: Principal = Depends(require_user)) -> list[ShareGrantRead]:
    return [ShareGrantRead.model_validate(grant) for grant in service.list_grants(principal)]
