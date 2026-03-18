"""
Database client initialisation.

All clients are created once and stored as module-level singletons.
Call `init_all_clients()` during FastAPI lifespan startup and
`close_all_clients()` during shutdown.

Every operation logs the step so errors are fully traceable.
"""
from __future__ import annotations

from typing import Optional, Any

try:
    import chromadb
    _CHROMA_AVAILABLE = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    _CHROMA_AVAILABLE = False

from neo4j import AsyncGraphDatabase, AsyncDriver
from supabase import create_client, Client as SupabaseClient
from upstash_redis import Redis

from app.core.config import get_settings
from app.core.logger import get_logger

log = get_logger("core.database")
settings = get_settings()

# ── Singletons ────────────────────────────────────────────────────────────────
_supabase: Optional[SupabaseClient] = None
_neo4j: Optional[AsyncDriver] = None
_chroma: Optional[Any] = None
_redis: Optional[Redis] = None


# ─────────────────────────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────────────────────────
def get_supabase() -> SupabaseClient:
    if _supabase is None:
        raise RuntimeError("Supabase client not initialised. Call init_all_clients() first.")
    return _supabase


def _init_supabase() -> SupabaseClient:
    log.info("supabase.connecting", url=settings.supabase_url)
    try:
        client = create_client(settings.supabase_url, settings.supabase_key)
        log.info("supabase.connected")
        return client
    except Exception as e:
        log.error("supabase.connect_failed", error=str(e), exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j
# ─────────────────────────────────────────────────────────────────────────────
def get_neo4j() -> AsyncDriver:
    if _neo4j is None:
        raise RuntimeError("Neo4j driver not initialised. Call init_all_clients() first.")
    return _neo4j


def _init_neo4j() -> AsyncDriver:
    log.info("neo4j.connecting", uri=settings.neo4j_uri, user=settings.neo4j_user)
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=3600,
        )
        log.info("neo4j.driver_created")
        return driver
    except Exception as e:
        log.error("neo4j.connect_failed", error=str(e), exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# ChromaDB (optional — local Docker only)
# ─────────────────────────────────────────────────────────────────────────────
def get_chroma() -> Any:
    return _chroma  # may be None if not installed / not running


async def _init_chroma() -> Any:
    if not _CHROMA_AVAILABLE:
        log.warning("chroma.skipped", reason="chromadb not installed (production mode)")
        return None
    log.info(
        "chroma.connecting",
        host=settings.chroma_host,
        port=settings.chroma_port,
    )
    try:
        client = await chromadb.AsyncHttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        log.info("chroma.connected")
        return client
    except Exception as e:
        log.error("chroma.connect_failed", error=str(e), exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Upstash Redis
# ─────────────────────────────────────────────────────────────────────────────
def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis client not initialised. Call init_all_clients() first.")
    return _redis


def _init_redis() -> Redis:
    log.info("redis.connecting", url=settings.upstash_redis_rest_url)
    try:
        client = Redis(
            url=settings.upstash_redis_rest_url,
            token=settings.upstash_redis_rest_token,
        )
        log.info("redis.connected")
        return client
    except Exception as e:
        log.error("redis.connect_failed", error=str(e), exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────
async def init_all_clients() -> None:
    """Initialise every DB client. Called during FastAPI lifespan startup."""
    global _supabase, _neo4j, _chroma, _redis
    log.info("database.init_start")

    _supabase = _init_supabase()
    _neo4j = _init_neo4j()
    _redis = _init_redis()

    # ChromaDB — only connect when running locally with Docker
    try:
        _chroma = await _init_chroma()
    except Exception:
        log.warning("chroma.skipped", reason="Could not reach ChromaDB — start Docker Compose")

    # Verify Neo4j connectivity
    await _verify_neo4j()

    log.info("database.init_complete")


async def _verify_neo4j() -> None:
    log.info("neo4j.verifying")
    try:
        async with _neo4j.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            assert record["ok"] == 1
        log.info("neo4j.verified")
    except Exception as e:
        log.error("neo4j.verify_failed", error=str(e), exc_info=True)
        raise


async def close_all_clients() -> None:
    """Gracefully close all connections. Called during FastAPI lifespan shutdown."""
    log.info("database.shutdown_start")
    if _neo4j:
        await _neo4j.close()
        log.info("neo4j.closed")
    log.info("database.shutdown_complete")
