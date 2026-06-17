from fastapi import APIRouter

from app.modules.analysis.router import router as analysis_router
from app.modules.auth.router import router as auth_router
from app.modules.datasets.router import router as datasets_router
from app.modules.exports.router import router as exports_router
from app.modules.models.router import router as models_router
from app.modules.serving.router import router as serving_router
from app.modules.sharing.router import router as sharing_router
from app.modules.users.router import router as users_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(datasets_router)
api_router.include_router(analysis_router)
api_router.include_router(models_router)
api_router.include_router(serving_router)
api_router.include_router(sharing_router)
api_router.include_router(exports_router)
