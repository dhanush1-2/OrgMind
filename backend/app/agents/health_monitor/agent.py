"""
Agent 12 — Health Monitor Agent

Responsibilities:
- Scan all Decision nodes in Neo4j
- Mark decisions as stale if older than STALE_DAYS (default 180)
- Compute health metrics: total, active, stale, conflicted, no_rationale
- Return a health report dict for the dashboard API
- Runs on a schedule (APScheduler) — also callable on-demand

Staleness rules:
  - date is older than 180 days → stale = true
  - no date recorded → stale = false (unknown, not stale)

LangGraph node: `health_monitor`
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.core.database import get_neo4j
from app.models.documents import PipelineState

_STALE_DAYS = 180

_ALL_DECISIONS_CYPHER = """
MATCH (d:Decision)
OPTIONAL MATCH (d)-[:CONFLICTS_WITH]->(conflict:Decision)
OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
RETURN d.id AS id, d.title AS title, d.date AS date,
       d.stale AS stale, d.rationale AS rationale,
       d.confidence AS confidence, d.source_url AS source_url,
       count(DISTINCT conflict) AS conflict_count,
       collect(DISTINCT e.name) AS entities
"""

_MARK_STALE_CYPHER = """
MATCH (d:Decision {id: $id})
SET d.stale = true, d.stale_marked_at = $now
"""

_MARK_ACTIVE_CYPHER = """
MATCH (d:Decision {id: $id})
SET d.stale = false
"""


class HealthMonitorAgent(BaseAgent):
    name = "health_monitor"

    async def _run(self, state: PipelineState) -> PipelineState:
        report = await self.run_health_check()
        self.log.info("health_monitor.pipeline_check_complete", report=report)
        return state

    async def run_health_check(self) -> dict[str, Any]:
        """Full health scan — callable from scheduler or API."""
        self.log.info("health_monitor.start")
        decisions = await self._fetch_all_decisions()
        now = datetime.now(tz=timezone.utc)
        stale_cutoff = now - timedelta(days=_STALE_DAYS)

        metrics = {
            "total": len(decisions),
            "active": 0,
            "stale": 0,
            "newly_stale": 0,
            "conflicted": 0,
            "no_rationale": 0,
            "no_entities": 0,
            "avg_confidence": 0.0,
            "stale_decisions": [],
            "conflicted_decisions": [],
            "checked_at": now.isoformat(),
        }

        confidences: list[float] = []

        for dec in decisions:
            dec_id = dec["id"]
            date_str = dec.get("date", "")
            is_stale = dec.get("stale", False)
            conflict_count = dec.get("conflict_count", 0)
            rationale = dec.get("rationale", "")
            entities = dec.get("entities", [])
            confidence = dec.get("confidence") or 0.0

            confidences.append(confidence)

            # Check staleness
            newly_stale = False
            if date_str:
                try:
                    dec_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if dec_date.tzinfo is None:
                        dec_date = dec_date.replace(tzinfo=timezone.utc)
                    if dec_date < stale_cutoff and not is_stale:
                        await self._mark_stale(dec_id, now)
                        is_stale = True
                        newly_stale = True
                        self.log.info("health_monitor.marked_stale", id=dec_id, date=date_str)
                    elif dec_date >= stale_cutoff and is_stale:
                        await self._mark_active(dec_id)
                        is_stale = False
                except ValueError:
                    self.log.warning("health_monitor.bad_date", id=dec_id, date=date_str)

            # Tally metrics
            if is_stale:
                metrics["stale"] += 1
                metrics["stale_decisions"].append({
                    "id": dec_id, "title": dec.get("title", ""), "date": date_str,
                    "source_url": dec.get("source_url", ""),
                })
            else:
                metrics["active"] += 1

            if newly_stale:
                metrics["newly_stale"] += 1

            if conflict_count > 0:
                metrics["conflicted"] += 1
                metrics["conflicted_decisions"].append({
                    "id": dec_id, "title": dec.get("title", ""), "conflict_count": conflict_count,
                })

            if not rationale or len(rationale) < 20:
                metrics["no_rationale"] += 1

            if not entities:
                metrics["no_entities"] += 1

        if confidences:
            metrics["avg_confidence"] = round(sum(confidences) / len(confidences), 3)

        self.log.info(
            "health_monitor.complete",
            total=metrics["total"],
            stale=metrics["stale"],
            newly_stale=metrics["newly_stale"],
            conflicted=metrics["conflicted"],
        )
        return metrics

    async def _fetch_all_decisions(self) -> list[dict[str, Any]]:
        driver = get_neo4j()
        try:
            async with driver.session() as session:
                result = await session.run(_ALL_DECISIONS_CYPHER)
                return await result.data()
        except Exception as e:
            self.log.error("health_monitor.fetch_failed", error=str(e), exc_info=True)
            return []

    async def _mark_stale(self, decision_id: str, now: datetime) -> None:
        driver = get_neo4j()
        try:
            async with driver.session() as session:
                await session.run(_MARK_STALE_CYPHER, id=decision_id, now=now.isoformat())
        except Exception as e:
            self.log.error("health_monitor.mark_stale_failed", id=decision_id, error=str(e))

    async def _mark_active(self, decision_id: str) -> None:
        driver = get_neo4j()
        try:
            async with driver.session() as session:
                await session.run(_MARK_ACTIVE_CYPHER, id=decision_id)
        except Exception as e:
            self.log.error("health_monitor.mark_active_failed", id=decision_id, error=str(e))
