#!/usr/bin/env python3
"""
Step 17 — Seed Data Script

Two seeding strategies:
  A. Groq-generated fake company decisions (demo_company.json)
  B. Public ADR repos ingested via the pipeline

Usage:
    python scripts/seed_data.py            # both strategies
    python scripts/seed_data.py --groq     # Option A only
    python scripts/seed_data.py --adrs     # Option B only
    python scripts/seed_data.py --dry-run  # just generate JSON, no write

Writes output to: scripts/demo_company.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import argparse
import os
from pathlib import Path

# Ensure app package is importable from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.logger import setup_logging, get_logger

setup_logging()
log = get_logger("seed")

# ── Option A: Groq-generated company data ─────────────────────────────────────

GROQ_SYSTEM_PROMPT = """You are generating realistic fake architectural decision records (ADRs)
for a fictional B2B SaaS company called "NovaTech Labs" that builds data pipeline tooling.
The company has 3 teams: Platform, Data, and Product.

Generate exactly {n} decisions as a JSON array. Each decision must have:
- id: string (e.g. "dec_001")
- title: string (concise action, e.g. "Adopt PostgreSQL as primary database")
- rationale: string (2-3 sentences explaining why)
- date: ISO date string (between 2022-01-01 and 2024-12-31)
- entities: array of technology/service names (2-4 items)
- authors: array of person names (1-3 people from: Alice Chen, Bob Martinez, Carol Singh, David Park, Eve Johnson)
- source_type: one of SLACK, NOTION, GITHUB_ADR, MANUAL
- confidence: float between 0.6 and 1.0

Make decisions realistic and interconnected — some should involve the same technologies,
creating conflict opportunities (e.g., one decision picks Redis, another picks Memcached for caching).

Return ONLY valid JSON array, no markdown fences."""


async def generate_groq_decisions(n: int = 25) -> list[dict]:
    """Call Groq to generate n fake company decisions."""
    from langchain_groq import ChatGroq
    settings = get_settings()
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.groq_api_key,
        temperature=0.8,
        max_tokens=4096,
    )
    log.info("seed.groq.generating", n=n)
    prompt = GROQ_SYSTEM_PROMPT.format(n=n)
    response = await llm.ainvoke(prompt)
    content = response.content.strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()

    decisions = json.loads(content)
    log.info("seed.groq.complete", count=len(decisions))
    return decisions


# ── Option B: Public ADR repos ────────────────────────────────────────────────

PUBLIC_ADR_REPOS = [
    "joelparkerhenderson/architecture-decision-record",
    "adr/adr.github.io",
    "npryce/adr-tools",
]

async def fetch_adr_repo_docs(repo: str) -> list[dict]:
    """Fetch .md files from a public GitHub repo's docs/ or doc/adr/ folder."""
    import httpx
    # Try common ADR paths
    adr_paths = ["docs/decisions", "doc/adr", "docs/adr", "adr"]
    headers = {"Accept": "application/vnd.github+json"}
    docs = []

    async with httpx.AsyncClient(timeout=30) as client:
        for path in adr_paths:
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            try:
                r = await client.get(url, headers=headers)
                if r.status_code != 200:
                    continue
                files = r.json()
                if not isinstance(files, list):
                    continue
                for f in files[:10]:  # limit per repo
                    if f.get("name", "").endswith(".md") and f.get("download_url"):
                        content_r = await client.get(f["download_url"])
                        if content_r.status_code == 200:
                            docs.append({
                                "content": content_r.text,
                                "source_url": f["html_url"],
                                "source_type": "GITHUB_ADR",
                                "repo": repo,
                            })
                if docs:
                    break
            except Exception as e:
                log.warning("seed.adr.fetch_error", repo=repo, path=path, error=str(e))
                continue

    log.info("seed.adr.fetched", repo=repo, docs=len(docs))
    return docs


async def ingest_adr_docs(docs: list[dict]) -> dict:
    """Push ADR docs through the full pipeline."""
    from app.core.database import init_all_clients
    from app.core.neo4j_schema import apply_schema
    from app.models.documents import RawDocument, SourceType
    from app.pipeline.graph import run_pipeline

    await init_all_clients()
    await apply_schema()

    # Inject docs as MANUAL source into pipeline state by pre-populating
    # We do this by running run_pipeline which calls source_monitor —
    # instead we directly populate raw_documents and skip source_monitor
    from app.pipeline.graph import _build_graph
    from app.models.documents import PipelineState, SourceType

    raw = [
        RawDocument(
            content=d["content"],
            source_url=d.get("source_url", ""),
            source_type=SourceType.GITHUB_ADR,
            metadata={"repo": d.get("repo", "")},
        )
        for d in docs
    ]

    # Run pipeline with pre-populated raw_documents
    from app.agents.chunker import ChunkerAgent
    from app.agents.dedup_gate import DedupGateAgent
    from app.agents.extraction import ExtractionAgent
    from app.agents.splitter import SplitterAgent
    from app.agents.review_queue import ReviewQueueAgent
    from app.agents.entity_normalizer import EntityNormalizerAgent
    from app.agents.resolution import ResolutionAgent
    from app.agents.conflict_detector import ConflictDetectorAgent

    state = PipelineState(raw_documents=raw)
    for AgentClass in [
        ChunkerAgent, DedupGateAgent, ExtractionAgent, SplitterAgent,
        ReviewQueueAgent, EntityNormalizerAgent, ResolutionAgent, ConflictDetectorAgent,
    ]:
        agent = AgentClass()
        state = await agent.run(state)

    return {
        "raw_docs": len(raw),
        "decisions": len(state.decisions),
        "errors": state.errors[:5],
    }


