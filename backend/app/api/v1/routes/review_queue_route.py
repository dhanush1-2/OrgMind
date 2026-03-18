"""GET/PATCH /api/v1/review-queue — manage flagged decisions."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.database import get_supabase
from app.core.logger import get_logger

log = get_logger("api.review_queue")
router = APIRouter(tags=["review_queue"])


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "escalate"
    note: str | None = None


@router.get("/review-queue")
async def list_review_queue(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    status: str | None = None,
):
    """List decisions flagged for human review."""
    log.info("api.review_queue.list", limit=limit, offset=offset, status=status)
    try:
        supabase = get_supabase()
        query = supabase.table("review_queue").select("*")
        if status:
            query = query.eq("status", status)
        result = (
            query
            .order("flagged_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return {"items": result.data, "count": len(result.data)}
    except Exception as e:
        log.error("api.review_queue.list_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/review-queue/{item_id}")
async def update_review_item(item_id: str, action: ReviewAction):
    """Approve, reject, or escalate a review queue item."""
    log.info("api.review_queue.update", id=item_id, action=action.action)
    if action.action not in ("approve", "reject", "escalate"):
        raise HTTPException(status_code=400, detail="action must be approve | reject | escalate")
    try:
        supabase = get_supabase()
        update_data = {"status": action.action}
        if action.note:
            update_data["note"] = action.note
        result = (
            supabase.table("review_queue")
            .update(update_data)
            .eq("id", item_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Review item not found")
        log.info("api.review_queue.updated", id=item_id, action=action.action)
        return {"id": item_id, "status": action.action}
    except HTTPException:
        raise
    except Exception as e:
        log.error("api.review_queue.update_failed", id=item_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/review-queue/stats")
async def review_queue_stats():
    """Counts by status for the review queue dashboard."""
    log.info("api.review_queue.stats")
    try:
        supabase = get_supabase()
        result = supabase.table("review_queue").select("status").execute()
        counts: dict[str, int] = {}
        for row in result.data:
            s = row.get("status", "pending")
            counts[s] = counts.get(s, 0) + 1
        return {"stats": counts, "total": len(result.data)}
    except Exception as e:
        log.error("api.review_queue.stats_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
