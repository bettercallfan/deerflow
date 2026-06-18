from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.enums import OutputMode, StorageConfigType, TaskStatus


class CrawlTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    portal_url: HttpUrl
    query: str = Field(min_length=1)
    output_mode: OutputMode = OutputMode.JSON
    json_schema: dict | list | None = None
    storage_db_type: StorageConfigType | None = None
    max_iterations: int = Field(default=10, ge=1, le=100, description="BrowserAgent max navigation steps")

    dedup_enabled: bool = True
    dedup_scope: str = "global"
    hash_mode: str = "raw+normalized"

    @field_validator("storage_db_type", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrawlTaskRead(BaseModel):
    id: str
    name: str
    portal_url: str
    query: str
    output_mode: OutputMode
    max_iterations: int = 10
    status: TaskStatus
    progress: int
    source: str
    skip_reason: str | None = None
    error_message: str | None = None
    result_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class CrawlTaskResultItem(BaseModel):
    page_id: str
    url: str
    title: str | None = None
    is_duplicate: bool
    duplicate_reason: str
    raw_html_hash: str
    normalized_content_hash: str
    result_type: str | None = None
    result_json: dict | list | None = None
    result_markdown: str | None = None
    result_markdown_ocr: str | None = None


class CrawlTaskDetail(BaseModel):
    task: CrawlTaskRead
    run_stats: dict


class CrawlTaskFingerprint(BaseModel):
    page_id: str
    url: str
    raw_html_hash: str
    normalized_content_hash: str
    is_duplicate: bool
    duplicate_reason: str
    created_at: datetime


class CrawlTaskListResponse(BaseModel):
    items: list[CrawlTaskRead]
    total: int
    page: int
    page_size: int
