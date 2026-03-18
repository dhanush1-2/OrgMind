"""
Pytest configuration — runs before all tests.
Configures structlog with a simple no-op renderer so agents
can call get_logger() freely without hitting files or stdout.
"""
import logging
import pytest
import structlog


def pytest_configure(config):
    """Configure structlog once for the entire test session."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
