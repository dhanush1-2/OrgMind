"""
Agent 4 — Extraction Agent

Responsibilities:
- Feed each deduped chunk to Groq LLM (llama-3.3-70b-versatile)
- Parse structured JSON response into ExtractedDecision
- Filter out non-decisions (is_decision=False) and low-confidence (<0.4)
- Output list of extracted decisions into PipelineState.extracted_decisions

LangGraph node: `extraction`
Groq model: llama-3.3-70b-versatile (free tier, high quality)
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.base import BaseAgent
from app.agents.extraction.prompts import EXTRACTION_SYSTEM, EXTRACTION_HUMAN
from app.core.config import get_settings
from app.models.documents import PipelineState

_GROQ_MODEL = "llama-3.3-70b-versatile"
_MIN_CONFIDENCE = 0.4
_MAX_CONCURRENT = 3   # stay within Groq free-tier rate limits


class ExtractionAgent(BaseAgent):
    name = "extraction"

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self._llm = ChatGroq(
            model=_GROQ_MODEL,
            api_key=settings.groq_api_key,
            temperature=0.0,        # deterministic extraction
            max_tokens=512,
        )

    async def _run(self, state: PipelineState) -> PipelineState:
        chunks = state.deduped_chunks
        self.log.info("extraction.start", chunk_count=len(chunks))

        extracted: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            self.log.debug(
                "extraction.processing_chunk",
                index=i + 1,
                total=len(chunks),
                chunk_id=chunk["id"],
            )
            try:
                result = await self._extract_chunk(chunk)
                if result:
                    extracted.append(result)
                    self.log.info(
                        "extraction.decision_found",
                        chunk_id=chunk["id"],
                        decision=result["decision"][:80],
                        confidence=result["confidence"],
                    )
                else:
                    self.log.debug("extraction.no_decision", chunk_id=chunk["id"])
            except Exception as e:
                self.log.error(
                    "extraction.chunk_failed",
                    chunk_id=chunk["id"],
                    error=str(e),
                    exc_info=True,
                )
                state.errors.append(f"extraction:{chunk['id']}: {e}")

        self.log.info(
            "extraction.complete",
            chunks_processed=len(chunks),
            decisions_extracted=len(extracted),
        )
        state.extracted_decisions = extracted
        return state

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _extract_chunk(self, chunk: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Call Groq and parse the JSON response. Retries up to 3x on failure."""
        prompt = EXTRACTION_HUMAN.format(
            text=chunk["text"][:2000],      # cap at 2000 chars per chunk
            source_type=chunk["source_type"],
            source_url=chunk.get("source_url", ""),
            author=chunk.get("metadata", {}).get("author", "unknown"),
            created_at=chunk.get("metadata", {}).get("created_at", "unknown"),
        )

        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        raw = response.content.strip()

        self.log.debug("extraction.llm_response", chunk_id=chunk["id"], raw=raw[:200])

        parsed = self._parse_json(raw)
        if not parsed:
            self.log.warning("extraction.parse_failed", chunk_id=chunk["id"], raw=raw[:200])
            return None

        if not parsed.get("is_decision", False):
            return None

        confidence = float(parsed.get("confidence", 0.0))
        if confidence < _MIN_CONFIDENCE:
            self.log.debug(
                "extraction.low_confidence",
                chunk_id=chunk["id"],
                confidence=confidence,
            )
            return None

        return {
            "chunk_id": chunk["id"],
            "doc_id": chunk["doc_id"],
            "source_type": chunk["source_type"],
            "source_url": chunk.get("source_url", ""),
            "decision": parsed.get("decision", "").strip(),
            "rationale": parsed.get("rationale", "").strip(),
            "decision_date": parsed.get("decision_date", ""),
            "entities": parsed.get("entities", []),
            "confidence": confidence,
            "raw_text": chunk["text"],
            "metadata": chunk.get("metadata", {}),
        }

    def _parse_json(self, raw: str) -> Optional[dict]:
        """Parse JSON from LLM response, handling markdown code fences."""
        # Strip ```json ... ``` wrappers if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON object anywhere in the response
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
