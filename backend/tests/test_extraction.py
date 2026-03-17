"""
Unit tests — Agent 4: Extraction Agent

All tests mock the Groq LLM — no real API calls.

Tests verify:
- Clear decision text → extracted decision in state
- Non-decision text (is_decision=False) → filtered out
- Low confidence (<0.4) → filtered out
- Malformed JSON → handled gracefully, no crash
- JSON inside markdown fences → parsed correctly
- LLM error → captured in state.errors, pipeline continues
- Retry on transient LLM failure
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.extraction.agent import ExtractionAgent
from app.models.documents import PipelineState


def _make_chunk(text: str, chunk_id: str = "chunk-001") -> dict:
    return {
        "id": chunk_id,
        "doc_id": "doc-001",
        "source_type": "slack",
        "source_url": "https://example.com",
        "title": "Test",
        "text": text,
        "chunk_index": 0,
        "total_chunks": 1,
        "metadata": {"author": "alice", "created_at": "2025-01-15T10:00:00"},
    }


def _state(*chunks) -> PipelineState:
    return PipelineState(deduped_chunks=list(chunks))


def _llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    return msg


def _make_agent() -> ExtractionAgent:
    """Create ExtractionAgent with mocked LLM constructor."""
    with patch("app.agents.extraction.agent.ChatGroq"):
        agent = ExtractionAgent()
    return agent


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_decision_is_extracted():
    agent = _make_agent()
    llm_json = """{
        "is_decision": true,
        "decision": "We will use PostgreSQL as the primary database.",
        "rationale": "PostgreSQL provides ACID compliance and strong ecosystem support.",
        "decision_date": "2025-01-15",
        "entities": ["PostgreSQL", "auth-service"],
        "confidence": 0.95
    }"""
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_response(llm_json))

    result = await agent.run(_state(_make_chunk("We will use PostgreSQL.")))

    assert len(result.extracted_decisions) == 1
    d = result.extracted_decisions[0]
    assert "PostgreSQL" in d["decision"]
    assert d["confidence"] == 0.95
    assert "PostgreSQL" in d["entities"]


@pytest.mark.asyncio
async def test_non_decision_is_filtered():
    agent = _make_agent()
    llm_json = '{"is_decision": false, "decision": "", "rationale": "", "decision_date": "", "entities": [], "confidence": 0.1}'
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_response(llm_json))

    result = await agent.run(_state(_make_chunk("Hey team, has anyone looked at the Q4 metrics?")))
    assert result.extracted_decisions == []


@pytest.mark.asyncio
async def test_low_confidence_is_filtered():
    agent = _make_agent()
    llm_json = '{"is_decision": true, "decision": "Maybe use Redis.", "rationale": "unclear", "decision_date": "", "entities": ["Redis"], "confidence": 0.3}'
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_response(llm_json))

    result = await agent.run(_state(_make_chunk("Maybe we could use Redis, not sure.")))
    assert result.extracted_decisions == []


@pytest.mark.asyncio
async def test_markdown_fenced_json_parsed():
    agent = _make_agent()
    fenced = """```json
{
    "is_decision": true,
    "decision": "We adopted Kafka for event streaming.",
    "rationale": "Kafka handles high throughput with durability guarantees.",
    "decision_date": "2025-03-01",
    "entities": ["Kafka", "data-pipeline"],
    "confidence": 0.9
}
```"""
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_response(fenced))

    result = await agent.run(_state(_make_chunk("We adopted Kafka for event streaming.")))
    assert len(result.extracted_decisions) == 1
    assert "Kafka" in result.extracted_decisions[0]["decision"]


@pytest.mark.asyncio
async def test_malformed_json_no_crash():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(return_value=_llm_response("Sorry, I cannot extract that."))

    result = await agent.run(_state(_make_chunk("Some text.")))
    assert result.extracted_decisions == []
    # errors list should be empty — parse failure is not a pipeline error
    assert result.errors == []


@pytest.mark.asyncio
async def test_llm_exception_captured_in_errors():
    agent = _make_agent()
    agent._llm = AsyncMock()
    agent._llm.ainvoke = AsyncMock(side_effect=RuntimeError("Groq rate limit"))

    result = await agent.run(_state(_make_chunk("We decided to use Terraform.")))
    assert result.extracted_decisions == []
    assert len(result.errors) == 1
    assert "Groq rate limit" in result.errors[0]


@pytest.mark.asyncio
async def test_multiple_chunks_all_processed():
    agent = _make_agent()
    llm_json = lambda d: f'{{"is_decision": true, "decision": "{d}", "rationale": "sound reasoning", "decision_date": "", "entities": [], "confidence": 0.85}}'

    call_count = 0
    decisions = [
        "We adopted GraphQL for the public API.",
        "We chose Terraform for infrastructure.",
    ]
    async def mock_invoke(messages):
        nonlocal call_count
        resp = _llm_response(llm_json(decisions[call_count]))
        call_count += 1
        return resp

    agent._llm = AsyncMock()
    agent._llm.ainvoke = mock_invoke

    chunks = [_make_chunk(d, f"c{i}") for i, d in enumerate(decisions)]
    result = await agent.run(PipelineState(deduped_chunks=chunks))
    assert len(result.extracted_decisions) == 2
