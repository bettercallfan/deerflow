from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import APIMessage
from app.schemas.schedule import ScheduleCreate, ScheduleListResponse, ScheduleRead, ScheduleUpdate
from app.services.schedule_service import ScheduleService
from app.services.crawl_service import executor, run_task_blocking

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _split_interval(seconds: int | None) -> tuple[int, int, int]:
    total = int(seconds or 0)
    days = total // 86400
    rem = total % 86400
    hours = rem // 3600
    minutes = (rem % 3600) // 60
    return days, hours, minutes


def _to_schedule_read(row) -> ScheduleRead:
    days, hours, minutes = _split_interval(getattr(row, "interval_seconds", None))
    return ScheduleRead(
        id=row.id,
        name=row.name,
        schedule_type=row.schedule_type,
        cron_expr=row.cron_expr,
        interval_seconds=row.interval_seconds,
        interval_days=days,
        interval_hours=hours,
        interval_minutes=minutes,
        timezone=row.timezone,
        payload=row.payload,
        status=row.status,
        change_detect_enabled=row.change_detect_enabled,
        quick_hash_strategy=row.quick_hash_strategy,
        force_full_crawl_every=row.force_full_crawl_every,
        dedup_enabled=row.dedup_enabled,
        dedup_scope=row.dedup_scope,
        last_run_at=row.last_run_at,
        next_run_at=row.next_run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=ScheduleRead)
def create_schedule(payload: ScheduleCreate, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    try:
        row = svc.create_schedule(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_schedule_read(row)


@router.get("", response_model=ScheduleListResponse)
def list_schedules(db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    items = svc.list_schedules()
    return ScheduleListResponse(items=[_to_schedule_read(item) for item in items], total=len(items))


@router.get("/{schedule_id}", response_model=ScheduleRead)
def get_schedule(schedule_id: str, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    row = svc.get_schedule(schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return _to_schedule_read(row)


@router.put("/{schedule_id}", response_model=ScheduleRead)
def update_schedule(schedule_id: str, payload: ScheduleUpdate, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    try:
        row = svc.update_schedule(schedule_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return _to_schedule_read(row)


@router.post("/{schedule_id}/pause", response_model=ScheduleRead)
def pause_schedule(schedule_id: str, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    row = svc.pause(schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return _to_schedule_read(row)


@router.post("/{schedule_id}/resume", response_model=ScheduleRead)
def resume_schedule(schedule_id: str, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    try:
        row = svc.resume(schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return _to_schedule_read(row)


@router.post("/{schedule_id}/run-once", response_model=APIMessage)
async def run_once(schedule_id: str, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    try:
        prepared = svc.prepare_schedule_run(schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if prepared is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    schedule, payload, task, run = prepared

    async def _execute_in_background_thread():
        await asyncio.to_thread(
            run_task_blocking,
            task.id,
            run.id,
            {
                "enabled": schedule.change_detect_enabled,
                "strategy": schedule.quick_hash_strategy,
            },
            payload.get("storage_db_type"),
        )

    executor.submit(key=f"task:{task.id}", coro=_execute_in_background_thread())
    return APIMessage(message="schedule triggered")


@router.delete("/{schedule_id}", response_model=APIMessage)
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)):
    svc = ScheduleService(db)
    ok = svc.delete(schedule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="schedule not found")
    return APIMessage(message="schedule deleted")
