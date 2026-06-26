"""Dataset viewer router — proxies dataset queries to the Crawler Backend."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-center/datasets", tags=["datasets"])

CRAWLER_BACKEND_URL = os.getenv("CRAWLER_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _datasets_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{CRAWLER_BACKEND_URL}/api/v1/{path.lstrip('/')}"
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 500
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("Failed to reach Crawler Backend at %s", url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/records")
async def list_dataset_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    result_type: str | None = Query(None),
):
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
    }
    if keyword:
        params["keyword"] = keyword
    if result_type and result_type != "all":
        params["result_type"] = result_type

    return _datasets_get("datasets/records", params=params)


@router.get("/records/{record_id}")
async def get_dataset_record(record_id: int):
    return _datasets_get(f"datasets/records/{record_id}")


@router.get("/stats")
async def get_dataset_stats():
    return _datasets_get("datasets/stats")
