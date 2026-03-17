"""
OrgMind ingestion pipeline — LangGraph StateGraph

Pipeline order (9 agents):
  source_monitor → chunker → dedup_gate → extraction
  → splitter → review_queue → entity_normalizer
  → resolution → conflict_detector → END

Agents 10-12 (query, onboarding, health_monitor) are called
directly from API routes, not part of the ingestion pipeline.
"""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.source_monitor import SourceMonitorAgent
from app.agents.chunker import ChunkerAgent
from app.agents.dedup_gate import DedupGateAgent
from app.agents.extraction import ExtractionAgent
from app.agents.splitter import MultiDecisionSplitterAgent
from app.agents.review_queue import ReviewQueueAgent
from app.agents.entity_normalizer import EntityNormalizerAgent
from app.agents.resolution import ResolutionAgent
from app.agents.conflict_detector import ConflictDetectorAgent
from app.core.logger import get_logger
from app.models.documents import PipelineState

log = get_logger("pipeline")

# Instantiate agents once (singletons)
_source_monitor = SourceMonitorAgent()
_chunker = ChunkerAgent()
_dedup_gate = DedupGateAgent()
_extraction = ExtractionAgent()
_splitter = MultiDecisionSplitterAgent()
_review_queue = ReviewQueueAgent()
_entity_normalizer = EntityNormalizerAgent()
_resolution = ResolutionAgent()
_conflict_detector = ConflictDetectorAgent()


def _build_graph() -> Any:
    """Build and compile the LangGraph StateGraph."""

    async def source_monitor_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _source_monitor.run(s)
        return result.model_dump()

    async def chunker_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _chunker.run(s)
        return result.model_dump()

    async def dedup_gate_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _dedup_gate.run(s)
        return result.model_dump()

    async def extraction_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _extraction.run(s)
        return result.model_dump()

    async def splitter_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _splitter.run(s)
        return result.model_dump()

    async def review_queue_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _review_queue.run(s)
        return result.model_dump()

    async def entity_normalizer_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _entity_normalizer.run(s)
        return result.model_dump()

    async def resolution_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _resolution.run(s)
        return result.model_dump()

    async def conflict_detector_node(state: dict) -> dict:
        s = PipelineState(**state)
        result = await _conflict_detector.run(s)
        return result.model_dump()

    graph = StateGraph(dict)
    graph.add_node("source_monitor", source_monitor_node)
    graph.add_node("chunker", chunker_node)
    graph.add_node("dedup_gate", dedup_gate_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("splitter", splitter_node)
    graph.add_node("review_queue", review_queue_node)
    graph.add_node("entity_normalizer", entity_normalizer_node)
    graph.add_node("resolution", resolution_node)
    graph.add_node("conflict_detector", conflict_detector_node)

    graph.set_entry_point("source_monitor")
    graph.add_edge("source_monitor", "chunker")
    graph.add_edge("chunker", "dedup_gate")
    graph.add_edge("dedup_gate", "extraction")
    graph.add_edge("extraction", "splitter")
    graph.add_edge("splitter", "review_queue")
    graph.add_edge("review_queue", "entity_normalizer")
    graph.add_edge("entity_normalizer", "resolution")
    graph.add_edge("resolution", "conflict_detector")
    graph.add_edge("conflict_detector", END)

    return graph.compile()


# Lazy-compiled graph (avoids import-time agent initialization issues in tests)
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


async def run_pipeline() -> dict[str, Any]:
    """Run the full ingestion pipeline and return a summary."""
    run_id = PipelineState().run_id
    log.info("pipeline.run_start", run_id=run_id)
    start = time.perf_counter()

    initial_state = PipelineState(run_id=run_id).model_dump()
    graph = _get_graph()
    final_state = await graph.ainvoke(initial_state)

    elapsed = round(time.perf_counter() - start, 2)
    errors = final_state.get("errors", [])

    summary = {
        "run_id": run_id,
        "elapsed_s": elapsed,
        "raw_documents": len(final_state.get("raw_documents", [])),
        "chunks": len(final_state.get("chunks", [])),
        "deduped_chunks": len(final_state.get("deduped_chunks", [])),
        "extracted_decisions": len(final_state.get("extracted_decisions", [])),
        "split_decisions": len(final_state.get("split_decisions", [])),
        "review_queue": len(final_state.get("review_queue", [])),
        "resolved_decisions": len(final_state.get("resolved_decisions", [])),
        "conflicts": len(final_state.get("conflicts", [])),
        "errors": errors,
        "status": "completed_with_errors" if errors else "completed",
    }

    log.info("pipeline.run_complete", **{k: v for k, v in summary.items() if k != "errors"})
    return summary
