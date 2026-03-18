"""Unit tests — Agent 5: Multi-Decision Splitter"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.splitter.agent import MultiDecisionSplitterAgent
from app.models.documents import PipelineState


def _make_decision(decision: str, raw_text: str = "", chunk_id: str = "c1") -> dict:
    return {
        "chunk_id": chunk_id, "doc_id": "d1", "source_type": "slack",
        "source_url": "", "decision": decision, "rationale": "sound reasoning",
        "decision_date": "", "entities": ["Postgres"], "confidence": 0.9,
        "raw_text": raw_text or decision, "metadata": {},
    }


def _state(*decs) -> PipelineState:
    return PipelineState(extracted_decisions=list(decs))


def _llm_resp(content: str):
    from unittest.mock import MagicMock
    m = MagicMock(); m.content = content; return m


def _make_agent():
    with patch("app.agents.splitter.agent.ChatGroq"):
        return MultiDecisionSplitterAgent()


@pytest.mark.asyncio
async def test_single_decision_passes_unchanged():
    dec = _make_decision("We will use PostgreSQL.", "We will use PostgreSQL.")
    agent = _make_agent()
    result = await agent.run(_state(dec))
    assert len(result.split_decisions) == 1
    assert result.split_decisions[0]["decision"] == dec["decision"]


@pytest.mark.asyncio
async def test_compound_decision_is_split():
    dec = _make_decision(
        "We will use PostgreSQL and also adopt Terraform.",
        "We decided to use PostgreSQL and also agreed to adopt Terraform for infra.",
    )
    agent = _make_agent()
    llm_json = """{
        "is_compound": true,
        "decisions": [
            {"decision": "We will use PostgreSQL.", "rationale": "ACID compliance.", "entities": ["PostgreSQL"]},
            {"decision": "We will adopt Terraform.", "rationale": "Infrastructure as code.", "entities": ["Terraform"]}
        ]
    }"""
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(llm_json))
    result = await agent.run(_state(dec))
    assert len(result.split_decisions) == 2
    texts = [d["decision"] for d in result.split_decisions]
    assert any("PostgreSQL" in t for t in texts)
    assert any("Terraform" in t for t in texts)


@pytest.mark.asyncio
async def test_llm_says_not_compound_passes_through():
    dec = _make_decision("We chose Kafka and configured it with 3 brokers.", "We chose Kafka.")
    agent = _make_agent()
    llm_json = '{"is_compound": false, "decisions": [{"decision": "We chose Kafka.", "rationale": "High throughput.", "entities": ["Kafka"]}]}'
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp(llm_json))
    result = await agent.run(_state(dec))
    assert len(result.split_decisions) == 1


@pytest.mark.asyncio
async def test_llm_error_falls_back_to_original():
    dec = _make_decision("We use Postgres and Redis.", "We use Postgres and Redis.")
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))
    result = await agent.run(_state(dec))
    # Falls back: original decision passed through, error recorded
    assert len(result.split_decisions) == 1
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_no_compound_signals_skips_llm():
    """No 'and/also/additionally' → LLM never called (fast path)."""
    dec = _make_decision("We chose GraphQL.", "We chose GraphQL for the API.")
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_resp("{}"))
    result = await agent.run(_state(dec))
    agent._llm.ainvoke.assert_not_called()
    assert len(result.split_decisions) == 1
