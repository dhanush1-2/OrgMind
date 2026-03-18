"""
Agent 5 — Multi-Decision Splitter

Responsibilities:
- Inspect each extracted decision's raw_text for compound decisions
  e.g. "We decided to use Postgres AND agreed to adopt Terraform"
- Use Groq to detect and split compound decisions into atomic ones
- Single decisions pass through unchanged
- Output: PipelineState.split_decisions

LangGraph node: `splitter`
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
import uuid

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.models.documents import PipelineState

_GROQ_MODEL = "llama-3.3-70b-versatile"

_SYSTEM = """You are an expert at identifying compound engineering decisions.
Respond ONLY with valid JSON — no explanation, no markdown."""

_HUMAN = """Does the following text contain MORE THAN ONE distinct engineering decision?

EXTRACTED DECISION: {decision}
RAW TEXT: {raw_text}

Respond with this exact JSON:
{{
  "is_compound": true or false,
  "decisions": [
    {{
      "decision": "first atomic decision sentence",
      "rationale": "rationale for this specific decision",
      "entities": ["entity1", "entity2"]
    }}
  ]
}}

Rules:
- If NOT compound, put the single decision in the decisions array unchanged
- Each decision in the array must be fully self-contained (one sentence)
- Maximum 5 split decisions
- Keep the same entities relevant to each sub-decision
"""

# Compound signal keywords — if none present, skip LLM call (fast path)
_COMPOUND_SIGNALS = [
    " and ", " also ", " additionally ", " furthermore ", " as well as ",
    " along with ", " plus ", " moreover ", ";\n", "; "
]


class MultiDecisionSplitterAgent(BaseAgent):
    name = "splitter"

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self._llm = ChatGroq(
            model=_GROQ_MODEL,
            api_key=settings.groq_api_key,
            temperature=0.0,
            max_tokens=512,
        )

    async def _run(self, state: PipelineState) -> PipelineState:
        decisions = state.extracted_decisions
        self.log.info("splitter.start", decision_count=len(decisions))

        split: list[dict[str, Any]] = []

        for dec in decisions:
            try:
                results = await self._split_if_compound(dec)
                split.extend(results)
                self.log.debug(
                    "splitter.processed",
                    original_id=dec["chunk_id"],
                    produced=len(results),
                )
            except Exception as e:
                self.log.error("splitter.failed", chunk_id=dec.get("chunk_id"), error=str(e), exc_info=True)
                state.errors.append(f"splitter:{dec.get('chunk_id')}: {e}")
                split.append(dec)  # pass through on error

        self.log.info("splitter.complete", input=len(decisions), output=len(split))
        state.split_decisions = split
        return state

    async def _split_if_compound(self, dec: dict[str, Any]) -> list[dict[str, Any]]:
        text = dec.get("decision", "")
        raw = dec.get("raw_text", "")

        # Fast path — no compound signals, skip LLM
        combined = (text + " " + raw).lower()
        if not any(sig in combined for sig in _COMPOUND_SIGNALS):
            self.log.debug("splitter.fast_path_single", decision=text[:60])
            return [dec]

        parsed = await self._ask_llm(text, raw)
        if not parsed or not parsed.get("is_compound"):
            return [dec]

        sub_decisions = parsed.get("decisions", [])
        if len(sub_decisions) <= 1:
            return [dec]

        self.log.info("splitter.compound_found", count=len(sub_decisions), original=text[:60])
        results = []
        for sub in sub_decisions:
            new_dec = {**dec}
            new_dec["chunk_id"] = str(uuid.uuid4())
            new_dec["decision"] = sub.get("decision", dec["decision"])
            new_dec["rationale"] = sub.get("rationale", dec["rationale"])
            new_dec["entities"] = sub.get("entities", dec["entities"])
            new_dec["split_from"] = dec["chunk_id"]
            results.append(new_dec)
        return results

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5), reraise=True)
    async def _ask_llm(self, decision: str, raw_text: str) -> Optional[dict]:
        prompt = _HUMAN.format(decision=decision[:500], raw_text=raw_text[:1000])
        response = await self._llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
