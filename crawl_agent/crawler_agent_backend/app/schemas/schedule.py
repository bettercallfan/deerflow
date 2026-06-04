from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import ScheduleStatus, ScheduleType


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    schedule_type: ScheduleType
    cron_expr: str | None = None
    interval_seconds: int | None = None
    interval_days: int = 0
    interval_hours: int = 0
    interval_minutes: int = 0
    timezone: str = "Asia/Shanghai"

    payload: dict

    enabled: bool = True
    change_detect_enabled: bool = True
    quick_hash_strategy: str = "content_only"
    force_full_crawl_every: int = 10
    dedup_enabled: bool = True
    dedup_scope: str = "global"


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = None
    interval_days: int | None = None
    interval_hours: int | None = None
    interval_minutes: int | None = None
    timezone: str | None = None
    payload: dict | None = None
    status: ScheduleStatus | None = None

    change_detect_enabled: bool | None = None
    quick_hash_strategy: str | None = None
    force_full_crawl_every: int | None = None
    dedup_enabled: bool | None = None
    dedup_scope: str | None = None


class ScheduleRead(BaseModel):
    id: str
    name: str
    schedule_type: ScheduleType
    cron_expr: str | None
    interval_seconds: int | None
    interval_days: int = 0
    interval_hours: int = 0
    interval_minutes: int = 0
    timezone: str
    payload: dict
    status: ScheduleStatus

    change_detect_enabled: bool
    quick_hash_strategy: str
    force_full_crawl_every: int
    dedup_enabled: bool
    dedup_scope: str

    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduleListResponse(BaseModel):
    items: list[ScheduleRead]
    total: int
