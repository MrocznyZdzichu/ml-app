from fastapi import APIRouter, Depends, HTTPException

from app.core.security import Principal, require_user
from app.modules.exports.schemas import ExportJobRead, ExportRequest
from app.modules.exports.service import ExportService
from app.core.container import get_container

router = APIRouter(prefix="/exports", tags=["exports"])
service: ExportService = get_container().exports


@router.post("", status_code=501, deprecated=True)
def create_export(
    payload: ExportRequest,
    principal: Principal = Depends(require_user),
) -> None:
    raise HTTPException(status_code=501, detail="Background resource export is unavailable.")


@router.get("", response_model=list[ExportJobRead], deprecated=True)
def list_exports(principal: Principal = Depends(require_user)) -> list[ExportJobRead]:
    return [ExportJobRead.model_validate(job) for job in service.list_exports(principal)]
