"""
Agent 2 — Chunker

Responsibilities:
- Take every RawDocument from PipelineState.raw_documents
- Split into overlapping text chunks sized for LLM context windows
- Preserve source metadata on every chunk for traceability
- Output chunks into PipelineState.chunks

Chunking strategy per source type:
  - GitHub ADR / Notion: semantic split on markdown headings first,
    then token-aware sliding window
  - Slack messages: each message is already a natural chunk (usually short)
  - Google Drive: paragraph-boundary sliding window

LangGraph node: `chunker`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import BaseAgent
from app.models.documents import PipelineState, RawDocument, SourceType

# ── Chunk size config ─────────────────────────────────────────────────────────
_CHUNK_CHARS = 1500       # target chunk size in characters (~375 tokens)
_OVERLAP_CHARS = 200      # overlap between consecutive chunks
_MIN_CHUNK_CHARS = 100    # discard chunks shorter than this


@dataclass
class Chunk:
    id: str
    doc_id: str
    source_type: str
    source_url: str
    title: str
    text: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "title": self.title,
            "text": self.text,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "metadata": self.metadata,
        }


class ChunkerAgent(BaseAgent):
    name = "chunker"

    async def _run(self, state: PipelineState) -> PipelineState:
        all_chunks: list[dict[str, Any]] = []
        total_docs = len(state.raw_documents)

        self.log.info("chunker.start", doc_count=total_docs)

        for doc in state.raw_documents:
            try:
                chunks = self._chunk_document(doc)
                self.log.debug(
                    "chunker.doc_chunked",
                    doc_id=doc.id,
                    source=doc.source_type.value,
                    title=doc.title[:60],
                    chunk_count=len(chunks),
                )
                all_chunks.extend(c.to_dict() for c in chunks)
            except Exception as e:
                self.log.error(
                    "chunker.doc_failed",
                    doc_id=doc.id,
                    source=doc.source_type.value,
                    error=str(e),
                    exc_info=True,
                )
                state.errors.append(f"chunker:{doc.id}: {e}")

        self.log.info(
            "chunker.complete",
            docs_processed=total_docs,
            chunks_produced=len(all_chunks),
        )
        state.chunks = all_chunks
        return state

    # ── Routing ───────────────────────────────────────────────────────────────

    def _chunk_document(self, doc: RawDocument) -> list[Chunk]:
        if doc.source_type == SourceType.SLACK:
            return self._chunk_slack(doc)
        elif doc.source_type in (SourceType.GITHUB_ADR, SourceType.NOTION):
            return self._chunk_markdown(doc)
        else:
            return self._chunk_sliding_window(doc)

    # ── Strategy: Slack (one message = one chunk) ─────────────────────────────

    def _chunk_slack(self, doc: RawDocument) -> list[Chunk]:
        text = doc.content.strip()
        if len(text) < _MIN_CHUNK_CHARS:
            return []
        return [self._make_chunk(doc, text, 0, 1)]

    # ── Strategy: Markdown heading-first split ────────────────────────────────

    def _chunk_markdown(self, doc: RawDocument) -> list[Chunk]:
        """Split on ## / ### headings first; fall back to sliding window per section."""
        sections = re.split(r"(?m)^(#{1,3} .+)$", doc.content)
        raw_sections: list[str] = []
        current = ""
        for part in sections:
            if re.match(r"^#{1,3} ", part):
                if current.strip():
                    raw_sections.append(current.strip())
                current = part + "\n"
            else:
                current += part
        if current.strip():
            raw_sections.append(current.strip())

        # If no headings found, fall through to sliding window
        if not raw_sections:
            return self._chunk_sliding_window(doc)

        chunks: list[Chunk] = []
        for section in raw_sections:
            if len(section) <= _CHUNK_CHARS:
                if len(section) >= _MIN_CHUNK_CHARS:
                    chunks.append(self._make_chunk(doc, section, len(chunks), -1))
            else:
                # Section is too large — slide over it
                sub = self._sliding_window_texts(section)
                for text in sub:
                    chunks.append(self._make_chunk(doc, text, len(chunks), -1))

        # Patch total_chunks now that we know the count
        total = len(chunks)
        for i, c in enumerate(chunks):
            c.chunk_index = i
            c.total_chunks = total
        return chunks

    # ── Strategy: Sliding window ──────────────────────────────────────────────

    def _chunk_sliding_window(self, doc: RawDocument) -> list[Chunk]:
        texts = self._sliding_window_texts(doc.content)
        total = len(texts)
        return [self._make_chunk(doc, t, i, total) for i, t in enumerate(texts)]

    def _sliding_window_texts(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= _CHUNK_CHARS:
            return [text] if len(text) >= _MIN_CHUNK_CHARS else []

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + _CHUNK_CHARS
            chunk = text[start:end]
            # Try to break on a sentence boundary
            if end < len(text):
                boundary = max(
                    chunk.rfind(". "),
                    chunk.rfind(".\n"),
                    chunk.rfind("\n\n"),
                )
                if boundary > _CHUNK_CHARS // 2:
                    chunk = chunk[: boundary + 1]
            if len(chunk.strip()) >= _MIN_CHUNK_CHARS:
                chunks.append(chunk.strip())
            start += len(chunk) - _OVERLAP_CHARS
            if start >= len(text):
                break
        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_chunk(
        self, doc: RawDocument, text: str, index: int, total: int
    ) -> Chunk:
        import uuid
        return Chunk(
            id=str(uuid.uuid4()),
            doc_id=doc.id,
            source_type=doc.source_type.value,
            source_url=doc.source_url,
            title=doc.title,
            text=text,
            chunk_index=index,
            total_chunks=total,
            metadata={
                **doc.metadata,
                "author": doc.author,
                "created_at": doc.created_at.isoformat(),
            },
        )
