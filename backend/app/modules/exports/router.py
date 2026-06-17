from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.exports.schemas import ExportJobRead, ExportRequest
from app.modules.exports.service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])
service = ExportService()


@router.post("", response_model=ExportJobRead, status_code=201)
def create_export(
    payload: ExportRequest,
    principal: Principal = Depends(require_user),
) -> ExportJobRead:
    return ExportJobRead.model_validate(service.create_export(payload, principal))


@router.get("", response_model=list[ExportJobRead])
def list_exports(principal: Principal = Depends(require_user)) -> list[ExportJobRead]:
    return [ExportJobRead.model_validate(job) for job in service.list_exports(principal)]
