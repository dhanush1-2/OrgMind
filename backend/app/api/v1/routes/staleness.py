"""GET /api/v1/staleness — stale decision dashboard data."""
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_neo4j
from app.core.logger import get_logger

log = get_logger("api.staleness")
router = APIRouter(tags=["staleness"])


@router.get("/staleness")
async def get_staleness_report(limit: int = Query(50, le=200)):
    """Return stale decisions and staleness metrics."""
    log.info("api.staleness.request")
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            # Summary metrics
            metrics_result = await session.run(
                """
                MATCH (d:Decision)
                RETURN
                    count(d) AS total,
                    sum(CASE WHEN d.stale = true THEN 1 ELSE 0 END) AS stale,
                    sum(CASE WHEN d.stale = false OR d.stale IS NULL THEN 1 ELSE 0 END) AS active,
                    avg(d.confidence) AS avg_confidence
                """
            )
            metrics_record = await metrics_result.single()
            metrics = dict(metrics_record) if metrics_record else {}

            # Stale decisions list
            stale_result = await session.run(
                """
                MATCH (d:Decision)
                WHERE d.stale = true
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                RETURN d.id AS id, d.title AS title, d.date AS date,
                       d.confidence AS confidence, d.source_url AS source_url,
                       collect(DISTINCT e.name) AS entities
                ORDER BY d.date ASC
                LIMIT $limit
                """,
                limit=limit,
            )
            stale_decisions = await stale_result.data()

        log.info("api.staleness.complete", total=metrics.get("total"), stale=metrics.get("stale"))
        return {
            "metrics": {
                "total": metrics.get("total", 0),
                "stale": metrics.get("stale", 0),
                "active": metrics.get("active", 0),
                "avg_confidence": round(metrics.get("avg_confidence") or 0, 3),
                "stale_pct": round(
                    (metrics.get("stale", 0) / metrics.get("total", 1)) * 100, 1
                ) if metrics.get("total") else 0,
            },
            "stale_decisions": stale_decisions,
        }
    except Exception as e:
        log.error("api.staleness.failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/staleness/run")
async def run_health_check():
    """Trigger health monitor agent to refresh staleness flags."""
    log.info("api.staleness.run_requested")
    try:
        from app.agents.health_monitor import HealthMonitorAgent
        report = await HealthMonitorAgent().run_health_check()
        log.info("api.staleness.run_complete", **{k: v for k, v in report.items()})
        return report
    except Exception as e:
        log.error("api.staleness.run_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
