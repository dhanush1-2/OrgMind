"""Unit tests — Agent 12: Health Monitor Agent"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.health_monitor.agent import HealthMonitorAgent, _STALE_DAYS


def _make_agent():
    with patch("app.agents.health_monitor.agent.get_neo4j"):
        return HealthMonitorAgent()


def _neo4j_with(records: list[dict], mark_calls_ok: bool = True):
    session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.data = AsyncMock(return_value=records)
    session.run = AsyncMock(return_value=result_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _old_date() -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(days=_STALE_DAYS + 30)).strftime("%Y-%m-%d")


def _recent_date() -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_total_count_correct():
    records = [
        {"id": "d1", "title": "Use PostgreSQL", "date": _recent_date(), "stale": False,
         "rationale": "ACID compliance and good tooling.", "confidence": 0.9,
         "source_url": "", "conflict_count": 0, "entities": ["PostgreSQL"]},
        {"id": "d2", "title": "Use Kafka", "date": _recent_date(), "stale": False,
         "rationale": "High throughput event streaming.", "confidence": 0.85,
         "source_url": "", "conflict_count": 0, "entities": ["Kafka"]},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["total"] == 2
    assert report["active"] == 2
    assert report["stale"] == 0


@pytest.mark.asyncio
async def test_old_decision_marked_stale():
    records = [
        {"id": "d1", "title": "Use Monolith", "date": _old_date(), "stale": False,
         "rationale": "Simple to deploy initially.", "confidence": 0.7,
         "source_url": "", "conflict_count": 0, "entities": ["backend"]},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["stale"] == 1
    assert report["newly_stale"] == 1
    assert len(report["stale_decisions"]) == 1


@pytest.mark.asyncio
async def test_already_stale_not_double_counted():
    records = [
        {"id": "d1", "title": "Old decision", "date": _old_date(), "stale": True,
         "rationale": "Old reasoning.", "confidence": 0.5,
         "source_url": "", "conflict_count": 0, "entities": []},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["stale"] == 1
    assert report["newly_stale"] == 0   # already was stale


@pytest.mark.asyncio
async def test_conflicted_decisions_counted():
    records = [
        {"id": "d1", "title": "Use PostgreSQL", "date": _recent_date(), "stale": False,
         "rationale": "Good rationale here.", "confidence": 0.9,
         "source_url": "", "conflict_count": 2, "entities": ["PostgreSQL"]},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["conflicted"] == 1
    assert len(report["conflicted_decisions"]) == 1


@pytest.mark.asyncio
async def test_no_rationale_flagged():
    records = [
        {"id": "d1", "title": "Use Redis", "date": _recent_date(), "stale": False,
         "rationale": "", "confidence": 0.8,
         "source_url": "", "conflict_count": 0, "entities": ["Redis"]},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["no_rationale"] == 1


@pytest.mark.asyncio
async def test_avg_confidence_computed():
    records = [
        {"id": "d1", "title": "A", "date": _recent_date(), "stale": False,
         "rationale": "Good reason here.", "confidence": 0.8,
         "source_url": "", "conflict_count": 0, "entities": []},
        {"id": "d2", "title": "B", "date": _recent_date(), "stale": False,
         "rationale": "Another good reason.", "confidence": 0.6,
         "source_url": "", "conflict_count": 0, "entities": []},
    ]
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with(records)):
        report = await agent.run_health_check()
    assert report["avg_confidence"] == 0.7


@pytest.mark.asyncio
async def test_empty_graph_returns_zero_metrics():
    agent = _make_agent()
    with patch("app.agents.health_monitor.agent.get_neo4j", return_value=_neo4j_with([])):
        report = await agent.run_health_check()
    assert report["total"] == 0
    assert report["avg_confidence"] == 0.0
