"""Unit tests — Agent 9: Conflict Detector"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.conflict_detector.agent import ConflictDetectorAgent
from app.models.documents import PipelineState


def _make_resolved(node_id: str, decision: str) -> dict:
    return {
        "node_id": node_id, "chunk_id": node_id, "doc_id": "d1",
        "source_type": "slack", "source_url": "",
        "decision": decision, "rationale": "sound reasoning",
        "decision_date": "", "entities": ["PostgreSQL"],
        "normalized_entities": [{"name": "PostgreSQL", "type": "technology", "raw": "PostgreSQL"}],
        "confidence": 0.9, "raw_text": "", "metadata": {},
        "flags": [], "review_status": "approved",
    }


def _state(*decs) -> PipelineState:
    return PipelineState(resolved_decisions=list(decs))


def _make_agent():
    with patch("app.agents.conflict_detector.agent.ChatGroq"), \
         patch("app.agents.conflict_detector.agent.get_neo4j"):
        return ConflictDetectorAgent()


def _llm_resp(content: str):
    m = MagicMock(); m.content = content; return m


def _neo4j_with_neighbors(neighbors: list[dict]):
    session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.data = AsyncMock(return_value=neighbors)
    session.run = AsyncMock(return_value=result_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_no_neighbors_no_conflict():
    dec = _make_resolved("d1", "We will use PostgreSQL.")
    agent = _make_agent()
    with patch("app.agents.conflict_detector.agent.get_neo4j",
               return_value=_neo4j_with_neighbors([])):
        result = await agent.run(_state(dec))
    assert result.conflicts == []


@pytest.mark.asyncio
async def test_conflict_detected_and_written():
    dec = _make_resolved("d1", "We will use PostgreSQL.")
    neighbors = [{"other_id": "d2", "other_title": "We will use MySQL.", "shared_entities": ["PostgreSQL"]}]
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(
        '{"conflicts": true, "reason": "Contradictory database choices.", "severity": "high"}'
    ))

    with patch("app.agents.conflict_detector.agent.get_neo4j",
               return_value=_neo4j_with_neighbors(neighbors)):
        result = await agent.run(_state(dec))

    assert len(result.conflicts) == 1
    assert result.conflicts[0]["severity"] == "high"
    assert result.conflicts[0]["decision_a_id"] == "d1"
    assert result.conflicts[0]["decision_b_id"] == "d2"


@pytest.mark.asyncio
async def test_no_conflict_when_llm_says_false():
    dec = _make_resolved("d1", "We will use PostgreSQL for OLTP.")
    neighbors = [{"other_id": "d2", "other_title": "We will use Redshift for analytics.", "shared_entities": ["data"]}]
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(
        '{"conflicts": false, "reason": "Different use cases, no conflict.", "severity": "low"}'
    ))

    with patch("app.agents.conflict_detector.agent.get_neo4j",
               return_value=_neo4j_with_neighbors(neighbors)):
        result = await agent.run(_state(dec))

    assert result.conflicts == []


@pytest.mark.asyncio
async def test_neo4j_failure_captured_in_errors():
    dec = _make_resolved("d1", "We will use PostgreSQL.")
    broken_session = AsyncMock()
    broken_session.run = AsyncMock(side_effect=RuntimeError("Neo4j down"))
    broken_session.__aenter__ = AsyncMock(return_value=broken_session)
    broken_session.__aexit__ = AsyncMock(return_value=False)
    broken_driver = MagicMock()
    broken_driver.session = MagicMock(return_value=broken_session)

    agent = _make_agent()
    with patch("app.agents.conflict_detector.agent.get_neo4j", return_value=broken_driver):
        result = await agent.run(_state(dec))

    assert result.conflicts == []
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_multiple_decisions_checked():
    decs = [
        _make_resolved("d1", "We will use PostgreSQL."),
        _make_resolved("d2", "We will use MySQL."),
    ]
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(
        '{"conflicts": true, "reason": "Both decisions about database choice.", "severity": "high"}'
    ))
    neighbors = [{"other_id": "d2", "other_title": "We will use MySQL.", "shared_entities": ["database"]}]

    with patch("app.agents.conflict_detector.agent.get_neo4j",
               return_value=_neo4j_with_neighbors(neighbors)):
        result = await agent.run(PipelineState(resolved_decisions=decs))

    assert len(result.conflicts) >= 1
