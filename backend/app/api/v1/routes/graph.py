"""GET /api/v1/graph — Neo4j graph data for D3.js visualization."""
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_neo4j
from app.core.logger import get_logger

log = get_logger("api.graph")
router = APIRouter(tags=["graph"])


@router.get("/graph")
async def get_graph(limit: int = Query(100, le=500)):
    """
    Return nodes and edges for D3 force graph visualization.
    Nodes: Decision, Entity, Person
    Edges: INVOLVES, CONFLICTS_WITH, MADE_BY
    """
    log.info("api.graph.request", limit=limit)
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            # Fetch nodes
            node_result = await session.run(
                """
                MATCH (d:Decision)
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                OPTIONAL MATCH (d)-[:MADE_BY]->(p:Person)
                WITH d, collect(DISTINCT e) AS entities, collect(DISTINCT p) AS persons
                RETURN d.id AS id, d.title AS label, 'Decision' AS type,
                       d.stale AS stale, d.confidence AS confidence,
                       [e IN entities | {id: e.id, name: e.name, type: e.type}] AS entities,
                       [p IN persons | p.name] AS authors
                LIMIT $limit
                """,
                limit=limit,
            )
            decision_records = await node_result.data()

            # Fetch edges
            edge_result = await session.run(
                """
                MATCH (d:Decision)-[r]->(target)
                WHERE type(r) IN ['INVOLVES', 'CONFLICTS_WITH', 'MADE_BY', 'SOURCED_FROM']
                RETURN d.id AS source, target.id AS target,
                       type(r) AS relationship,
                       r.severity AS severity
                LIMIT $limit
                """,
                limit=limit * 3,
            )
            edge_records = await edge_result.data()

        # Build node set (decisions + all unique entities)
        nodes = []
        seen_ids: set[str] = set()

        for d in decision_records:
            if d["id"] not in seen_ids:
                nodes.append({
                    "id": d["id"],
                    "label": d["label"],
                    "type": "Decision",
                    "stale": d.get("stale", False),
                    "confidence": d.get("confidence", 0),
                })
                seen_ids.add(d["id"])
            for entity in d.get("entities", []):
                eid = entity.get("id", entity["name"].lower().replace(" ", "_"))
                if eid not in seen_ids:
                    nodes.append({
                        "id": eid,
                        "label": entity["name"],
                        "type": "Entity",
                        "entity_type": entity.get("type", "technology"),
                    })
                    seen_ids.add(eid)

        edges = [
            {
                "source": r["source"],
                "target": r["target"],
                "type": r["relationship"],
                "severity": r.get("severity"),
            }
            for r in edge_records
            if r["source"] and r["target"]
        ]

        log.info("api.graph.complete", nodes=len(nodes), edges=len(edges))
        return {"nodes": nodes, "edges": edges}

    except Exception as e:
        log.error("api.graph.failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
