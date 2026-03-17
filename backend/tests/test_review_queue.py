"""Unit tests — Agent 6: Review Queue Agent"""
import pytest
from unittest.mock import MagicMock, patch

from app.agents.review_queue.agent import ReviewQueueAgent, _AUTO_APPROVE_THRESHOLD
from app.models.documents import PipelineState


def _make_decision(confidence: float = 0.9, entities=None, rationale: str = "Clear rationale for this decision.", decision_date: str = "2025-01-01") -> dict:
    return {
        "chunk_id": "c1", "doc_id": "d1", "source_type": "slack",
        "source_url": "https://example.com",
        "decision": "We will use PostgreSQL.",
        "rationale": rationale,
        "decision_date": decision_date,
        "entities": entities if entities is not None else ["PostgreSQL"],
        "confidence": confidence,
        "raw_text": "We will use PostgreSQL.", "metadata": {},
    }


def _state(*decs) -> PipelineState:
    return PipelineState(split_decisions=list(decs))


def _make_agent():
    with patch("app.agents.review_queue.agent.get_supabase"):
        return ReviewQueueAgent()


@pytest.mark.asyncio
async def test_high_confidence_is_auto_approved():
    dec = _make_decision(confidence=0.95)
    agent = _make_agent()
    with patch("app.agents.review_queue.agent.get_supabase"):
        result = await agent.run(_state(dec))
    assert len(result.review_queue) == 0
    assert len(result.split_decisions) == 1
    assert result.split_decisions[0]["review_status"] == "approved"


@pytest.mark.asyncio
async def test_low_confidence_goes_to_queue():
    dec = _make_decision(confidence=0.4)
    agent = _make_agent()
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = None
    with patch("app.agents.review_queue.agent.get_supabase", return_value=mock_sb):
        result = await agent.run(_state(dec))
    assert len(result.review_queue) == 1
    assert "low_confidence" in result.review_queue[0]["flags"]


@pytest.mark.asyncio
async def test_no_entities_flagged():
    dec = _make_decision(confidence=0.4, entities=[])
    agent = _make_agent()
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = None
    with patch("app.agents.review_queue.agent.get_supabase", return_value=mock_sb):
        result = await agent.run(_state(dec))
    flags = result.review_queue[0]["flags"]
    assert "no_entities" in flags


@pytest.mark.asyncio
async def test_vague_rationale_flagged():
    dec = _make_decision(confidence=0.4, rationale="unclear")
    agent = _make_agent()
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = None
    with patch("app.agents.review_queue.agent.get_supabase", return_value=mock_sb):
        result = await agent.run(_state(dec))
    assert "vague_rationale" in result.review_queue[0]["flags"]


@pytest.mark.asyncio
async def test_supabase_failure_captured_in_errors():
    dec = _make_decision(confidence=0.3)
    agent = _make_agent()
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.side_effect = RuntimeError("DB down")
    with patch("app.agents.review_queue.agent.get_supabase", return_value=mock_sb):
        result = await agent.run(_state(dec))
    assert any("review_queue" in e for e in result.errors)


@pytest.mark.asyncio
async def test_mixed_approved_and_queued():
    good = _make_decision(confidence=0.95)
    bad = _make_decision(confidence=0.35)
    agent = _make_agent()
    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = None
    with patch("app.agents.review_queue.agent.get_supabase", return_value=mock_sb):
        result = await agent.run(_state(good, bad))
    assert len(result.review_queue) == 1
    approved = [d for d in result.split_decisions if d["review_status"] == "approved"]
    assert len(approved) == 1
