"""Health check routes — used by Render's health probe and the frontend."""
from fastapi import APIRouter
from app.core.logger import get_logger

log = get_logger("api.health")
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    log.info("health.ping")
    return {"status": "ok", "service": "orgmind-backend"}


@router.get("/health/detailed")
async def health_detailed() -> dict:
    """Checks each DB client is reachable."""
    from app.core.database import get_neo4j, get_redis, get_supabase

    checks: dict[str, str] = {}

    # Neo4j
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            await session.run("RETURN 1")
        checks["neo4j"] = "ok"
        log.info("health.neo4j", status="ok")
    except Exception as e:
        checks["neo4j"] = f"error: {e}"
        log.error("health.neo4j", status="error", error=str(e))

    # Redis
    try:
        redis = get_redis()
        redis.ping()
        checks["redis"] = "ok"
        log.info("health.redis", status="ok")
    except Exception as e:
        checks["redis"] = f"error: {e}"
        log.error("health.redis", status="error", error=str(e))

    # Supabase — just verify client exists
    try:
        get_supabase()
        checks["supabase"] = "ok"
        log.info("health.supabase", status="ok")
    except Exception as e:
        checks["supabase"] = f"error: {e}"
        log.error("health.supabase", status="error", error=str(e))

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    log.info("health.detailed", overall=overall, checks=checks)
    return {"status": overall, "checks": checks}
