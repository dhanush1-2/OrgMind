"""Unit tests — Agent 11: Onboarding Briefing Agent"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.onboarding.agent import OnboardingBriefingAgent


def _make_agent():
    with patch("app.agents.onboarding.agent.ChatGroq"), \
         patch("app.agents.onboarding.agent.get_neo4j"):
        return OnboardingBriefingAgent()


def _neo4j_with(records: list[dict]):
    session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.data = AsyncMock(return_value=records)
    session.run = AsyncMock(return_value=result_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _llm_resp(content: str):
    m = MagicMock()
    m.content = content
    return m


_SAMPLE_RECORDS = [
    {
        "id": "d1", "decision": "We use PostgreSQL.", "rationale": "ACID compliance.",
        "date": "2025-01-01", "stale": False, "source_url": "https://example.com/adr-1",
        "entities": ["PostgreSQL"], "conflicts": [],
    },
    {
        "id": "d2", "decision": "We use Kubernetes.", "rationale": "Container orchestration.",
        "date": "2025-02-01", "stale": True, "source_url": "https://example.com/adr-2",
        "entities": ["Kubernetes"], "conflicts": ["Use Docker Swarm"],
    },
]


@pytest.mark.asyncio
async def test_briefing_returned_for_role():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("Welcome to the platform team! ..."))

    with patch("app.agents.onboarding.agent.get_neo4j", return_value=_neo4j_with(_SAMPLE_RECORDS)):
        result = await agent.generate_briefing("backend engineer")

    assert "briefing" in result
    assert result["decisions_count"] == 2
    assert "Welcome" in result["briefing"]


@pytest.mark.asyncio
async def test_stale_count_correct():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("Briefing content"))

    with patch("app.agents.onboarding.agent.get_neo4j", return_value=_neo4j_with(_SAMPLE_RECORDS)):
        result = await agent.generate_briefing("backend engineer")

    assert result["stale_count"] == 1


@pytest.mark.asyncio
async def test_conflicts_count_correct():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("Briefing content"))

    with patch("app.agents.onboarding.agent.get_neo4j", return_value=_neo4j_with(_SAMPLE_RECORDS)):
        result = await agent.generate_briefing("platform team")

    assert result["conflicts_count"] == 1


@pytest.mark.asyncio
async def test_fallback_to_recent_when_no_role_match():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("Recent decisions briefing"))

    # Role query returns nothing; recent query returns records
    call_count = 0
    async def side_effect_data():
        nonlocal call_count
        call_count += 1
        return [] if call_count == 1 else _SAMPLE_RECORDS

    session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.data = side_effect_data
    session.run = AsyncMock(return_value=result_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    with patch("app.agents.onboarding.agent.get_neo4j", return_value=driver):
        result = await agent.generate_briefing("xyzunknownrole")

    assert result["briefing"] == "Recent decisions briefing"


@pytest.mark.asyncio
async def test_sources_included_in_result():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("Briefing"))

    with patch("app.agents.onboarding.agent.get_neo4j", return_value=_neo4j_with(_SAMPLE_RECORDS)):
        result = await agent.generate_briefing("engineer")

    assert len(result["sources"]) == 2
    urls = [s["url"] for s in result["sources"]]
    assert "https://example.com/adr-1" in urls
