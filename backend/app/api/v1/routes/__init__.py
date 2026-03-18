"""Route modules for OrgMind API v1."""
from app.api.v1.routes import (
    health,
    ingest,
    query,
    decisions,
    graph,
    conflicts,
    staleness,
    onboarding,
    review_queue_route,
    integrations,
)

__all__ = [
    "health",
    "ingest",
    "query",
    "decisions",
    "graph",
    "conflicts",
    "staleness",
    "onboarding",
    "review_queue_route",
    "integrations",
]
