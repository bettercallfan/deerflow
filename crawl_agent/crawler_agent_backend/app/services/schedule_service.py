from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scheduler import build_trigger, scheduler
from app.db.session import SessionLocal
from app.models.enums import ScheduleStatus
from app.models.enums import ScheduleType
from app.models.schedule import CrawlSchedule
from app.services.model_config_service import ModelConfigService
from app.services.crawl_service import CrawlService, executor, run_task_blocking


def _job_id(schedule_id: str) -> str:
    return f"schedule:{schedule_id}"


def _to_interval_seconds(days: int, hours: int, minutes: int) -> int:
    return max(0, days) * 86400 + max(0, hours) * 3600 + max(0, minutes) * 60


async def run_schedule_job(schedule_id: str) -> None:
    db = SessionLocal()
    try:
        schedule = db.get(CrawlSchedule, schedule_id)
        if schedule is None or schedule.status != ScheduleStatus.ACTIVE:
            return

        svc = ScheduleService(db)
        prepared = svc.prepare_schedule_run(schedule_id)
        if prepared is None:
            return
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
    finally:
        db.close()


class ScheduleService:
    def __init__(self, db: Session):
        self.db = db

    def _ensure_payload_ready(self, payload: dict) -> None:
        output_mode = payload.get("output_mode", "json")
        ModelConfigService(self.db).ensure_output_mode_ready(output_mode)

    def prepare_schedule_run(self, schedule_id: str) -> tuple[CrawlSchedule, dict, object, object] | None:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return None

        self._ensure_payload_ready(schedule.payload)

        crawl_service = CrawlService(self.db)
        payload = dict(schedule.payload)
        payload.setdefault("name", f"{schedule.name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        payload["dedup_enabled"] = schedule.dedup_enabled
        payload["dedup_scope"] = schedule.dedup_scope

        task = crawl_service.create_task(payload=payload, source="schedule", schedule_id=schedule.id)
        run = crawl_service.create_run(task.id)

        schedule.last_run_at = datetime.utcnow()
        job = scheduler.get_job(_job_id(schedule.id))
        if job:
            schedule.next_run_at = getattr(job, "next_run_time", None)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule, payload, task, run

    def create_schedule(self, payload: dict) -> CrawlSchedule:
        if payload["schedule_type"] != ScheduleType.INTERVAL:
            raise ValueError("only interval schedule is supported")
        self._ensure_payload_ready(payload["payload"])

        interval_seconds = payload.get("interval_seconds")
        if payload["schedule_type"].value == "interval":
            interval_seconds = _to_interval_seconds(
                int(payload.get("interval_days", 0) or 0),
                int(payload.get("interval_hours", 0) or 0),
                int(payload.get("interval_minutes", 0) or 0),
            )
            if interval_seconds <= 0:
                raise ValueError("interval schedule requires a positive days/hours/minutes value")

        schedule = CrawlSchedule(
            name=payload["name"],
            schedule_type=payload["schedule_type"],
            cron_expr=payload.get("cron_expr"),
            interval_seconds=interval_seconds,
            timezone=payload.get("timezone", "Asia/Shanghai"),
            payload=payload["payload"],
            status=ScheduleStatus.ACTIVE if payload.get("enabled", True) else ScheduleStatus.PAUSED,
            change_detect_enabled=payload.get("change_detect_enabled", True),
            quick_hash_strategy=payload.get("quick_hash_strategy", "content_only"),
            force_full_crawl_every=payload.get("force_full_crawl_every", 10),
            dedup_enabled=payload.get("dedup_enabled", True),
            dedup_scope=payload.get("dedup_scope", "global"),
        )
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)

        self.register_job(schedule)
        # 创建后立即执行一次（仅 ACTIVE），后续继续按 interval 调度。
        if schedule.status == ScheduleStatus.ACTIVE:
            self.run_once(schedule.id)
        return schedule

    def register_job(self, schedule: CrawlSchedule) -> None:
        trigger = build_trigger(
            schedule_type=schedule.schedule_type.value,
            cron_expr=schedule.cron_expr,
            interval_seconds=schedule.interval_seconds,
            timezone=schedule.timezone,
        )
        scheduler.add_job(
            run_schedule_job,
            trigger=trigger,
            args=[schedule.id],
            id=_job_id(schedule.id),
            replace_existing=True,
        )
        if schedule.status == ScheduleStatus.PAUSED:
            scheduler.pause_job(_job_id(schedule.id))

        job = scheduler.get_job(_job_id(schedule.id))
        if job:
            schedule.next_run_at = getattr(job, "next_run_time", None)
            self.db.commit()

    def list_schedules(self) -> list[CrawlSchedule]:
        return self.db.scalars(select(CrawlSchedule).order_by(CrawlSchedule.created_at.desc())).all()

    def get_schedule(self, schedule_id: str) -> CrawlSchedule | None:
        return self.db.get(CrawlSchedule, schedule_id)

    def update_schedule(self, schedule_id: str, payload: dict) -> CrawlSchedule | None:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return None

        if "schedule_type" in payload and payload["schedule_type"] is not None:
            if payload["schedule_type"] != ScheduleType.INTERVAL:
                raise ValueError("only interval schedule is supported")

        if schedule.schedule_type.value == "interval":
            days = payload.get("interval_days")
            hours = payload.get("interval_hours")
            minutes = payload.get("interval_minutes")
            if days is not None or hours is not None or minutes is not None:
                interval_seconds = _to_interval_seconds(
                    int(days or 0),
                    int(hours or 0),
                    int(minutes or 0),
                )
                if interval_seconds <= 0:
                    raise ValueError("interval schedule requires a positive days/hours/minutes value")
                payload["interval_seconds"] = interval_seconds

        for key, value in payload.items():
            if value is not None and hasattr(schedule, key):
                setattr(schedule, key, value)

        if schedule.status == ScheduleStatus.ACTIVE:
            self._ensure_payload_ready(schedule.payload)

        self.db.commit()
        self.db.refresh(schedule)
        self.register_job(schedule)
        return schedule

    def pause(self, schedule_id: str) -> CrawlSchedule | None:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return None
        schedule.status = ScheduleStatus.PAUSED
        self.db.commit()
        if scheduler.get_job(_job_id(schedule_id)):
            scheduler.pause_job(_job_id(schedule_id))
        return schedule

    def resume(self, schedule_id: str) -> CrawlSchedule | None:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return None
        self._ensure_payload_ready(schedule.payload)
        schedule.status = ScheduleStatus.ACTIVE
        self.db.commit()
        if scheduler.get_job(_job_id(schedule_id)):
            scheduler.resume_job(_job_id(schedule_id))
        return schedule

    def run_once(self, schedule_id: str) -> bool:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return False
        self._ensure_payload_ready(schedule.payload)
        scheduler.add_job(run_schedule_job, args=[schedule_id])
        return True

    def delete(self, schedule_id: str) -> bool:
        schedule = self.db.get(CrawlSchedule, schedule_id)
        if schedule is None:
            return False

        job = scheduler.get_job(_job_id(schedule_id))
        if job:
            scheduler.remove_job(_job_id(schedule_id))

        self.db.delete(schedule)
        self.db.commit()
        return True
