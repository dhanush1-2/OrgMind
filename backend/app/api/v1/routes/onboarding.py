"""POST /api/v1/onboarding — role-based decision briefing."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.logger import get_logger

log = get_logger("api.onboarding")
router = APIRouter(tags=["onboarding"])


class OnboardingRequest(BaseModel):
    role: str
    name: str | None = None
    focus_areas: list[str] = []


@router.post("/onboarding")
async def get_onboarding_briefing(req: OnboardingRequest):
    """
    Generate a role-based onboarding briefing using the OnboardingAgent.
    Returns a structured briefing with relevant decisions and context.
    """
    log.info("api.onboarding.request", role=req.role, name=req.name)
    try:
        from app.agents.onboarding import OnboardingBriefingAgent
        agent = OnboardingBriefingAgent()
        briefing = await agent.generate_briefing(role=req.role)
        log.info("api.onboarding.complete", role=req.role, sections=len(briefing.get("sections", [])))
        return briefing
    except Exception as e:
        log.error("api.onboarding.failed", role=req.role, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
