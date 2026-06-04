from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OutputMode, TaskStatus


class CrawlTask(Base):
    __tablename__ = "crawl_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    portal_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    output_mode: Mapped[OutputMode] = mapped_column(Enum(OutputMode), nullable=False)
    json_schema: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    schedule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crawl_schedule.id"), nullable=True)

    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    dedup_enabled: Mapped[bool] = mapped_column(default=True)
    dedup_scope: Mapped[str] = mapped_column(String(32), default="global")
    hash_mode: Mapped[str] = mapped_column(String(32), default="raw+normalized")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pages: Mapped[list[CrawlPage]] = relationship("CrawlPage", back_populates="task", cascade="all,delete-orphan")
    runs: Mapped[list[CrawlRun]] = relationship("CrawlRun", back_populates="task", cascade="all,delete-orphan")


class CrawlRun(Base):
    __tablename__ = "crawl_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_task.id"), nullable=False)

    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    site_changed: Mapped[bool | None] = mapped_column(nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    new_pages_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_pages_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_pages_count: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[CrawlTask] = relationship("CrawlTask", back_populates="runs")


class CrawlPage(Base):
    __tablename__ = "crawl_page"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_task.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_run.id"), nullable=False)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)

    raw_html_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    is_duplicate: Mapped[bool] = mapped_column(default=False)
    duplicate_reason: Mapped[str] = mapped_column(String(32), default="NONE")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped[CrawlTask] = relationship("CrawlTask", back_populates="pages")
    results: Mapped[list[CrawlResult]] = relationship("CrawlResult", back_populates="page", cascade="all,delete-orphan")


class CrawlResult(Base):
    __tablename__ = "crawl_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_task.id"), nullable=False)
    page_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_page.id"), nullable=False)

    result_type: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    result_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_markdown_ocr: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    page: Mapped[CrawlPage] = relationship("CrawlPage", back_populates="results")
