"""Unit tests — Agent 8: Resolution Agent"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.resolution.agent import ResolutionAgent
from app.models.documents import PipelineState


def _make_decision(chunk_id: str = "c1") -> dict:
    return {
        "chunk_id": chunk_id, "doc_id": "d1", "source_type": "slack",
        "source_url": "https://example.com/123",
        "decision": "We will use PostgreSQL as our primary database.",
        "rationale": "ACID compliance and strong ecosystem.",
        "decision_date": "2025-01-15",
        "entities": ["PostgreSQL", "auth-service"],
        "normalized_entities": [
            {"name": "PostgreSQL", "type": "technology", "raw": "PostgreSQL"},
            {"name": "Auth-Service", "type": "service", "raw": "auth-service"},
        ],
        "confidence": 0.92, "raw_text": "", "metadata": {"author": "alice"},
        "flags": [], "review_status": "approved",
    }


def _state(*decs) -> PipelineState:
    return PipelineState(split_decisions=list(decs))


def _make_neo4j_mock():
    session = AsyncMock()
    session.run = AsyncMock(return_value=None)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _make_supabase_mock():
    sb = MagicMock()
    sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return sb


def _make_agent():
    with patch("app.agents.resolution.agent.get_neo4j"), \
         patch("app.agents.resolution.agent.get_supabase"):
        return ResolutionAgent()


@pytest.mark.asyncio
async def test_decision_written_to_neo4j_and_supabase():
    dec = _make_decision()
    agent = _make_agent()
    neo4j_mock = _make_neo4j_mock()
    sb_mock = _make_supabase_mock()

    with patch("app.agents.resolution.agent.get_neo4j", return_value=neo4j_mock), \
         patch("app.agents.resolution.agent.get_supabase", return_value=sb_mock):
        result = await agent.run(_state(dec))

    assert len(result.resolved_decisions) == 1
    assert result.resolved_decisions[0]["node_id"] == "c1"
    # Neo4j session.run called multiple times (decision + source + entities + author)
    assert neo4j_mock.session.return_value.__aenter__.return_value.run.call_count >= 3


@pytest.mark.asyncio
async def test_node_id_assigned_from_chunk_id():
    dec = _make_decision(chunk_id="my-unique-id")
    agent = _make_agent()
    with patch("app.agents.resolution.agent.get_neo4j", return_value=_make_neo4j_mock()), \
         patch("app.agents.resolution.agent.get_supabase", return_value=_make_supabase_mock()):
        result = await agent.run(_state(dec))
    assert result.resolved_decisions[0]["node_id"] == "my-unique-id"


@pytest.mark.asyncio
async def test_neo4j_failure_captured_in_errors():
    dec = _make_decision()
    agent = _make_agent()
    broken_session = AsyncMock()
    broken_session.run = AsyncMock(side_effect=RuntimeError("Neo4j unavailable"))
    broken_session.__aenter__ = AsyncMock(return_value=broken_session)
    broken_session.__aexit__ = AsyncMock(return_value=False)
    broken_driver = MagicMock()
    broken_driver.session = MagicMock(return_value=broken_session)

    with patch("app.agents.resolution.agent.get_neo4j", return_value=broken_driver), \
         patch("app.agents.resolution.agent.get_supabase", return_value=_make_supabase_mock()):
        result = await agent.run(_state(dec))

    assert result.resolved_decisions == []
    assert len(result.errors) == 1
    assert "Neo4j unavailable" in result.errors[0]


@pytest.mark.asyncio
async def test_multiple_decisions_all_written():
    decs = [_make_decision(f"c{i}") for i in range(3)]
    agent = _make_agent()
    with patch("app.agents.resolution.agent.get_neo4j", return_value=_make_neo4j_mock()), \
         patch("app.agents.resolution.agent.get_supabase", return_value=_make_supabase_mock()):
        result = await agent.run(PipelineState(split_decisions=decs))
    assert len(result.resolved_decisions) == 3
