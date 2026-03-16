"""
Structured logging setup using structlog + Rich.

Every log record is a JSON object (in production) or a coloured table (dev).
Usage anywhere in the codebase:
    from app.core.logger import get_logger
    log = get_logger(__name__)
    log.info("agent.started", agent="extraction", doc_id="abc123")
    log.error("db.write_failed", db="neo4j", error=str(e), exc_info=True)
"""
import logging
import sys
from pathlib import Path

import structlog
from structlog.types import Processor

from app.core.config import get_settings

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_SETTINGS = get_settings()
_IS_DEV = _SETTINGS.environment == "development"


def _configure_stdlib_logging() -> None:
    """Route stdlib logging (uvicorn, sqlalchemy, neo4j…) through structlog."""
    level = logging.DEBUG if _IS_DEV else logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    # Always write to a rolling file so errors are traceable after the fact
    file_handler = logging.FileHandler(_LOG_DIR / "orgmind.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )
    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "neo4j"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _build_processors(dev: bool) -> list[Processor]:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]
    if dev:
        shared.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        shared.append(structlog.processors.JSONRenderer())
    return shared


def setup_logging() -> None:
    """Call once at application startup."""
    _configure_stdlib_logging()
    structlog.configure(
        processors=_build_processors(_IS_DEV),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if _IS_DEV else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    log = get_logger("core.logging")
    log.info(
        "logging.configured",
        environment=_SETTINGS.environment,
        log_file=str(_LOG_DIR / "orgmind.log"),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound logger tagged with the module name."""
    return structlog.get_logger(name)
