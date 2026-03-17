"""Top-level v1 API router — import all route modules here."""
from fastapi import APIRouter
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

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(ingest.router)
api_router.include_router(query.router)
api_router.include_router(decisions.router)
api_router.include_router(graph.router)
api_router.include_router(conflicts.router)
api_router.include_router(staleness.router)
api_router.include_router(onboarding.router)
api_router.include_router(review_queue_route.router)
api_router.include_router(integrations.router)
