"""
Agent 11 — Onboarding Briefing Agent

Responsibilities:
- Accept a role/team name (e.g. "backend engineer", "platform team")
- Query Neo4j for the most relevant decisions for that role
- Use Groq to generate a structured onboarding briefing document
- Return: summary, key decisions, open conflicts, recommended reading

Called directly from the API — not part of the ingestion pipeline.
"""
from __future__ import annotations

from typing import Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.core.database import get_neo4j
from app.models.documents import PipelineState

_GROQ_MODEL = "llama-3.3-70b-versatile"

_ROLE_CYPHER = """
MATCH (d:Decision)-[:INVOLVES]->(e:Entity)
WHERE toLower(e.name) CONTAINS toLower($keyword)
   OR toLower(e.type) CONTAINS toLower($keyword)
OPTIONAL MATCH (d)-[:CONFLICTS_WITH]->(conflict:Decision)
OPTIONAL MATCH (d)-[:SOURCED_FROM]->(s:Source)
RETURN d.id AS id, d.title AS decision, d.rationale AS rationale,
       d.date AS date, d.stale AS stale, d.source_url AS source_url,
       collect(DISTINCT e.name) AS entities,
       collect(DISTINCT conflict.title) AS conflicts
ORDER BY d.confidence DESC
LIMIT 15
"""

_RECENT_CYPHER = """
MATCH (d:Decision)
OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
OPTIONAL MATCH (d)-[:CONFLICTS_WITH]->(conflict:Decision)
RETURN d.id AS id, d.title AS decision, d.rationale AS rationale,
       d.date AS date, d.stale AS stale, d.source_url AS source_url,
       collect(DISTINCT e.name) AS entities,
       collect(DISTINCT conflict.title) AS conflicts
ORDER BY d.date DESC
LIMIT 10
"""

_SYSTEM = """You are OrgMind. Generate a concise, friendly onboarding briefing for
a new team member. Structure it clearly with sections. Be practical and specific."""

_BRIEFING_PROMPT = """
Generate an onboarding briefing for a new {role}.

Key decisions they need to know about:
{decisions_context}

Open conflicts to be aware of:
{conflicts_context}

Format the briefing as:
1. **Welcome Summary** (2-3 sentences about the team's tech landscape)
2. **Key Decisions You Need to Know** (bullet list with rationale)
3. **Open Conflicts / Debates** (if any — things that are still being decided)
4. **Stale Decisions to Watch** (decisions that may be outdated)
5. **Recommended Reading** (source links)

Keep it under 500 words. Be friendly and practical.
"""


class OnboardingBriefingAgent(BaseAgent):
    name = "onboarding"

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self._llm = ChatGroq(
            model=_GROQ_MODEL,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _run(self, state: PipelineState) -> PipelineState:
        return state  # Called directly via generate_briefing()

    async def generate_briefing(self, role: str) -> dict[str, Any]:
        self.log.info("onboarding.start", role=role)

        decisions = await self._fetch_decisions_for_role(role)
        if not decisions:
            decisions = await self._fetch_recent_decisions()
            self.log.info("onboarding.fallback_to_recent", count=len(decisions))

        conflicts = [
            {"decision": d["decision"], "conflicts_with": d.get("conflicts", [])}
            for d in decisions if d.get("conflicts")
        ]
        stale = [d for d in decisions if d.get("stale")]

        decisions_context = self._format_decisions(decisions)
        conflicts_context = self._format_conflicts(conflicts) if conflicts else "No known conflicts."

        prompt = _BRIEFING_PROMPT.format(
            role=role,
            decisions_context=decisions_context,
            conflicts_context=conflicts_context,
        )

        response = await self._llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])

        self.log.info(
            "onboarding.complete",
            role=role,
            decisions_used=len(decisions),
            conflicts=len(conflicts),
            stale=len(stale),
        )

        return {
            "role": role,
            "briefing": response.content,
            "decisions_count": len(decisions),
            "conflicts_count": len(conflicts),
            "stale_count": len(stale),
            "sources": [
                {"decision": d["decision"], "url": d.get("source_url", "")}
                for d in decisions if d.get("source_url")
            ],
        }

    async def _fetch_decisions_for_role(self, role: str) -> list[dict[str, Any]]:
        keywords = [w for w in role.lower().split() if len(w) > 3]
        all_results: dict[str, dict] = {}
        driver = get_neo4j()

        for keyword in keywords[:2]:
            try:
                async with driver.session() as session:
                    result = await session.run(_ROLE_CYPHER, keyword=keyword)
                    for r in await result.data():
                        if r["id"] not in all_results:
                            all_results[r["id"]] = r
            except Exception as e:
                self.log.error("onboarding.neo4j_failed", keyword=keyword, error=str(e), exc_info=True)

        return list(all_results.values())

    async def _fetch_recent_decisions(self) -> list[dict[str, Any]]:
        driver = get_neo4j()
        try:
            async with driver.session() as session:
                result = await session.run(_RECENT_CYPHER)
                return await result.data()
        except Exception as e:
            self.log.error("onboarding.recent_fetch_failed", error=str(e), exc_info=True)
            return []

    def _format_decisions(self, decisions: list[dict]) -> str:
        lines = []
        for d in decisions[:10]:
            stale = " [STALE]" if d.get("stale") else ""
            lines.append(
                f"- {d.get('decision', '')}{stale}\n"
                f"  Rationale: {d.get('rationale', 'N/A')}\n"
                f"  Entities: {', '.join(d.get('entities', []))}"
            )
        return "\n".join(lines)

    def _format_conflicts(self, conflicts: list[dict]) -> str:
        lines = []
        for c in conflicts:
            for conflict_dec in c.get("conflicts_with", []):
                lines.append(f"- '{c['decision']}' conflicts with '{conflict_dec}'")
        return "\n".join(lines) if lines else "No known conflicts."
