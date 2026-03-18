"""
Unit tests — Agent 3: Dedup Gate

Tests verify:
- New chunks pass through and fingerprint is stored in Redis
- Identical chunks on a second run are dropped
- Different chunks both pass through
- Redis failure is fail-open (chunk passes, no crash)
- Fingerprint is normalised (whitespace / case insensitive)
- chunk["fingerprint"] is set on passing chunks
"""
import pytest
from unittest.mock import MagicMock, patch

from app.agents.dedup_gate.agent import DedupGateAgent, _REDIS_PREFIX
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
        "metadata": {},
    }


def _state(*chunks) -> PipelineState:
    return PipelineState(chunks=list(chunks))


# ── Redis mock helpers ────────────────────────────────────────────────────────

def _redis_first_time():
    """SET NX returns 'OK' on first write (new key)."""
    m = MagicMock()
    m.set.return_value = "OK"
    return m


def _redis_already_seen():
    """SET NX returns None when key exists (duplicate)."""
    m = MagicMock()
    m.set.return_value = None
    return m


def _redis_error():
    m = MagicMock()
    m.set.side_effect = RuntimeError("Redis connection refused")
    return m


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_chunk_passes_through():
    chunk = _make_chunk("We decided to use Postgres as our primary database.")
    with patch("app.agents.dedup_gate.agent.get_redis", return_value=_redis_first_time()):
        result = await DedupGateAgent().run(_state(chunk))
    assert len(result.deduped_chunks) == 1
    assert result.deduped_chunks[0]["id"] == "chunk-001"


@pytest.mark.asyncio
async def test_duplicate_chunk_is_dropped():
    chunk = _make_chunk("We decided to use Postgres as our primary database.")
    with patch("app.agents.dedup_gate.agent.get_redis", return_value=_redis_already_seen()):
        result = await DedupGateAgent().run(_state(chunk))
    assert result.deduped_chunks == []


@pytest.mark.asyncio
async def test_two_different_chunks_both_pass():
    c1 = _make_chunk("We chose Postgres.", "c1")
    c2 = _make_chunk("We chose Kafka for the event bus.", "c2")
    mock_redis = MagicMock()
    mock_redis.set.return_value = "OK"   # both are new
    with patch("app.agents.dedup_gate.agent.get_redis", return_value=mock_redis):
        result = await DedupGateAgent().run(_state(c1, c2))
    assert len(result.deduped_chunks) == 2


@pytest.mark.asyncio
async def test_redis_failure_is_fail_open():
    """If Redis is down, chunk passes through (pipeline doesn't crash)."""
    chunk = _make_chunk("We decided to adopt a microservices architecture.")
    with patch("app.agents.dedup_gate.agent.get_redis", return_value=_redis_error()):
        result = await DedupGateAgent().run(_state(chunk))
    assert len(result.deduped_chunks) == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_fingerprint_is_case_and_whitespace_insensitive():
    """Same content with different casing/spacing → same fingerprint → deduped."""
    agent = DedupGateAgent()
    fp1 = agent._fingerprint("We decided to use Postgres.")
    fp2 = agent._fingerprint("we  decided  to  use  postgres.")
    assert fp1 == fp2


@pytest.mark.asyncio
async def test_passing_chunk_has_fingerprint_field():
    """Chunks that pass through get a 'fingerprint' field attached."""
    chunk = _make_chunk("We decided to adopt GraphQL for all public APIs.")
    with patch("app.agents.dedup_gate.agent.get_redis", return_value=_redis_first_time()):
        result = await DedupGateAgent().run(_state(chunk))
    assert "fingerprint" in result.deduped_chunks[0]
    assert len(result.deduped_chunks[0]["fingerprint"]) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_mixed_new_and_duplicate():
    """One new, one duplicate → only new one passes."""
    new_chunk = _make_chunk("We adopted event sourcing.", "new")
    dup_chunk = _make_chunk("We adopted event sourcing.", "dup")

    seen = set()
    def smart_set(key, value, ex=None, nx=False):
        if key in seen:
            return None   # duplicate
        seen.add(key)
        return "OK"       # new

    mock_redis = MagicMock()
    mock_redis.set.side_effect = smart_set

    with patch("app.agents.dedup_gate.agent.get_redis", return_value=mock_redis):
        result = await DedupGateAgent().run(_state(new_chunk, dup_chunk))

    assert len(result.deduped_chunks) == 1
    assert result.deduped_chunks[0]["id"] == "new"
