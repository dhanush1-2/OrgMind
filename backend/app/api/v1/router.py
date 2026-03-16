"""Top-level v1 API router — import all route modules here."""
from fastapi import APIRouter
from app.api.v1.routes import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
