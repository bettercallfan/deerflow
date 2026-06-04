from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import TaskStatus
from app.models.task import CrawlPage, CrawlResult, CrawlRun, CrawlTask
from app.schemas.common import APIMessage
from app.schemas.task import (
    CrawlTaskCreate,
    CrawlTaskDetail,
    CrawlTaskFingerprint,
    CrawlTaskListResponse,
    CrawlTaskRead,
    CrawlTaskResultItem,
)
from app.services.model_config_service import ModelConfigService
from app.services.crawl_service import CrawlService, executor, run_task_blocking

router = APIRouter(prefix="/crawl/tasks", tags=["crawl-tasks"])


@router.post("", response_model=CrawlTaskRead)
async def create_task(payload: CrawlTaskCreate, db: Session = Depends(get_db)):
    model_config_service = ModelConfigService(db)
    try:
        model_config_service.ensure_output_mode_ready(payload.output_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = CrawlService(db)
    payload_dict = payload.model_dump()
    task = service.create_task(payload_dict, source="manual")
    run = service.create_run(task.id)

    async def _execute_in_background_thread():
        storage_db_type = payload_dict.get("storage_db_type")
        storage_db_type_value = getattr(storage_db_type, "value", storage_db_type)
        await asyncio.to_thread(
            run_task_blocking,
            task.id,
            run.id,
            None,
            storage_db_type_value,
        )

    executor.submit(key=f"task:{task.id}", coro=_execute_in_background_thread())
    return task


@router.get("", response_model=CrawlTaskListResponse)
def list_tasks(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = select(CrawlTask)
    if status:
        query = query.where(CrawlTask.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(CrawlTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size),
    ).all()

    return CrawlTaskListResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=CrawlTaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    run = db.scalar(
        select(CrawlRun).where(CrawlRun.task_id == task_id).order_by(CrawlRun.started_at.desc()).limit(1),
    )
    run_stats = {
        "status": run.status if run else None,
        "site_changed": run.site_changed if run else None,
        "skip_reason": run.skip_reason if run else None,
        "new_pages_count": run.new_pages_count if run else 0,
        "duplicate_pages_count": run.duplicate_pages_count if run else 0,
        "unchanged_pages_count": run.unchanged_pages_count if run else 0,
    }
    return CrawlTaskDetail(task=task, run_stats=run_stats)


@router.get("/{task_id}/results", response_model=list[CrawlTaskResultItem])
def get_task_results(task_id: str, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    pages = db.scalars(select(CrawlPage).where(CrawlPage.task_id == task_id).order_by(CrawlPage.created_at.asc())).all()
    items = []
    for page in pages:
        result = db.scalar(select(CrawlResult).where(CrawlResult.page_id == page.id).limit(1))
        items.append(
            CrawlTaskResultItem(
                page_id=page.id,
                url=page.url,
                title=page.title,
                is_duplicate=page.is_duplicate,
                duplicate_reason=page.duplicate_reason,
                raw_html_hash=page.raw_html_hash,
                normalized_content_hash=page.normalized_content_hash,
                result_type=result.result_type if result else None,
                result_json=result.result_json if result else None,
                result_markdown=result.result_markdown if result else None,
                result_markdown_ocr=result.result_markdown_ocr if result else None,
            ),
        )
    return items


@router.get("/{task_id}/fingerprints", response_model=list[CrawlTaskFingerprint])
def get_task_fingerprints(task_id: str, db: Session = Depends(get_db)):
    pages = db.scalars(select(CrawlPage).where(CrawlPage.task_id == task_id).order_by(CrawlPage.created_at.asc())).all()
    return [
        CrawlTaskFingerprint(
            page_id=p.id,
            url=p.url,
            raw_html_hash=p.raw_html_hash,
            normalized_content_hash=p.normalized_content_hash,
            is_duplicate=p.is_duplicate,
            duplicate_reason=p.duplicate_reason,
            created_at=p.created_at,
        )
        for p in pages
    ]


@router.post("/{task_id}/cancel", response_model=APIMessage)
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task.status = TaskStatus.CANCELED
    db.commit()
    return APIMessage(message="task marked as canceled")
