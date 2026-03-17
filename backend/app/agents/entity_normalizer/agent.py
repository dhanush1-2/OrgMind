"""
Agent 7 — Entity Normalizer

Responsibilities:
- Normalize entity names across decisions (Postgres → PostgreSQL, k8s → Kubernetes)
- Classify entities by type: technology, service, team, person, process
- Deduplicate entities within each decision
- Build a registry of seen entities (cached in Redis)

No LLM needed — uses a canonical alias map + fuzzy matching (difflib).

LangGraph node: `entity_normalizer`
"""
from __future__ import annotations

import difflib
import json
from typing import Any

from app.agents.base import BaseAgent
from app.core.database import get_redis
from app.models.documents import PipelineState

_REDIS_KEY = "orgmind:entity_registry"
_SIMILARITY_THRESHOLD = 0.82    # difflib ratio cutoff for fuzzy match

# Canonical entity name → list of known aliases
_CANONICAL_MAP: dict[str, list[str]] = {
    "PostgreSQL":   ["postgres", "postgresql", "pg", "psql"],
    "MySQL":        ["mysql", "mariadb"],
    "Redis":        ["redis", "upstash"],
    "MongoDB":      ["mongo", "mongodb"],
    "Kafka":        ["kafka", "apache kafka"],
    "Kubernetes":   ["k8s", "kube", "kubernetes"],
    "Docker":       ["docker", "dockerfile"],
    "Terraform":    ["terraform", "tf"],
    "AWS":          ["amazon web services", "aws"],
    "GCP":          ["google cloud", "gcp", "google cloud platform"],
    "Azure":        ["microsoft azure", "azure"],
    "GraphQL":      ["graphql", "gql"],
    "REST":         ["rest api", "restful", "rest"],
    "gRPC":         ["grpc", "grpc api"],
    "React":        ["reactjs", "react.js"],
    "TypeScript":   ["typescript", "ts"],
    "Python":       ["python3", "py"],
    "Go":           ["golang", "go lang"],
    "Rust":         ["rust-lang"],
    "GitHub":       ["github", "gh"],
    "GitLab":       ["gitlab"],
    "Datadog":      ["datadog", "dd"],
    "Sentry":       ["sentry.io"],
    "Stripe":       ["stripe api"],
    "OpenAI":       ["openai api", "gpt", "chatgpt"],
    "Groq":         ["groq api"],
}

# Alias → canonical lookup (built once at import)
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in _CANONICAL_MAP.items():
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical

# Entity type classification keywords
_TYPE_RULES: list[tuple[list[str], str]] = [
    (["team", "squad", "chapter", "tribe", "guild", "platform", "infra"], "team"),
    (["service", "api", "endpoint", "microservice", "backend", "frontend"], "service"),
    (list(_CANONICAL_MAP.keys()), "technology"),
]


def _classify_type(entity: str) -> str:
    lower = entity.lower()
    for keywords, etype in _TYPE_RULES:
        if any(kw.lower() in lower for kw in keywords):
            return etype
    return "technology"  # default


def _normalize_entity(raw: str) -> str:
    lower = raw.strip().lower()
    # Exact alias lookup
    if lower in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[lower]
    # Fuzzy match against all known aliases
    all_aliases = list(_ALIAS_TO_CANONICAL.keys())
    matches = difflib.get_close_matches(lower, all_aliases, n=1, cutoff=_SIMILARITY_THRESHOLD)
    if matches:
        return _ALIAS_TO_CANONICAL[matches[0]]
    # Unknown entity → title-case as written
    return raw.strip().title()


class EntityNormalizerAgent(BaseAgent):
    name = "entity_normalizer"

    async def _run(self, state: PipelineState) -> PipelineState:
        decisions = state.split_decisions
        self.log.info("entity_normalizer.start", decision_count=len(decisions))

        all_entities: list[dict[str, Any]] = []
        normalized_decisions: list[dict[str, Any]] = []

        for dec in decisions:
            raw_entities: list[str] = dec.get("entities", [])
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()

            for raw in raw_entities:
                canonical = _normalize_entity(raw)
                if canonical in seen:
                    continue
                seen.add(canonical)
                etype = _classify_type(canonical)
                normalized.append({"name": canonical, "type": etype, "raw": raw})
                self.log.debug(
                    "entity_normalizer.normalized",
                    raw=raw, canonical=canonical, type=etype,
                )

            dec = {**dec, "normalized_entities": normalized}
            normalized_decisions.append(dec)
            all_entities.extend(normalized)

        # Persist entity registry snapshot to Redis
        await self._update_registry(all_entities)

        self.log.info(
            "entity_normalizer.complete",
            decisions=len(normalized_decisions),
            unique_entities=len({e["name"] for e in all_entities}),
        )
        state.split_decisions = normalized_decisions
        state.normalized_entities = all_entities
        return state

    async def _update_registry(self, entities: list[dict[str, Any]]) -> None:
        try:
            redis = get_redis()
            existing_raw = redis.get(_REDIS_KEY)
            existing: dict[str, str] = json.loads(existing_raw) if existing_raw else {}
            for e in entities:
                existing[e["name"]] = e["type"]
            redis.set(_REDIS_KEY, json.dumps(existing), ex=60 * 60 * 24 * 30)
            self.log.debug("entity_normalizer.registry_updated", count=len(existing))
        except Exception as e:
            self.log.warning("entity_normalizer.registry_failed", error=str(e))
