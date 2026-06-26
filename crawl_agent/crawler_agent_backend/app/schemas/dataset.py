from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DatasetRecordListItem(BaseModel):
    id: int
    task_id: str | None = None
    page_url: str | None = None
    title: str | None = None
    raw_html_hash: str | None = None
    normalized_content_hash: str | None = None
    result_type: str | None = None
    content_preview: str | None = None
    created_at: datetime | None = None


class DatasetRecordDetail(BaseModel):
    id: int
    task_id: str | None = None
    page_url: str | None = None
    title: str | None = None
    raw_html_hash: str | None = None
    normalized_content_hash: str | None = None
    result_type: str | None = None
    result_json: Any | None = None
    result_markdown: str | None = None
    result_html: str | None = None
    created_at: datetime | None = None


class DatasetRecordListResponse(BaseModel):
    items: list[DatasetRecordListItem]
    total: int
    page: int
    page_size: int


class DatasetStatsResponse(BaseModel):
    total_records: int
    markdown_count: int
    json_count: int
    html_count: int
    task_count: int
    latest_created_at: datetime | None = None
