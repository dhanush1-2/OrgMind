"""
APScheduler — background jobs

Jobs:
  - ingestion_job     : runs full pipeline every 6 hours
  - health_check_job  : marks stale decisions every 24 hours
"""
from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger import get_logger

log = get_logger("scheduler")
_scheduler: AsyncIOScheduler | None = None


async def _ingestion_job() -> None:
    from app.pipeline.graph import run_pipeline
    log.info("scheduler.ingestion_job.start")
    try:
        summary = await run_pipeline()
        log.info("scheduler.ingestion_job.complete", **{k: v for k, v in summary.items() if k != "errors"})
    except Exception as e:
        log.error("scheduler.ingestion_job.failed", error=str(e), exc_info=True)


async def _health_check_job() -> None:
    from app.agents.health_monitor import HealthMonitorAgent
    log.info("scheduler.health_check_job.start")
    try:
        report = await HealthMonitorAgent().run_health_check()
        log.info(
            "scheduler.health_check_job.complete",
            total=report["total"],
            stale=report["stale"],
            newly_stale=report["newly_stale"],
        )
    except Exception as e:
        log.error("scheduler.health_check_job.failed", error=str(e), exc_info=True)


def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(
        _ingestion_job,
        trigger=IntervalTrigger(hours=6),
        id="ingestion",
        name="Full ingestion pipeline",
        replace_existing=True,
    )
    _scheduler.add_job(
        _health_check_job,
        trigger=IntervalTrigger(hours=24),
        id="health_check",
        name="Health monitor",
        replace_existing=True,
    )

    _scheduler.start()
    log.info("scheduler.started", jobs=["ingestion (6h)", "health_check (24h)"])


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler.stopped")
