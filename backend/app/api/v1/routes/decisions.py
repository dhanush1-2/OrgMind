"""GET /api/v1/decisions — list and retrieve decisions."""
from fastapi import APIRouter, Query, HTTPException
from app.core.logger import get_logger
from app.core.database import get_supabase, get_neo4j

log = get_logger("api.decisions")
router = APIRouter(tags=["decisions"])


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    source_type: str | None = None,
    stale: bool | None = None,
    review_status: str | None = None,
):
    log.info("api.decisions.list", limit=limit, offset=offset)
    try:
        supabase = get_supabase()
        query = supabase.table("decisions").select("*")
        if source_type:
            query = query.eq("source_type", source_type)
        if stale is not None:
            # stale stored in Neo4j — approximate via Supabase for now
            pass
        if review_status:
            query = query.eq("review_status", review_status)
        result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return {"decisions": result.data, "count": len(result.data)}
    except Exception as e:
        log.error("api.decisions.list_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str):
    log.info("api.decisions.get", id=decision_id)
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Decision {id: $id})
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                OPTIONAL MATCH (d)-[:MADE_BY]->(p:Person)
                OPTIONAL MATCH (d)-[:SOURCED_FROM]->(s:Source)
                OPTIONAL MATCH (d)-[:CONFLICTS_WITH]->(conflict:Decision)
                RETURN d.id AS id, d.title AS decision, d.rationale AS rationale,
                       d.date AS date, d.stale AS stale, d.confidence AS confidence,
                       d.source_url AS source_url,
                       collect(DISTINCT {name: e.name, type: e.type}) AS entities,
                       collect(DISTINCT p.name) AS authors,
                       collect(DISTINCT {id: conflict.id, title: conflict.title}) AS conflicts
                """,
                id=decision_id,
            )
            record = await result.single()
            if not record:
                raise HTTPException(status_code=404, detail="Decision not found")
            return dict(record)
    except HTTPException:
        raise
    except Exception as e:
        log.error("api.decisions.get_failed", id=decision_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline")
async def get_timeline(limit: int = Query(100, le=500)):
    """All decisions ordered by date for the timeline view."""
    log.info("api.timeline.request", limit=limit)
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Decision)
                WHERE d.date IS NOT NULL AND d.date <> ''
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                RETURN d.id AS id, d.title AS decision, d.date AS date,
                       d.stale AS stale, d.confidence AS confidence,
                       d.source_url AS source_url,
                       collect(DISTINCT e.name) AS entities
                ORDER BY d.date DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            records = await result.data()
            return {"decisions": records, "count": len(records)}
    except Exception as e:
        log.error("api.timeline.failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
