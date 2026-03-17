"""
Agent 6 — Review Queue Agent

Responsibilities:
- Score each split decision for review worthiness
- Decisions below AUTO_APPROVE_THRESHOLD go into Supabase review_queue table
- Decisions at or above threshold pass straight to resolved pipeline
- Review flags: low_confidence, no_entities, vague_rationale, no_date

Supabase table: review_queue
  id, decision_text, rationale, confidence, flags, source_url,
  source_type, status (pending/approved/rejected), created_at

LangGraph node: `review_queue`
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.agents.base import BaseAgent
from app.core.database import get_supabase
from app.models.documents import PipelineState

_AUTO_APPROVE_THRESHOLD = 0.65   # confidence >= this → auto-approve
_REVIEW_TABLE = "review_queue"


def _score_flags(dec: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if dec.get("confidence", 1.0) < _AUTO_APPROVE_THRESHOLD:
        flags.append("low_confidence")
    if not dec.get("entities"):
        flags.append("no_entities")
    rationale = dec.get("rationale", "")
    if not rationale or len(rationale) < 20:
        flags.append("vague_rationale")
    if not dec.get("decision_date"):
        flags.append("no_date")
    return flags


class ReviewQueueAgent(BaseAgent):
    name = "review_queue"

    async def _run(self, state: PipelineState) -> PipelineState:
        decisions = state.split_decisions
        self.log.info("review_queue.start", decision_count=len(decisions))

        approved: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []

        for dec in decisions:
            flags = _score_flags(dec)
            needs_review = bool(flags) and dec.get("confidence", 1.0) < _AUTO_APPROVE_THRESHOLD

            if needs_review:
                self.log.info(
                    "review_queue.flagged",
                    decision=dec.get("decision", "")[:60],
                    flags=flags,
                    confidence=dec.get("confidence"),
                )
                await self._enqueue(dec, flags, state)
                queued.append({**dec, "flags": flags, "review_status": "pending"})
            else:
                self.log.debug("review_queue.approved", decision=dec.get("decision", "")[:60])
                approved.append({**dec, "flags": flags, "review_status": "approved"})

        self.log.info(
            "review_queue.complete",
            approved=len(approved),
            queued_for_review=len(queued),
        )
        # Both approved and queued go to split_decisions for the next agents,
        # but review_queue holds the ones needing human review
        state.split_decisions = approved + queued
        state.review_queue = queued
        return state

    async def _enqueue(self, dec: dict[str, Any], flags: list[str], state: PipelineState) -> None:
        row = {
            "id": str(uuid.uuid4()),
            "decision_text": dec.get("decision", ""),
            "rationale": dec.get("rationale", ""),
            "confidence": dec.get("confidence", 0.0),
            "flags": flags,
            "source_url": dec.get("source_url", ""),
            "source_type": dec.get("source_type", ""),
            "entities": dec.get("entities", []),
            "status": "pending",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            supabase = get_supabase()
            supabase.table(_REVIEW_TABLE).insert(row).execute()
            self.log.info("review_queue.enqueued", id=row["id"])
        except Exception as e:
            self.log.error("review_queue.enqueue_failed", error=str(e), exc_info=True)
            state.errors.append(f"review_queue:enqueue: {e}")
