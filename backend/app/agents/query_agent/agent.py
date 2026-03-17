"""
Agent 10 — Query Agent

Responsibilities:
- Accept a natural language question
- Translate to Neo4j Cypher using entity extraction
- Retrieve relevant decisions from Neo4j
- Stream a grounded answer via Groq (SSE-compatible AsyncGenerator)
- Return citations with source URLs

This agent is called directly from the API (not in the ingestion pipeline).
It exposes two methods:
  - query()  → non-streaming, returns full answer dict
  - stream() → async generator, yields text chunks for SSE

LangGraph node: `query_agent`
"""
from __future__ import annotations

import re
from typing import Any, AsyncGenerator

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.core.database import get_neo4j
from app.models.documents import PipelineState

_GROQ_MODEL = "llama-3.3-70b-versatile"

_SEARCH_CYPHER = """
MATCH (d:Decision)
WHERE toLower(d.title) CONTAINS toLower($keyword)
   OR EXISTS {
       MATCH (d)-[:INVOLVES]->(e:Entity)
       WHERE toLower(e.name) CONTAINS toLower($keyword)
   }
OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
OPTIONAL MATCH (d)-[:SOURCED_FROM]->(s:Source)
OPTIONAL MATCH (d)-[:MADE_BY]->(p:Person)
RETURN d.id AS id, d.title AS decision, d.rationale AS rationale,
       d.date AS date, d.confidence AS confidence, d.stale AS stale,
       d.source_url AS source_url,
       collect(DISTINCT e.name) AS entities,
       collect(DISTINCT p.name) AS authors
ORDER BY d.confidence DESC
LIMIT 8
"""

_CONFLICT_CYPHER = """
MATCH (a:Decision {id: $id})-[r:CONFLICTS_WITH]->(b:Decision)
RETURN b.title AS conflicting_decision, r.reason AS reason, r.severity AS severity
LIMIT 3
"""

_SYSTEM_PROMPT = """You are OrgMind, an AI assistant that answers questions about
engineering decisions made by this organisation.

Answer ONLY based on the decisions provided. If the context doesn't contain enough
information, say so clearly. Always cite the source when referencing a specific decision.
Be concise and factual."""

_ANSWER_PROMPT = """Question: {question}

Relevant decisions from our knowledge base:
{context}

Answer the question based only on the decisions above.
Mention any conflicts if relevant. Include source citations."""


class QueryAgent(BaseAgent):
    name = "query_agent"

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self._llm = ChatGroq(
            model=_GROQ_MODEL,
            api_key=settings.groq_api_key,
            temperature=0.1,
            max_tokens=1024,
            streaming=True,
        )

    async def _run(self, state: PipelineState) -> PipelineState:
        # This agent is called directly via query()/stream(), not through the pipeline
        return state

    async def query(self, question: str) -> dict[str, Any]:
        """Non-streaming query — returns full answer + citations."""
        self.log.info("query_agent.query", question=question[:100])
        context_decisions = await self._retrieve(question)

        if not context_decisions:
            return {
                "answer": "I couldn't find any decisions related to your question in the knowledge base.",
                "citations": [],
                "decisions_found": 0,
            }

        context_text = self._format_context(context_decisions)
        prompt = _ANSWER_PROMPT.format(question=question, context=context_text)

        response = await self._llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        citations = [
            {"decision": d["decision"], "source_url": d.get("source_url", ""), "date": d.get("date", "")}
            for d in context_decisions
        ]

        self.log.info("query_agent.answered", question=question[:60], citations=len(citations))
        return {
            "answer": response.content,
            "citations": citations,
            "decisions_found": len(context_decisions),
        }

    async def stream(self, question: str) -> AsyncGenerator[str, None]:
        """Streaming query — yields text chunks for SSE."""
        self.log.info("query_agent.stream_start", question=question[:100])
        context_decisions = await self._retrieve(question)

        if not context_decisions:
            yield "I couldn't find any decisions related to your question in the knowledge base."
            return

        context_text = self._format_context(context_decisions)
        prompt = _ANSWER_PROMPT.format(question=question, context=context_text)

        async for chunk in self._llm.astream([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]):
            if chunk.content:
                yield chunk.content

        self.log.info("query_agent.stream_complete", question=question[:60])

    async def _retrieve(self, question: str) -> list[dict[str, Any]]:
        """Extract keywords and run Neo4j full-text search."""
        keywords = self._extract_keywords(question)
        self.log.debug("query_agent.keywords", keywords=keywords)

        all_results: dict[str, dict] = {}
        driver = get_neo4j()

        for keyword in keywords[:3]:  # cap at 3 keywords
            try:
                async with driver.session() as session:
                    result = await session.run(_SEARCH_CYPHER, keyword=keyword)
                    records = await result.data()
                    for r in records:
                        if r["id"] not in all_results:
                            all_results[r["id"]] = r
            except Exception as e:
                self.log.error("query_agent.neo4j_failed", keyword=keyword, error=str(e), exc_info=True)

        decisions = list(all_results.values())
        self.log.info("query_agent.retrieved", keyword_count=len(keywords), results=len(decisions))
        return decisions

    def _extract_keywords(self, question: str) -> list[str]:
        """Simple keyword extraction — remove stop words, keep nouns."""
        stop_words = {
            "what", "why", "how", "when", "where", "which", "who", "did", "do", "does",
            "we", "our", "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "about", "for", "with", "to", "of", "in", "on",
            "decision", "decided", "choose", "chose", "use", "using", "used",
        }
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-\.]+\b", question)
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 2]
        return list(dict.fromkeys(keywords))  # deduplicate preserving order

    def _format_context(self, decisions: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for i, d in enumerate(decisions, 1):
            stale_note = " [STALE]" if d.get("stale") else ""
            lines.append(
                f"{i}. Decision: {d.get('decision', '')}{stale_note}\n"
                f"   Rationale: {d.get('rationale', 'N/A')}\n"
                f"   Entities: {', '.join(d.get('entities', []))}\n"
                f"   Date: {d.get('date', 'unknown')} | Source: {d.get('source_url', 'N/A')}"
            )
        return "\n\n".join(lines)
