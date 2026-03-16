"""
Shared Pydantic models used across all agents.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class SourceType(str, Enum):
    SLACK = "slack"
    NOTION = "notion"
    GOOGLE_DRIVE = "gdrive"
    GITHUB_ADR = "github_adr"
    MANUAL = "manual"


class DocumentStatus(str, Enum):
    RAW = "raw"
    CHUNKED = "chunked"
    DEDUPED = "deduped"
    EXTRACTED = "extracted"
    REVIEWED = "reviewed"
    STORED = "stored"


class RawDocument(BaseModel):
    """Output of Source Monitor — one document fetched from a source."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: SourceType
    source_id: str                        # original ID in the source system
    source_url: str = ""
    title: str = ""
    content: str                          # raw text
    author: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: DocumentStatus = DocumentStatus.RAW


class PipelineState(BaseModel):
    """
    LangGraph state object — passed between all 12 agent nodes.
    Each agent reads what it needs and writes its output fields.
    """
    # ── Input ─────────────────────────────────────────────────────────────────
    raw_documents: list[RawDocument] = Field(default_factory=list)

    # ── Agent outputs (populated as pipeline progresses) ──────────────────────
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    deduped_chunks: list[dict[str, Any]] = Field(default_factory=list)
    extracted_decisions: list[dict[str, Any]] = Field(default_factory=list)
    split_decisions: list[dict[str, Any]] = Field(default_factory=list)
    review_queue: list[dict[str, Any]] = Field(default_factory=list)
    normalized_entities: list[dict[str, Any]] = Field(default_factory=list)
    resolved_decisions: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)

    # ── Control ───────────────────────────────────────────────────────────────
    errors: list[str] = Field(default_factory=list)
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
