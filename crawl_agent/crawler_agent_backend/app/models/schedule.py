from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ScheduleStatus, ScheduleType


class CrawlSchedule(Base):
    __tablename__ = "crawl_schedule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_type: Mapped[ScheduleType] = mapped_column(Enum(ScheduleType), nullable=False)

    cron_expr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")

    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    status: Mapped[ScheduleStatus] = mapped_column(Enum(ScheduleStatus), default=ScheduleStatus.ACTIVE)

    change_detect_enabled: Mapped[bool] = mapped_column(default=True)
    quick_hash_strategy: Mapped[str] = mapped_column(String(32), default="content_only")
    force_full_crawl_every: Mapped[int] = mapped_column(default=10)
    dedup_enabled: Mapped[bool] = mapped_column(default=True)
    dedup_scope: Mapped[str] = mapped_column(String(32), default="global")

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SiteCheckpoint(Base):
    __tablename__ = "site_checkpoint"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    portal_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    site_quick_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    check_method: Mapped[str] = mapped_column(String(64), default="content_only")

    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskEventLog(Base):
    __tablename__ = "task_event_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExtractionPositionCache(Base):
    __tablename__ = "extraction_position_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query_signature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_structure_key: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    position_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
