"""
Agent 8 — Resolution Agent

Responsibilities:
- Write each finalized decision to Neo4j as a (:Decision) node
- Write normalized entities as (:Entity) nodes with MERGE (idempotent)
- Create relationships: INVOLVES, SOURCED_FROM, MADE_BY
- Write decision metadata to Supabase decisions table for SQL queries
- Return resolved decisions with their graph node IDs

Neo4j write pattern: MERGE on decision.id (idempotent — safe to re-run)
Supabase table: decisions

LangGraph node: `resolution`
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.core.database import get_neo4j, get_supabase
from app.models.documents import PipelineState

_DECISIONS_TABLE = "decisions"


class ResolutionAgent(BaseAgent):
    name = "resolution"

    async def _run(self, state: PipelineState) -> PipelineState:
        decisions = state.split_decisions
        self.log.info("resolution.start", decision_count=len(decisions))

        resolved: list[dict[str, Any]] = []

        for dec in decisions:
            try:
                node_id = await self._write_to_neo4j(dec)
                await self._write_to_supabase(dec, node_id)
                resolved.append({**dec, "node_id": node_id})
                self.log.info(
                    "resolution.saved",
                    node_id=node_id,
                    decision=dec.get("decision", "")[:60],
                )
            except Exception as e:
                self.log.error(
                    "resolution.failed",
                    decision=dec.get("decision", "")[:60],
                    error=str(e),
                    exc_info=True,
                )
                state.errors.append(f"resolution:{dec.get('chunk_id')}: {e}")

        self.log.info("resolution.complete", resolved=len(resolved))
        state.resolved_decisions = resolved
        return state

    async def _write_to_neo4j(self, dec: dict[str, Any]) -> str:
        node_id = dec.get("chunk_id", str(uuid.uuid4()))
        driver = get_neo4j()

        async with driver.session() as session:
            # MERGE Decision node
            await session.run(
                """
                MERGE (d:Decision {id: $id})
                SET d.title       = $title,
                    d.rationale   = $rationale,
                    d.date        = $date,
                    d.status      = 'active',
                    d.source_url  = $source_url,
                    d.confidence  = $confidence,
                    d.stale       = false,
                    d.updated_at  = $updated_at
                """,
                id=node_id,
                title=dec.get("decision", ""),
                rationale=dec.get("rationale", ""),
                date=dec.get("decision_date", ""),
                source_url=dec.get("source_url", ""),
                confidence=dec.get("confidence", 0.0),
                updated_at=datetime.now(tz=timezone.utc).isoformat(),
            )
            self.log.debug("resolution.neo4j_decision_written", node_id=node_id)

            # MERGE Source node + relationship
            await session.run(
                """
                MERGE (s:Source {url: $url})
                SET s.type = $source_type, s.ingested_at = $now
                WITH s
                MATCH (d:Decision {id: $decision_id})
                MERGE (d)-[:SOURCED_FROM]->(s)
                """,
                url=dec.get("source_url", "unknown"),
                source_type=dec.get("source_type", ""),
                now=datetime.now(tz=timezone.utc).isoformat(),
                decision_id=node_id,
            )

            # MERGE Entity nodes + INVOLVES relationships
            for entity in dec.get("normalized_entities", []):
                entity_id = entity["name"].lower().replace(" ", "_")
                await session.run(
                    """
                    MERGE (e:Entity {id: $entity_id})
                    SET e.name = $name, e.type = $type
                    WITH e
                    MATCH (d:Decision {id: $decision_id})
                    MERGE (d)-[:INVOLVES]->(e)
                    """,
                    entity_id=entity_id,
                    name=entity["name"],
                    type=entity.get("type", "technology"),
                    decision_id=node_id,
                )

            # Author node if present
            author = dec.get("metadata", {}).get("author", "")
            if author:
                await session.run(
                    """
                    MERGE (p:Person {id: $person_id})
                    SET p.name = $name
                    WITH p
                    MATCH (d:Decision {id: $decision_id})
                    MERGE (d)-[:MADE_BY]->(p)
                    """,
                    person_id=author.lower().replace(" ", "_"),
                    name=author,
                    decision_id=node_id,
                )

        return node_id

    async def _write_to_supabase(self, dec: dict[str, Any], node_id: str) -> None:
        row = {
            "id": node_id,
            "decision_text": dec.get("decision", ""),
            "rationale": dec.get("rationale", ""),
            "confidence": dec.get("confidence", 0.0),
            "source_type": dec.get("source_type", ""),
            "source_url": dec.get("source_url", ""),
            "decision_date": dec.get("decision_date") or None,
            "entities": [e["name"] for e in dec.get("normalized_entities", [])],
            "review_status": dec.get("review_status", "approved"),
            "flags": dec.get("flags", []),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            supabase = get_supabase()
            supabase.table(_DECISIONS_TABLE).upsert(row, on_conflict="id").execute()
            self.log.debug("resolution.supabase_written", id=node_id)
        except Exception as e:
            self.log.error("resolution.supabase_failed", id=node_id, error=str(e), exc_info=True)
            raise
