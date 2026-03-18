"""
Neo4j schema bootstrap — constraints + indexes.

Run once at startup via `apply_schema()`.
Idempotent: uses CREATE CONSTRAINT IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

Graph model
───────────
Nodes:
  (:Decision  {id, title, rationale, date, status, source_url, confidence, stale})
  (:Entity    {id, name, type})          # services, teams, technologies
  (:Person    {id, name, email})
  (:Source    {id, url, type, ingested_at})  # slack/notion/gdrive/adr
  (:Tag       {name})

Relationships:
  (:Decision)-[:INVOLVES]->(:Entity)
  (:Decision)-[:MADE_BY]->(:Person)
  (:Decision)-[:SOURCED_FROM]->(:Source)
  (:Decision)-[:TAGGED]->(:Tag)
  (:Decision)-[:SUPERSEDES]->(:Decision)
  (:Decision)-[:CONFLICTS_WITH]->(:Decision)
  (:Decision)-[:RELATED_TO]->(:Decision)
"""
from app.core.database import get_neo4j
from app.core.logger import get_logger

log = get_logger("core.neo4j_schema")

_CONSTRAINTS = [
    "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id   IF NOT EXISTS FOR (e:Entity)   REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT person_id   IF NOT EXISTS FOR (p:Person)   REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT source_id   IF NOT EXISTS FOR (s:Source)   REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT tag_name    IF NOT EXISTS FOR (t:Tag)       REQUIRE t.name IS UNIQUE",
]

_INDEXES = [
    "CREATE INDEX decision_date   IF NOT EXISTS FOR (d:Decision) ON (d.date)",
    "CREATE INDEX decision_status IF NOT EXISTS FOR (d:Decision) ON (d.status)",
    "CREATE INDEX decision_stale  IF NOT EXISTS FOR (d:Decision) ON (d.stale)",
    "CREATE INDEX entity_type     IF NOT EXISTS FOR (e:Entity)   ON (e.type)",
    "CREATE INDEX entity_name     IF NOT EXISTS FOR (e:Entity)   ON (e.name)",
    "CREATE INDEX person_name     IF NOT EXISTS FOR (p:Person)   ON (p.name)",
    "CREATE INDEX source_type     IF NOT EXISTS FOR (s:Source)   ON (s.type)",
]


async def apply_schema() -> None:
    """Create all constraints and indexes if they do not already exist."""
    log.info("neo4j_schema.applying")
    driver = get_neo4j()
    async with driver.session() as session:
        for stmt in _CONSTRAINTS:
            log.debug("neo4j_schema.constraint", cypher=stmt)
            try:
                await session.run(stmt)
            except Exception as e:
                log.error("neo4j_schema.constraint_failed", cypher=stmt, error=str(e), exc_info=True)
                raise

        for stmt in _INDEXES:
            log.debug("neo4j_schema.index", cypher=stmt)
            try:
                await session.run(stmt)
            except Exception as e:
                log.error("neo4j_schema.index_failed", cypher=stmt, error=str(e), exc_info=True)
                raise

    log.info(
        "neo4j_schema.applied",
        constraints=len(_CONSTRAINTS),
        indexes=len(_INDEXES),
    )
