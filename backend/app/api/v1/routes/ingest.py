"""POST /api/v1/ingest — trigger the ingestion pipeline."""
from fastapi import APIRouter, BackgroundTasks
from app.core.logger import get_logger

log = get_logger("api.ingest")
router = APIRouter(tags=["ingest"])


@router.post("/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    """Trigger the full ingestion pipeline asynchronously."""
    from app.pipeline.graph import run_pipeline
    log.info("api.ingest.triggered")
    background_tasks.add_task(_run_pipeline_task)
    return {"status": "started", "message": "Ingestion pipeline triggered in background"}


async def _run_pipeline_task():
    from app.pipeline.graph import run_pipeline
    try:
        summary = await run_pipeline()
        log.info("api.ingest.background_complete", **{k: v for k, v in summary.items() if k != "errors"})
    except Exception as e:
        log.error("api.ingest.background_failed", error=str(e), exc_info=True)


@router.post("/ingest/sync")
async def trigger_ingest_sync():
    """Run pipeline synchronously and return full summary (for dev/testing)."""
    from app.pipeline.graph import run_pipeline
    log.info("api.ingest.sync_triggered")
    summary = await run_pipeline()
    return summary
