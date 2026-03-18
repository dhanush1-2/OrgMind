"""
Agent 3 — Dedup Gate

Responsibilities:
- Compute a content fingerprint (SHA-256) for every chunk
- Check Redis for previously seen fingerprints
- Pass only new/unseen chunks into PipelineState.deduped_chunks
- Store new fingerprints in Redis with a 90-day TTL

Why SHA-256 over embedding similarity:
  Fast, deterministic, zero-cost. Near-duplicate detection (paraphrases)
  is handled later by the Extraction Agent's LLM — the Dedup Gate only
  blocks exact and near-exact re-ingestions of the same raw text.

Redis key schema:
  orgmind:chunk_hash:{sha256_hex}  →  "1"  (TTL 90 days)

LangGraph node: `dedup_gate`
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.agents.base import BaseAgent
from app.core.database import get_redis
from app.models.documents import PipelineState

_REDIS_TTL = 60 * 60 * 24 * 90          # 90 days in seconds
_REDIS_PREFIX = "orgmind:chunk_hash:"


class DedupGateAgent(BaseAgent):
    name = "dedup_gate"

    async def _run(self, state: PipelineState) -> PipelineState:
        total = len(state.chunks)
        self.log.info("dedup_gate.start", chunks_in=total)

        passed: list[dict[str, Any]] = []
        skipped = 0

        for chunk in state.chunks:
            fingerprint = self._fingerprint(chunk["text"])
            key = f"{_REDIS_PREFIX}{fingerprint}"

            try:
                already_seen = self._check_and_set(key)
            except Exception as e:
                # Redis failure → let the chunk through (fail open)
                self.log.warning(
                    "dedup_gate.redis_error",
                    chunk_id=chunk["id"],
                    error=str(e),
                )
                already_seen = False

            if already_seen:
                skipped += 1
                self.log.debug(
                    "dedup_gate.duplicate_dropped",
                    chunk_id=chunk["id"],
                    fingerprint=fingerprint[:12] + "…",
                )
            else:
                chunk["fingerprint"] = fingerprint
                passed.append(chunk)

        self.log.info(
            "dedup_gate.complete",
            chunks_in=total,
            chunks_passed=len(passed),
            chunks_dropped=skipped,
        )
        state.deduped_chunks = passed
        return state

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fingerprint(self, text: str) -> str:
        """
        SHA-256 of normalised text.
        Normalisation: lowercase + collapse whitespace so minor formatting
        differences don't create spurious duplicates.
        """
        normalised = " ".join(text.lower().split())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    def _check_and_set(self, key: str) -> bool:
        """
        Atomically check if key exists and set it if not.
        Returns True if the chunk was already seen (duplicate).
        """
        redis = get_redis()
        # SET key 1 EX ttl NX  — only sets if key does NOT exist
        # Returns None if key already existed, "OK" if newly set
        result = redis.set(key, "1", ex=_REDIS_TTL, nx=True)
        return result is None          # None → key existed → duplicate
