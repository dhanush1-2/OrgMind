"""GET /api/v1/query — ask a question, stream the answer via SSE."""
import asyncio
import json
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from app.core.logger import get_logger

log = get_logger("api.query")
router = APIRouter(tags=["query"])


@router.get("/query")
async def query_stream(q: str = Query(..., description="Natural language question")):
    """Stream an answer via Server-Sent Events."""
    from app.agents.query_agent import QueryAgent
    log.info("api.query.start", question=q[:100])

    async def event_stream():
        try:
            agent = QueryAgent()
            async for chunk in agent.stream(q):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            log.error("api.query.stream_error", error=str(e), exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/query/sync")
async def query_sync(q: str = Query(..., description="Natural language question")):
    """Non-streaming query — returns full answer + citations."""
    from app.agents.query_agent import QueryAgent
    log.info("api.query.sync", question=q[:100])
    agent = QueryAgent()
    return await agent.query(q)
