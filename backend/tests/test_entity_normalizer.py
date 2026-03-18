"""Unit tests — Agent 7: Entity Normalizer"""
import pytest
from unittest.mock import MagicMock, patch

from app.agents.entity_normalizer.agent import EntityNormalizerAgent, _normalize_entity
from app.models.documents import PipelineState


def _make_decision(entities: list[str]) -> dict:
    return {
        "chunk_id": "c1", "doc_id": "d1", "source_type": "slack",
        "source_url": "", "decision": "Test decision.", "rationale": "sound",
        "decision_date": "", "entities": entities, "confidence": 0.9,
        "raw_text": "", "metadata": {}, "flags": [], "review_status": "approved",
    }


def _state(*decs) -> PipelineState:
    return PipelineState(split_decisions=list(decs))


def _make_agent():
    with patch("app.agents.entity_normalizer.agent.get_redis"):
        return EntityNormalizerAgent()


# ── Unit-level normalizer tests ───────────────────────────────────────────────

def test_alias_normalized_to_canonical():
    assert _normalize_entity("postgres") == "PostgreSQL"
    assert _normalize_entity("k8s") == "Kubernetes"
    assert _normalize_entity("golang") == "Go"

def test_canonical_stays_unchanged():
    assert _normalize_entity("PostgreSQL") == "PostgreSQL"
    assert _normalize_entity("Kafka") == "Kafka"

def test_unknown_entity_title_cased():
    assert _normalize_entity("my-custom-service") == "My-Custom-Service"

def test_case_insensitive():
    assert _normalize_entity("POSTGRES") == "PostgreSQL"
    assert _normalize_entity("Kubernetes") == "Kubernetes"

# ── Agent-level tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_entities_normalized_in_decisions():
    dec = _make_decision(["postgres", "k8s"])
    agent = _make_agent()
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    with patch("app.agents.entity_normalizer.agent.get_redis", return_value=mock_redis):
        result = await agent.run(_state(dec))
    normalized = result.split_decisions[0]["normalized_entities"]
    names = [e["name"] for e in normalized]
    assert "PostgreSQL" in names
    assert "Kubernetes" in names


@pytest.mark.asyncio
async def test_duplicate_entities_deduped():
    dec = _make_decision(["postgres", "PostgreSQL", "pg"])
    agent = _make_agent()
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    with patch("app.agents.entity_normalizer.agent.get_redis", return_value=mock_redis):
        result = await agent.run(_state(dec))
    normalized = result.split_decisions[0]["normalized_entities"]
    names = [e["name"] for e in normalized]
    assert names.count("PostgreSQL") == 1


@pytest.mark.asyncio
async def test_entity_type_classified():
    dec = _make_decision(["platform team", "PostgreSQL"])
    agent = _make_agent()
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    with patch("app.agents.entity_normalizer.agent.get_redis", return_value=mock_redis):
        result = await agent.run(_state(dec))
    normalized = result.split_decisions[0]["normalized_entities"]
    by_name = {e["name"]: e["type"] for e in normalized}
    assert by_name.get("Platform Team") == "team"
    assert by_name.get("PostgreSQL") == "technology"


@pytest.mark.asyncio
async def test_redis_failure_does_not_crash():
    dec = _make_decision(["Kafka"])
    agent = _make_agent()
    mock_redis = MagicMock()
    mock_redis.get.side_effect = RuntimeError("Redis down")
    with patch("app.agents.entity_normalizer.agent.get_redis", return_value=mock_redis):
        result = await agent.run(_state(dec))
    # Still produces normalized entities even if Redis fails
    assert len(result.split_decisions[0]["normalized_entities"]) == 1
