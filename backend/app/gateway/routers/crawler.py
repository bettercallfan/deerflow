"""Crawler task router — proxies crawl requests to the Crawler Backend."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-center/crawler", tags=["crawler"])

CrawlerBackendURL = os.getenv("CRAWLER_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

OutputMode = Literal["html", "markdown", "json"]
TaskStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "SKIPPED_NO_CHANGE"]


# ── Request schemas ──────────────────────────────────────────────

class CrawlTaskCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    portal_url: str = Field(min_length=1, description="Target website URL to crawl")
    query: str = Field(min_length=1, description="Natural-language description of what to crawl")
    output_mode: OutputMode = Field(default="html", description="Output format: html, markdown, or json")
    json_schema: dict | list | None = Field(default=None, description="JSON schema for structured extraction (json mode only)")
    storage_db_type: str | None = Field(default=None, description="External storage target: mysql, milvus, or null for local")


# ── Response schemas ─────────────────────────────────────────────

class CrawlTaskItem(BaseModel):
    id: str
    name: str
    portal_url: str
    query: str
    output_mode: OutputMode
    status: TaskStatus
    progress: int = 0
    source: str = "manual"
    skip_reason: str | None = None
    error_message: str | None = None
    result_summary: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class CrawlTaskDetail(BaseModel):
    task: CrawlTaskItem
    run_stats: dict[str, Any] = Field(default_factory=dict)


class CrawlResultItem(BaseModel):
    page_id: str
    url: str
    title: str | None = None
    is_duplicate: bool = False
    duplicate_reason: str = "NONE"
    raw_html_hash: str = ""
    normalized_content_hash: str = ""
    result_type: str | None = None
    result_json: dict[str, Any] | list[Any] | None = None
    result_markdown: str | None = None
    result_markdown_ocr: str | None = None


class CrawlTaskResultsResponse(BaseModel):
    items: list[CrawlResultItem]
    total: int = 0


class CrawlTaskListResponse(BaseModel):
    items: list[CrawlTaskItem]
    total: int = 0
    page: int = 1
    page_size: int = 20


# ── HTTP helpers ──────────────────────────────────────────────────

def _crawler_get(path: str, params: dict | None = None) -> dict[str, Any]:
    url = f"{CrawlerBackendURL}/api/v1/{path.lstrip('/')}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to reach Crawler Backend at %s", url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _crawler_post(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    url = f"{CrawlerBackendURL}/api/v1/{path.lstrip('/')}"
    try:
        resp = requests.post(url, json=json_body, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to reach Crawler Backend at %s", url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _crawler_put(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    url = f"{CrawlerBackendURL}/api/v1/{path.lstrip('/')}"
    try:
        resp = requests.put(url, json=json_body, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to reach Crawler Backend at %s", url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _crawler_delete(path: str) -> dict[str, Any]:
    url = f"{CrawlerBackendURL}/api/v1/{path.lstrip('/')}"
    try:
        resp = requests.delete(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to reach Crawler Backend at %s", url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/tasks", response_model=CrawlTaskItem)
async def create_crawl_task(payload: CrawlTaskCreateRequest) -> CrawlTaskItem:
    """Create a new crawl task and dispatch it to the Crawler Backend."""

    body: dict[str, Any] = {
        "name": payload.name,
        "portal_url": payload.portal_url,
        "query": payload.query,
        "output_mode": payload.output_mode,
    }
    if payload.json_schema is not None:
        body["json_schema"] = payload.json_schema
    if payload.storage_db_type:
        body["storage_db_type"] = payload.storage_db_type

    data = _crawler_post("crawl/tasks", body)

    # The crawler backend returns the created task directly
    return CrawlTaskItem(**data)


@router.get("/tasks", response_model=CrawlTaskListResponse)
async def list_crawl_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> CrawlTaskListResponse:
    """List crawl tasks with optional pagination and status filter."""

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status

    data = _crawler_get("crawl/tasks", params=params)
    items = [CrawlTaskItem(**item) for item in data.get("items", [])]
    return CrawlTaskListResponse(
        items=items,
        total=data.get("total", 0),
        page=data.get("page", page),
        page_size=data.get("page_size", page_size),
    )


@router.get("/tasks/{task_id}", response_model=CrawlTaskDetail)
async def get_crawl_task_detail(task_id: str) -> CrawlTaskDetail:
    """Get a single crawl task with its run stats."""

    data = _crawler_get(f"crawl/tasks/{task_id}")
    task_data = data.get("task", data)
    run_stats = data.get("run_stats", {})

    return CrawlTaskDetail(
        task=CrawlTaskItem(**task_data),
        run_stats=run_stats,
    )


@router.get("/tasks/{task_id}/results", response_model=CrawlTaskResultsResponse)
async def get_crawl_task_results(task_id: str) -> CrawlTaskResultsResponse:
    """Get crawl results (pages + extracted content) for a completed task."""

    data = _crawler_get(f"crawl/tasks/{task_id}/results")

    results = data if isinstance(data, list) else data.get("items", data.get("results", []))
    items = [CrawlResultItem(**item) for item in results]
    return CrawlTaskResultsResponse(
        items=items,
        total=len(items),
    )


# ── Model config proxy endpoints ──────────────────────────────────────

@router.get("/model-configs")
async def list_model_configs():
    """List crawler model configs (crawler_agent + recursive_acquisition)."""
    return _crawler_get("model-configs")


@router.put("/model-configs/{target}")
async def upsert_model_config(target: str, payload: dict[str, Any]):
    """Update a crawler model config (crawler_agent or recursive_acquisition)."""
    return _crawler_put(f"model-configs/{target}", payload)


@router.post("/tasks/{task_id}/cancel")
async def cancel_crawl_task(task_id: str):
    """Cancel a running or pending crawl task."""
    return _crawler_post(f"crawl/tasks/{task_id}/cancel", {})


# ── Schedule proxy endpoints ─────────────────────────────────────────

@router.post("/schedules")
async def create_schedule(payload: dict[str, Any]):
    """Create a new crawl schedule."""
    return _crawler_post("schedules", payload)


@router.get("/schedules")
async def list_schedules():
    """List all crawl schedules."""
    return _crawler_get("schedules")


@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule(schedule_id: str):
    """Pause a crawl schedule."""
    return _crawler_post(f"schedules/{schedule_id}/pause", {})


@router.post("/schedules/{schedule_id}/resume")
async def resume_schedule(schedule_id: str):
    """Resume a crawl schedule."""
    return _crawler_post(f"schedules/{schedule_id}/resume", {})


@router.post("/schedules/{schedule_id}/run-once")
async def run_schedule_once(schedule_id: str):
    """Trigger a schedule to run immediately."""
    return _crawler_post(f"schedules/{schedule_id}/run-once", {})


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a crawl schedule."""
    return _crawler_delete(f"schedules/{schedule_id}")


@router.get("/tasks/{task_id}/download")
async def download_crawl_task_files(task_id: str):
    """Download crawl output files as a zip archive. Proxies the file stream from Crawler Backend."""

    url = f"{CrawlerBackendURL}/api/v1/crawl/tasks/{task_id}/download"

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to download crawl files from Crawler Backend")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    content_disposition = resp.headers.get(
        "Content-Disposition",
        f'attachment; filename="task_{task_id}_outputs.zip"',
    )

    return StreamingResponse(
        resp.iter_content(chunk_size=8192),
        status_code=resp.status_code,
        media_type=resp.headers.get("Content-Type", "application/zip"),
        headers={"Content-Disposition": content_disposition},
    )
