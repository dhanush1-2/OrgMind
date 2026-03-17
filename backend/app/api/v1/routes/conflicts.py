"""GET /api/v1/conflicts — list all CONFLICTS_WITH relationships."""
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_neo4j
from app.core.logger import get_logger

log = get_logger("api.conflicts")
router = APIRouter(tags=["conflicts"])


@router.get("/conflicts")
async def list_conflicts(limit: int = Query(100, le=500)):
    """Return all conflict pairs detected between decisions."""
    log.info("api.conflicts.request", limit=limit)
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Decision)-[r:CONFLICTS_WITH]->(b:Decision)
                RETURN a.id AS source_id, a.title AS source_title,
                       b.id AS target_id, b.title AS target_title,
                       r.reason AS reason, r.severity AS severity,
                       a.date AS source_date, b.date AS target_date
                ORDER BY r.severity DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            records = await result.data()
        log.info("api.conflicts.complete", count=len(records))
        return {"conflicts": records, "count": len(records)}
    except Exception as e:
        log.error("api.conflicts.failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conflicts/{decision_id}")
async def get_decision_conflicts(decision_id: str):
    """Return all conflicts for a specific decision."""
    log.info("api.conflicts.get", id=decision_id)
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Decision {id: $id})-[r:CONFLICTS_WITH]->(other:Decision)
                RETURN other.id AS conflicting_id, other.title AS conflicting_title,
                       r.reason AS reason, r.severity AS severity, 'outgoing' AS direction
                UNION
                MATCH (other:Decision)-[r:CONFLICTS_WITH]->(d:Decision {id: $id})
                RETURN other.id AS conflicting_id, other.title AS conflicting_title,
                       r.reason AS reason, r.severity AS severity, 'incoming' AS direction
                """,
                id=decision_id,
            )
            records = await result.data()
        return {"decision_id": decision_id, "conflicts": records, "count": len(records)}
    except Exception as e:
        log.error("api.conflicts.get_failed", id=decision_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
