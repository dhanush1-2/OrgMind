"""GET /api/v1/integrations — connection status for all data sources."""
from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase, get_neo4j, get_redis, get_chroma
from app.core.logger import get_logger

log = get_logger("api.integrations")
router = APIRouter(tags=["integrations"])


async def _check_supabase() -> dict:
    try:
        sb = get_supabase()
        result = sb.table("decisions").select("id").limit(1).execute()
        return {"status": "connected", "decisions_count": len(result.data)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_neo4j() -> dict:
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run("MATCH (d:Decision) RETURN count(d) AS n")
            record = await result.single()
            count = record["n"] if record else 0
        return {"status": "connected", "decision_nodes": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_redis() -> dict:
    try:
        redis = get_redis()
        redis.ping()  # Upstash REST client is synchronous
        return {"status": "connected"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_chroma() -> dict:
    try:
        from app.core.database import _chroma
        if _chroma is None:
            return {"status": "unavailable", "reason": "ChromaDB not started (Docker required)"}
        collections = await _chroma.list_collections()
        return {"status": "connected", "collections": len(collections)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/integrations")
async def get_integration_status():
    """Return live connection status for all external services."""
    log.info("api.integrations.check")
    try:
        import asyncio
        supabase_status, neo4j_status, redis_status, chroma_status = await asyncio.gather(
            _check_supabase(),
            _check_neo4j(),
            _check_redis(),
            _check_chroma(),
            return_exceptions=False,
        )
        result = {
            "supabase": supabase_status,
            "neo4j": neo4j_status,
            "redis": redis_status,
            "chromadb": chroma_status,
        }
        all_ok = all(v.get("status") in ("connected", "unavailable") for v in result.values())
        log.info("api.integrations.complete", all_ok=all_ok)
        return {"integrations": result, "all_healthy": all_ok}
    except Exception as e:
        log.error("api.integrations.failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
