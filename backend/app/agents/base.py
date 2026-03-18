"""
BaseAgent — every agent inherits from this.

Provides:
- Structured logging tagged with agent name + run_id
- Standardised error capture into PipelineState
- run() wrapper that logs start/end/duration/error for every invocation
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.core.logger import get_logger
from app.models.documents import PipelineState


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self.log = get_logger(f"agent.{self.name}")

    async def run(self, state: PipelineState) -> PipelineState:
        """Call this from LangGraph. Wraps _run() with trace logging."""
        start = time.perf_counter()
        self.log.info(
            "agent.start",
            agent=self.name,
            run_id=state.run_id,
        )
        try:
            result = await self._run(state)
            elapsed = round(time.perf_counter() - start, 3)
            self.log.info(
                "agent.complete",
                agent=self.name,
                run_id=state.run_id,
                elapsed_s=elapsed,
            )
            return result
        except Exception as e:
            elapsed = round(time.perf_counter() - start, 3)
            self.log.error(
                "agent.failed",
                agent=self.name,
                run_id=state.run_id,
                elapsed_s=elapsed,
                error=str(e),
                exc_info=True,
            )
            state.errors.append(f"{self.name}: {e}")
            return state

    @abstractmethod
    async def _run(self, state: PipelineState) -> PipelineState:
        """Override in each agent subclass."""
        ...
