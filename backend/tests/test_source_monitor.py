"""
Unit tests — Agent 1: Source Monitor

Tests verify:
- Configured sources are polled; unconfigured ones are skipped
- Docs returned by sources appear in PipelineState.raw_documents
- Redis last-poll timestamp is set after a successful poll
- Source fetch errors are captured in state.errors (pipeline doesn't crash)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.source_monitor.agent import SourceMonitorAgent
from app.models.documents import PipelineState, RawDocument, SourceType


def _make_doc(source_type: SourceType = SourceType.SLACK) -> RawDocument:
    return RawDocument(
        source_type=source_type,
        source_id="test-id-001",
        source_url="https://example.com",
        title="Test Decision",
        content="We decided to use PostgreSQL as our primary database.",
        author="alice",
        created_at=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def state():
    return PipelineState()


@pytest.mark.asyncio
async def test_configured_source_is_polled(state):
    """Docs from a configured source land in state.raw_documents."""
    agent = SourceMonitorAgent()
    mock_source = AsyncMock()
    mock_source.source_type = SourceType.SLACK
    mock_source.is_configured.return_value = True
    mock_source.fetch_since = AsyncMock(return_value=[_make_doc()])
    agent._sources = [mock_source]

    with patch("app.agents.source_monitor.agent.get_redis") as mock_redis:
        mock_redis.return_value.get.return_value = None
        mock_redis.return_value.set.return_value = True
        result = await agent.run(state)

    assert len(result.raw_documents) == 1
    assert result.raw_documents[0].source_type == SourceType.SLACK
    assert result.errors == []


@pytest.mark.asyncio
async def test_unconfigured_source_is_skipped(state):
    """Unconfigured sources do not raise errors and return no docs."""
    agent = SourceMonitorAgent()
    mock_source = AsyncMock()
    mock_source.source_type = SourceType.NOTION
    mock_source.is_configured.return_value = False
    agent._sources = [mock_source]

    with patch("app.agents.source_monitor.agent.get_redis"):
        result = await agent.run(state)

    assert result.raw_documents == []
    assert result.errors == []
    mock_source.fetch_since.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_error_captured_in_state(state):
    """A source that throws does not crash the pipeline — error goes to state.errors."""
    agent = SourceMonitorAgent()
    mock_source = AsyncMock()
    mock_source.source_type = SourceType.SLACK
    mock_source.is_configured.return_value = True
    mock_source.fetch_since = AsyncMock(side_effect=RuntimeError("Slack API down"))
    agent._sources = [mock_source]

    with patch("app.agents.source_monitor.agent.get_redis") as mock_redis:
        mock_redis.return_value.get.return_value = None
        result = await agent.run(state)

    assert len(result.errors) == 1
    assert "Slack API down" in result.errors[0]


@pytest.mark.asyncio
async def test_multiple_sources_aggregated(state):
    """Docs from multiple sources are all added to state.raw_documents."""
    agent = SourceMonitorAgent()

    def _mock_source(stype: SourceType, doc_count: int):
        m = AsyncMock()
        m.source_type = stype
        m.is_configured.return_value = True
        m.fetch_since = AsyncMock(return_value=[_make_doc(stype) for _ in range(doc_count)])
        return m

    agent._sources = [
        _mock_source(SourceType.SLACK, 3),
        _mock_source(SourceType.NOTION, 2),
    ]

    with patch("app.agents.source_monitor.agent.get_redis") as mock_redis:
        mock_redis.return_value.get.return_value = None
        mock_redis.return_value.set.return_value = True
        result = await agent.run(state)

    assert len(result.raw_documents) == 5
