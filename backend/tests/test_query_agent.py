"""Unit tests — Agent 10: Query Agent"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.query_agent.agent import QueryAgent


def _make_agent():
    with patch("app.agents.query_agent.agent.ChatGroq"), \
         patch("app.agents.query_agent.agent.get_neo4j"):
        return QueryAgent()


def _neo4j_with_results(records: list[dict]):
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


_SAMPLE_DECISION = {
    "id": "d1",
    "decision": "We will use PostgreSQL as our primary database.",
    "rationale": "ACID compliance and strong ecosystem support.",
    "date": "2025-01-15",
    "confidence": 0.92,
    "stale": False,
    "source_url": "https://example.com/adr-001",
    "entities": ["PostgreSQL"],
    "authors": ["alice"],
}


@pytest.mark.asyncio
async def test_query_returns_answer_and_citations():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(
        "We use PostgreSQL as the primary database. See ADR-001."
    ))
    with patch("app.agents.query_agent.agent.get_neo4j",
               return_value=_neo4j_with_results([_SAMPLE_DECISION])):
        result = await agent.query("What database do we use?")

    assert "answer" in result
    assert len(result["citations"]) == 1
    assert result["decisions_found"] == 1
    assert "PostgreSQL" in result["citations"][0]["decision"]


@pytest.mark.asyncio
async def test_query_no_results_returns_fallback():
    agent = _make_agent()
    with patch("app.agents.query_agent.agent.get_neo4j",
               return_value=_neo4j_with_results([])):
        result = await agent.query("What is our quantum computing strategy?")

    assert "couldn't find" in result["answer"].lower()
    assert result["citations"] == []
    assert result["decisions_found"] == 0


@pytest.mark.asyncio
async def test_stream_yields_chunks():
    agent = _make_agent()

    async def mock_astream(messages):
        for word in ["We ", "use ", "PostgreSQL."]:
            m = MagicMock()
            m.content = word
            yield m

    agent._llm = MagicMock()
    agent._llm.astream = mock_astream

    with patch("app.agents.query_agent.agent.get_neo4j",
               return_value=_neo4j_with_results([_SAMPLE_DECISION])):
        chunks = []
        async for chunk in agent.stream("What database do we use?"):
            chunks.append(chunk)

    assert len(chunks) == 3
    assert "".join(chunks) == "We use PostgreSQL."


@pytest.mark.asyncio
async def test_stream_no_results_yields_fallback():
    agent = _make_agent()
    with patch("app.agents.query_agent.agent.get_neo4j",
               return_value=_neo4j_with_results([])):
        chunks = []
        async for chunk in agent.stream("Unknown topic"):
            chunks.append(chunk)

    assert len(chunks) == 1
    assert "couldn't find" in chunks[0].lower()


def test_keyword_extraction():
    agent = _make_agent()
    keywords = agent._extract_keywords("What database did we choose for the auth service?")
    assert "database" in keywords or "auth" in keywords
    assert "what" not in keywords
    assert "did" not in keywords


def test_keyword_extraction_deduplicates():
    agent = _make_agent()
    keywords = agent._extract_keywords("PostgreSQL PostgreSQL database")
    assert keywords.count("PostgreSQL") == 1


@pytest.mark.asyncio
async def test_neo4j_error_returns_empty_answer():
    agent = _make_agent()
    broken_session = AsyncMock()
    broken_session.run = AsyncMock(side_effect=RuntimeError("Neo4j down"))
    broken_session.__aenter__ = AsyncMock(return_value=broken_session)
    broken_session.__aexit__ = AsyncMock(return_value=False)
    broken_driver = MagicMock()
    broken_driver.session = MagicMock(return_value=broken_session)

    with patch("app.agents.query_agent.agent.get_neo4j", return_value=broken_driver):
        result = await agent.query("What database do we use?")

    assert "couldn't find" in result["answer"].lower()
