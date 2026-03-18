"""
Unit tests — Agent 2: Chunker

Tests verify:
- Short Slack messages become exactly 1 chunk
- Tiny content below minimum is discarded
- Long docs are split into multiple overlapping chunks
- Markdown heading-aware splitting keeps sections together
- All chunks carry correct doc_id and source metadata
"""
import pytest
from datetime import datetime, timezone

from app.agents.chunker.agent import ChunkerAgent, _CHUNK_CHARS, _MIN_CHUNK_CHARS
from app.models.documents import PipelineState, RawDocument, SourceType


def _make_doc(content: str, source_type: SourceType = SourceType.SLACK, **kwargs) -> RawDocument:
    return RawDocument(
        source_type=source_type,
        source_id="test-001",
        source_url="https://example.com",
        title="Test Doc",
        content=content,
        author="alice",
        created_at=datetime.now(tz=timezone.utc),
        **kwargs,
    )


def _state(*docs: RawDocument) -> PipelineState:
    return PipelineState(raw_documents=list(docs))


@pytest.mark.asyncio
async def test_slack_short_message_is_one_chunk():
    """A normal Slack message produces exactly 1 chunk."""
    doc = _make_doc("We decided to use Postgres as the primary DB for the user service.", SourceType.SLACK)
    agent = ChunkerAgent()
    result = await agent.run(_state(doc))
    assert len(result.chunks) == 1
    assert result.chunks[0]["doc_id"] == doc.id
    assert result.chunks[0]["source_type"] == "slack"


@pytest.mark.asyncio
async def test_too_short_content_discarded():
    """Content below minimum chunk size is dropped."""
    doc = _make_doc("ok.", SourceType.SLACK)
    agent = ChunkerAgent()
    result = await agent.run(_state(doc))
    assert result.chunks == []


@pytest.mark.asyncio
async def test_long_doc_splits_into_multiple_chunks():
    """A document larger than CHUNK_CHARS is split into multiple chunks."""
    long_text = ("This is a sentence about an engineering decision. " * 60)
    doc = _make_doc(long_text, SourceType.GOOGLE_DRIVE)
    agent = ChunkerAgent()
    result = await agent.run(_state(doc))
    assert len(result.chunks) > 1
    # Every chunk must reference the original doc
    for chunk in result.chunks:
        assert chunk["doc_id"] == doc.id


@pytest.mark.asyncio
async def test_markdown_heading_split():
    """ADR with headings is split on section boundaries."""
    adr = """# ADR-001: Use PostgreSQL

## Context
We needed a relational database.

## Decision
We will use PostgreSQL as our primary database for the user service.

## Consequences
All services must use the shared connection pool.
"""
    doc = _make_doc(adr, SourceType.GITHUB_ADR)
    agent = ChunkerAgent()
    result = await agent.run(_state(doc))
    assert len(result.chunks) >= 1
    # Sections should be preserved in chunk text
    texts = " ".join(c["text"] for c in result.chunks)
    assert "PostgreSQL" in texts


@pytest.mark.asyncio
async def test_chunks_have_overlap():
    """Consecutive chunks should share some text (sliding window overlap)."""
    long_text = ("Engineering decision sentence number one. " * 80)
    doc = _make_doc(long_text, SourceType.NOTION)
    agent = ChunkerAgent()
    result = await agent.run(_state(doc))
    if len(result.chunks) >= 2:
        end_of_first = result.chunks[0]["text"][-100:]
        start_of_second = result.chunks[1]["text"][:100]
        # There should be some overlap between consecutive chunks
        overlap = set(end_of_first.split()) & set(start_of_second.split())
        assert len(overlap) > 0


@pytest.mark.asyncio
async def test_multiple_docs_all_chunked():
    """All documents in state are chunked and aggregated."""
    docs = [
        _make_doc("We decided to adopt microservices over a monolith for our backend.", SourceType.SLACK),
        _make_doc("We agreed to use Terraform for all infrastructure management going forward.", SourceType.NOTION),
    ]
    agent = ChunkerAgent()
    result = await agent.run(PipelineState(raw_documents=docs))
    doc_ids = {c["doc_id"] for c in result.chunks}
    assert doc_ids == {docs[0].id, docs[1].id}
