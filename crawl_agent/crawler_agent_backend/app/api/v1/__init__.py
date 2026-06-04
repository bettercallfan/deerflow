from fastapi import APIRouter

from app.api.v1.model_configs import router as model_config_router
from app.api.v1.tasks import router as task_router
from app.api.v1.schedules import router as schedule_router
from app.api.v1.storage import router as storage_router

api_router = APIRouter()
api_router.include_router(model_config_router)
api_router.include_router(task_router)
api_router.include_router(schedule_router)
api_router.include_router(storage_router)
