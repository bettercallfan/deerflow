from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.scheduler import scheduler
from app.db.base import Base
from app.db.session import engine, SessionLocal
import app.models  # noqa: F401
from app.models.schedule import CrawlSchedule
from app.schemas.common import HealthResponse
from app.services.schedule_service import ScheduleService

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", time=datetime.utcnow())


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

    if settings.scheduler_enabled and not scheduler.running:
        scheduler.start()

    db = SessionLocal()
    try:
        schedule_service = ScheduleService(db)
        schedules = db.scalars(select(CrawlSchedule)).all()
        for schedule in schedules:
            schedule_service.register_job(schedule)
    finally:
        db.close()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
