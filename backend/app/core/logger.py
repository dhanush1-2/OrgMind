"""
Structured logging — structlog over stdlib logging.

Usage:
    from app.core.logger import get_logger
    log = get_logger(__name__)
    log.info("agent.started", agent="extraction", doc_id="abc123")
    log.error("db.write_failed", db="neo4j", error=str(e))
"""
import logging
import sys
from pathlib import Path

import structlog

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"


def setup_logging() -> None:
    """Call once at application startup (main.py)."""
    from app.core.config import get_settings
    settings = get_settings()
    is_dev = settings.environment == "development"
    level = logging.DEBUG if is_dev else logging.INFO

    # ── stdlib root logger ────────────────────────────────────────────────────
    _LOG_DIR.mkdir(exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    file_handler = logging.FileHandler(_LOG_DIR / "orgmind.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    handlers.append(file_handler)

    logging.basicConfig(format="%(message)s", level=level, handlers=handlers, force=True)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "neo4j", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── structlog ─────────────────────────────────────────────────────────────
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_dev:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),   # uses stdlib — has .name
        cache_logger_on_first_use=True,
    )

    log = get_logger("core.logging")
    log.info(
        "logging.configured",
        environment=settings.environment,
        log_file=str(_LOG_DIR / "orgmind.log"),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
