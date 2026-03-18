"""
Agent 9 — Conflict Detector

Responsibilities:
- For each newly resolved decision, query Neo4j for other decisions that share entities
- Feed pairs to Groq to determine if they genuinely conflict
- Write CONFLICTS_WITH relationship in Neo4j for confirmed conflicts
- Output conflict list into PipelineState.conflicts

A conflict is: two decisions about the same entity that make contradictory choices.
e.g. "Use PostgreSQL" vs "Use MySQL" both involving the "database" entity.

LangGraph node: `conflict_detector`
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.core.database import get_neo4j
from app.models.documents import PipelineState

_GROQ_MODEL = "llama-3.3-70b-versatile"

_SYSTEM = """You are an expert at detecting conflicts between engineering decisions.
Respond ONLY with valid JSON."""

_HUMAN = """Do these two engineering decisions CONFLICT with each other?

Decision A: {decision_a}
Decision B: {decision_b}
Shared entities: {shared_entities}

A conflict means they make CONTRADICTORY choices about the same thing.
"Use PostgreSQL" vs "Use MySQL" is a conflict.
"Use PostgreSQL for OLTP" vs "Use Redshift for analytics" is NOT a conflict (different contexts).

Respond with:
{{
  "conflicts": true or false,
  "reason": "one sentence explaining why or why not",
  "severity": "high" | "medium" | "low"
}}
"""

_FIND_NEIGHBORS_CYPHER = """
MATCH (d:Decision {id: $decision_id})-[:INVOLVES]->(e:Entity)<-[:INVOLVES]-(other:Decision)
WHERE other.id <> $decision_id
RETURN other.id AS other_id, other.title AS other_title,
       collect(e.name) AS shared_entities
LIMIT 10
"""

_WRITE_CONFLICT_CYPHER = """
MATCH (a:Decision {id: $id_a}), (b:Decision {id: $id_b})
MERGE (a)-[r:CONFLICTS_WITH]->(b)
SET r.reason = $reason, r.severity = $severity, r.detected_at = $now
"""


class ConflictDetectorAgent(BaseAgent):
    name = "conflict_detector"

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self._llm = ChatGroq(
            model=_GROQ_MODEL,
            api_key=settings.groq_api_key,
            temperature=0.0,
            max_tokens=256,
        )

    async def _run(self, state: PipelineState) -> PipelineState:
        decisions = state.resolved_decisions
        self.log.info("conflict_detector.start", decision_count=len(decisions))

        all_conflicts: list[dict[str, Any]] = []

        for dec in decisions:
            try:
                conflicts = await self._detect_conflicts_for(dec)
                all_conflicts.extend(conflicts)
            except Exception as e:
                self.log.error(
                    "conflict_detector.failed",
                    node_id=dec.get("node_id"),
                    error=str(e),
                    exc_info=True,
                )
                state.errors.append(f"conflict_detector:{dec.get('node_id')}: {e}")

        self.log.info("conflict_detector.complete", conflicts_found=len(all_conflicts))
        state.conflicts = all_conflicts
        return state

    async def _detect_conflicts_for(self, dec: dict[str, Any]) -> list[dict[str, Any]]:
        node_id = dec.get("node_id") or dec.get("chunk_id")
        conflicts: list[dict[str, Any]] = []

        # Find neighbor decisions sharing entities
        neighbors = await self._find_neighbors(node_id)
        if not neighbors:
            return []

        self.log.debug(
            "conflict_detector.neighbors_found",
            node_id=node_id,
            count=len(neighbors),
        )

        for neighbor in neighbors:
            result = await self._check_conflict(
                decision_a=dec.get("decision", ""),
                decision_b=neighbor["other_title"],
                shared_entities=neighbor["shared_entities"],
            )
            if result and result.get("conflicts"):
                self.log.info(
                    "conflict_detector.conflict_found",
                    a=dec.get("decision", "")[:50],
                    b=neighbor["other_title"][:50],
                    severity=result.get("severity"),
                )
                await self._write_conflict(
                    node_id,
                    neighbor["other_id"],
                    result.get("reason", ""),
                    result.get("severity", "medium"),
                )
                conflicts.append({
                    "decision_a_id": node_id,
                    "decision_a": dec.get("decision", ""),
                    "decision_b_id": neighbor["other_id"],
                    "decision_b": neighbor["other_title"],
                    "shared_entities": neighbor["shared_entities"],
                    "reason": result.get("reason", ""),
                    "severity": result.get("severity", "medium"),
                })

        return conflicts

    async def _find_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run(_FIND_NEIGHBORS_CYPHER, decision_id=node_id)
            records = await result.data()
            return [
                {
                    "other_id": r["other_id"],
                    "other_title": r["other_title"] or "",
                    "shared_entities": r["shared_entities"],
                }
                for r in records
            ]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5), reraise=True)
    async def _check_conflict(
        self,
        decision_a: str,
        decision_b: str,
        shared_entities: list[str],
    ) -> Optional[dict[str, Any]]:
        prompt = _HUMAN.format(
            decision_a=decision_a[:300],
            decision_b=decision_b[:300],
            shared_entities=", ".join(shared_entities[:10]),
        )
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

    async def _write_conflict(
        self, id_a: str, id_b: str, reason: str, severity: str
    ) -> None:
        from datetime import datetime, timezone
        driver = get_neo4j()
        async with driver.session() as session:
            await session.run(
                _WRITE_CONFLICT_CYPHER,
                id_a=id_a,
                id_b=id_b,
                reason=reason,
                severity=severity,
                now=datetime.now(tz=timezone.utc).isoformat(),
            )
        self.log.debug("conflict_detector.relationship_written", id_a=id_a, id_b=id_b)
