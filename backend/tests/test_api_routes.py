"""Tests for all API routes using FastAPI TestClient with mocked dependencies."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_neo4j_driver(session: AsyncMock) -> MagicMock:
    """Build a Neo4j driver mock whose .session() returns an async context manager."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = cm
    return driver


def _mini_app(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── /graph ────────────────────────────────────────────────────────────────────

class TestGraphRoute:
    @patch("app.api.v1.routes.graph.get_neo4j")
    def test_get_graph_ok(self, mock_get_neo4j):
        """GET /graph returns nodes and edges."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)

        node_result = AsyncMock()
        node_result.data = AsyncMock(return_value=[
            {"id": "d1", "label": "Use PostgreSQL", "type": "Decision",
             "stale": False, "confidence": 0.9, "entities": [], "authors": []}
        ])
        edge_result = AsyncMock()
        edge_result.data = AsyncMock(return_value=[])
        session.run = AsyncMock(side_effect=[node_result, edge_result])

        from app.api.v1.routes.graph import router
        client = _mini_app(router)
        resp = client.get("/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 1


# ── /decisions ────────────────────────────────────────────────────────────────

class TestDecisionsRoute:
    @patch("app.api.v1.routes.decisions.get_supabase")
    def test_list_decisions(self, mock_get_supabase):
        """GET /decisions returns decision list."""
        supabase = MagicMock()
        mock_get_supabase.return_value = supabase
        chain = MagicMock()
        supabase.table.return_value.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        chain.execute.return_value = MagicMock(data=[
            {"id": "d1", "title": "Use Redis", "source_type": "SLACK"}
        ])

        from app.api.v1.routes.decisions import router
        client = _mini_app(router)
        resp = client.get("/decisions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @patch("app.api.v1.routes.decisions.get_neo4j")
    def test_get_decision_not_found(self, mock_get_neo4j):
        """GET /decisions/{id} returns 404 when not found."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)
        result = AsyncMock()
        result.single = AsyncMock(return_value=None)
        session.run = AsyncMock(return_value=result)

        from app.api.v1.routes.decisions import router
        client = _mini_app(router)
        resp = client.get("/decisions/nonexistent")
        assert resp.status_code == 404

    @patch("app.api.v1.routes.decisions.get_neo4j")
    def test_get_timeline(self, mock_get_neo4j):
        """GET /timeline returns ordered decisions."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)
        result = AsyncMock()
        result.data = AsyncMock(return_value=[
            {"id": "d1", "decision": "Use Redis", "date": "2024-01-01",
             "stale": False, "confidence": 0.8, "source_url": None, "entities": []}
        ])
        session.run = AsyncMock(return_value=result)

        from app.api.v1.routes.decisions import router
        client = _mini_app(router)
        resp = client.get("/timeline")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ── /conflicts ────────────────────────────────────────────────────────────────

class TestConflictsRoute:
    @patch("app.api.v1.routes.conflicts.get_neo4j")
    def test_list_conflicts(self, mock_get_neo4j):
        """GET /conflicts returns list of conflict pairs."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)
        result = AsyncMock()
        result.data = AsyncMock(return_value=[
            {"source_id": "d1", "target_id": "d2", "reason": "tech overlap", "severity": "high"}
        ])
        session.run = AsyncMock(return_value=result)

        from app.api.v1.routes.conflicts import router
        client = _mini_app(router)
        resp = client.get("/conflicts")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @patch("app.api.v1.routes.conflicts.get_neo4j")
    def test_get_decision_conflicts(self, mock_get_neo4j):
        """GET /conflicts/{id} returns conflicts for a decision."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)
        result = AsyncMock()
        result.data = AsyncMock(return_value=[])
        session.run = AsyncMock(return_value=result)

        from app.api.v1.routes.conflicts import router
        client = _mini_app(router)
        resp = client.get("/conflicts/d1")
        assert resp.status_code == 200
        assert resp.json()["decision_id"] == "d1"


# ── /staleness ────────────────────────────────────────────────────────────────

class TestStalenessRoute:
    @patch("app.api.v1.routes.staleness.get_neo4j")
    def test_staleness_report(self, mock_get_neo4j):
        """GET /staleness returns metrics and stale decisions."""
        session = AsyncMock()
        mock_get_neo4j.return_value = _make_neo4j_driver(session)

        metrics_result = AsyncMock()
        metrics_result.single = AsyncMock(return_value={
            "total": 10, "stale": 2, "active": 8, "avg_confidence": 0.8
        })
        stale_result = AsyncMock()
        stale_result.data = AsyncMock(return_value=[
            {"id": "d1", "title": "Old decision", "date": "2020-01-01",
             "confidence": 0.5, "source_url": None, "entities": []}
        ])
        session.run = AsyncMock(side_effect=[metrics_result, stale_result])

        from app.api.v1.routes.staleness import router
        client = _mini_app(router)
        resp = client.get("/staleness")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert data["metrics"]["total"] == 10
        assert data["metrics"]["stale"] == 2
        assert "stale_decisions" in data


# ── /review-queue ─────────────────────────────────────────────────────────────

class TestReviewQueueRoute:
    @patch("app.api.v1.routes.review_queue_route.get_supabase")
    def test_list_review_queue(self, mock_get_supabase):
        """GET /review-queue returns flagged items."""
        supabase = MagicMock()
        mock_get_supabase.return_value = supabase
        chain = MagicMock()
        supabase.table.return_value.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        chain.execute.return_value = MagicMock(data=[
            {"id": "rq1", "decision_id": "d1", "flags": ["low_confidence"], "status": "pending"}
        ])

        from app.api.v1.routes.review_queue_route import router
        client = _mini_app(router)
        resp = client.get("/review-queue")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @patch("app.api.v1.routes.review_queue_route.get_supabase")
    def test_approve_item(self, mock_get_supabase):
        """PATCH /review-queue/{id} approves item."""
        supabase = MagicMock()
        mock_get_supabase.return_value = supabase
        chain = MagicMock()
        supabase.table.return_value.update.return_value = chain
        chain.eq.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "rq1", "status": "approve"}])

        from app.api.v1.routes.review_queue_route import router
        client = _mini_app(router)
        resp = client.patch("/review-queue/rq1", json={"action": "approve"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approve"

    @patch("app.api.v1.routes.review_queue_route.get_supabase")
    def test_invalid_action_rejected(self, mock_get_supabase):
        """PATCH /review-queue/{id} rejects invalid actions."""
        mock_get_supabase.return_value = MagicMock()
        from app.api.v1.routes.review_queue_route import router
        client = _mini_app(router)
        resp = client.patch("/review-queue/rq1", json={"action": "delete"})
        assert resp.status_code == 400

    @patch("app.api.v1.routes.review_queue_route.get_supabase")
    def test_review_queue_stats(self, mock_get_supabase):
        """GET /review-queue/stats returns counts by status."""
        supabase = MagicMock()
        mock_get_supabase.return_value = supabase
        supabase.table.return_value.select.return_value.execute.return_value = MagicMock(data=[
            {"status": "pending"}, {"status": "pending"}, {"status": "approve"}
        ])
        from app.api.v1.routes.review_queue_route import router
        client = _mini_app(router)
        resp = client.get("/review-queue/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3


# ── /onboarding ───────────────────────────────────────────────────────────────

class TestOnboardingRoute:
    @patch("app.agents.onboarding.agent.OnboardingBriefingAgent.generate_briefing", new_callable=AsyncMock)
    def test_onboarding_briefing(self, mock_generate):
        """POST /onboarding returns briefing."""
        mock_generate.return_value = {
            "role": "engineer",
            "sections": [{"title": "Tech Decisions", "content": "Use PostgreSQL"}],
            "sources": [],
        }

        from app.api.v1.routes.onboarding import router
        client = _mini_app(router)
        resp = client.post("/onboarding", json={"role": "engineer", "name": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert data["role"] == "engineer"


# ── /integrations ─────────────────────────────────────────────────────────────

class TestIntegrationsRoute:
    @patch("app.api.v1.routes.integrations.get_supabase")
    @patch("app.api.v1.routes.integrations.get_neo4j")
    @patch("app.api.v1.routes.integrations.get_redis")
    @patch("app.api.v1.routes.integrations.get_chroma")
    def test_integration_status(self, mock_chroma, mock_redis, mock_neo4j, mock_supabase):
        """GET /integrations returns status for all services."""
        # Supabase mock
        sb = MagicMock()
        mock_supabase.return_value = sb
        sb.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        # Neo4j mock
        session = AsyncMock()
        mock_neo4j.return_value = _make_neo4j_driver(session)
        neo4j_result = AsyncMock()
        neo4j_result.single = AsyncMock(return_value={"n": 5})
        session.run = AsyncMock(return_value=neo4j_result)

        # Redis mock
        redis = AsyncMock()
        mock_redis.return_value = redis
        redis.ping = AsyncMock(return_value=True)

        # ChromaDB mock
        chroma = AsyncMock()
        mock_chroma.return_value = chroma
        chroma.list_collections = AsyncMock(return_value=[])

        from app.api.v1.routes.integrations import router
        client = _mini_app(router)
        resp = client.get("/integrations")
        assert resp.status_code == 200
        data = resp.json()
        assert "integrations" in data
        assert "all_healthy" in data