# ── Write to Neo4j / Supabase directly ───────────────────────────────────────

async def write_groq_decisions(decisions: list[dict]) -> None:
    """Write Groq-generated decisions directly to Neo4j + Supabase."""
    from app.core.database import init_all_clients, get_neo4j, get_supabase
    from app.core.neo4j_schema import apply_schema

    await init_all_clients()
    await apply_schema()

    driver = get_neo4j()
    supabase = get_supabase()

    async with driver.session() as session:
        for d in decisions:
            # Upsert Decision node
            await session.run(
                """
                MERGE (dec:Decision {id: $id})
                SET dec.title = $title,
                    dec.rationale = $rationale,
                    dec.date = $date,
                    dec.confidence = $confidence,
                    dec.source_type = $source_type,
                    dec.stale = false
                """,
                id=d["id"],
                title=d["title"],
                rationale=d.get("rationale", ""),
                date=d.get("date", ""),
                confidence=d.get("confidence", 0.8),
                source_type=d.get("source_type", "MANUAL"),
            )
            # Upsert entities + INVOLVES relationships
            for ent_name in d.get("entities", []):
                eid = ent_name.lower().replace(" ", "_")
                await session.run(
                    """
                    MERGE (e:Entity {id: $eid})
                    SET e.name = $name, e.type = 'technology'
                    WITH e
                    MATCH (dec:Decision {id: $did})
                    MERGE (dec)-[:INVOLVES]->(e)
                    """,
                    eid=eid, name=ent_name, did=d["id"],
                )
            # Upsert persons + MADE_BY
            for author in d.get("authors", []):
                pid = author.lower().replace(" ", "_")
                await session.run(
                    """
                    MERGE (p:Person {id: $pid})
                    SET p.name = $name
                    WITH p
                    MATCH (dec:Decision {id: $did})
                    MERGE (dec)-[:MADE_BY]->(p)
                    """,
                    pid=pid, name=author, did=d["id"],
                )

    # Upsert to Supabase decisions table
    for d in decisions:
        try:
            supabase.table("decisions").upsert({
                "id": d["id"],
                "title": d["title"],
                "rationale": d.get("rationale", ""),
                "date": d.get("date", ""),
                "source_type": d.get("source_type", "MANUAL"),
                "confidence": d.get("confidence", 0.8),
                "stale": False,
                "review_status": "ok",
            }).execute()
        except Exception as e:
            log.warning("seed.supabase.upsert_failed", id=d["id"], error=str(e))

    log.info("seed.write_complete", count=len(decisions))


# ── CLI entry point ────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    run_groq = args.groq or (not args.adrs)
    run_adrs = args.adrs or (not args.groq)

    demo_path = Path(__file__).parent / "demo_company.json"

    if run_groq:
        log.info("seed.start", strategy="groq")
        decisions = await generate_groq_decisions(n=25)
        demo_path.write_text(json.dumps(decisions, indent=2))
        log.info("seed.groq.saved", path=str(demo_path))

        if not args.dry_run:
            await write_groq_decisions(decisions)
            log.info("seed.groq.written_to_db", count=len(decisions))
        else:
            log.info("seed.dry_run", skipped="db write")

    if run_adrs:
        log.info("seed.start", strategy="adrs")
        all_docs = []
        for repo in PUBLIC_ADR_REPOS:
            docs = await fetch_adr_repo_docs(repo)
            all_docs.extend(docs)
        log.info("seed.adrs.total_docs", count=len(all_docs))

        if not args.dry_run and all_docs:
            result = await ingest_adr_docs(all_docs)
            log.info("seed.adrs.pipeline_complete", **result)
        elif args.dry_run:
            log.info("seed.dry_run", skipped="pipeline ingestion", docs=len(all_docs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed OrgMind with demo data")
    parser.add_argument("--groq", action="store_true", help="Run Groq generation only")
    parser.add_argument("--adrs", action="store_true", help="Run public ADR ingestion only")
    parser.add_argument("--dry-run", action="store_true", help="Generate data but don't write to DB")
    args = parser.parse_args()
    asyncio.run(main(args))
