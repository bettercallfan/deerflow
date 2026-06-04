from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings

settings = get_settings()

scheduler = AsyncIOScheduler(timezone=settings.timezone)


def build_trigger(schedule_type: str, cron_expr: str | None, interval_seconds: int | None, timezone: str):
    if schedule_type == "cron":
        if not cron_expr:
            raise ValueError("cron_expr is required for cron schedule")
        return CronTrigger.from_crontab(cron_expr, timezone=timezone)

    if not interval_seconds:
        raise ValueError("interval_seconds is required for interval schedule")
    return IntervalTrigger(seconds=interval_seconds, timezone=timezone)
