"""
OrgMind — FastAPI application entry point.

Startup order:
  1. Logging configured
  2. All DB clients initialised (Supabase, Neo4j, Redis, ChromaDB)
  3. Neo4j schema (constraints + indexes) applied
  4. Routers mounted

Shutdown order:
  1. DB connections gracefully closed
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.logger import setup_logging, get_logger
from app.core.config import get_settings

# Logging must be configured before any other imports that use get_logger()
setup_logging()
log = get_logger("main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    log.info("app.startup", environment=settings.environment, demo_mode=settings.demo_mode)

    from app.core.database import init_all_clients
    from app.core.neo4j_schema import apply_schema
    from app.core.scheduler import start_scheduler, stop_scheduler

    await init_all_clients()
    await apply_schema()
    start_scheduler()

    log.info("app.ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("app.shutdown")
    stop_scheduler()
    from app.core.database import close_all_clients
    await close_all_clients()
    log.info("app.stopped")


app = FastAPI(
    title="OrgMind API",
    description="AI-powered organisational memory — 12-agent LangGraph backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [settings.api_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response logging middleware ─────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_log = get_logger("http")
    request_log.info(
        "request.start",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else "unknown",
    )
    try:
        response = await call_next(request)
        request_log.info(
            "request.complete",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        return response
    except Exception as e:
        request_log.error(
            "request.failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.v1.router import api_router  # noqa: E402
app.include_router(api_router)


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "OrgMind API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
