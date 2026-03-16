"""
Agent 1 — Source Monitor

Responsibilities:
- Poll all configured sources (Slack, Notion, Google Drive, GitHub ADRs)
- Track last-polled timestamp per source in Redis
- Return new RawDocuments into PipelineState

LangGraph node: `source_monitor`
Redis keys:
  orgmind:last_poll:{source_type}  →  ISO timestamp
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.source_monitor.sources import (
    SlackSource,
    NotionSource,
    GoogleDriveSource,
    GitHubADRSource,
)
from app.core.database import get_redis
from app.models.documents import PipelineState, RawDocument, SourceType

_REDIS_KEY_PREFIX = "orgmind:last_poll:"
_DEFAULT_LOOKBACK_HOURS = 24


class SourceMonitorAgent(BaseAgent):
    name = "source_monitor"

    def __init__(self) -> None:
        super().__init__()
        self._sources = [
            SlackSource(),
            NotionSource(),
            GoogleDriveSource(),
            GitHubADRSource(),
        ]

    async def _run(self, state: PipelineState) -> PipelineState:
        all_docs: list[RawDocument] = []

        for source in self._sources:
            source_type = source.source_type
            if not source.is_configured():
                self.log.info(
                    "source_monitor.skipping",
                    source=source_type.value,
                    reason="not configured",
                )
                continue

            since = await self._get_last_poll(source_type)
            self.log.info(
                "source_monitor.polling",
                source=source_type.value,
                since=since.isoformat(),
            )

            try:
                docs = await source.fetch_since(since)
                self.log.info(
                    "source_monitor.fetched",
                    source=source_type.value,
                    count=len(docs),
                )
                all_docs.extend(docs)
                await self._set_last_poll(source_type)
            except Exception as e:
                self.log.error(
                    "source_monitor.fetch_error",
                    source=source_type.value,
                    error=str(e),
                    exc_info=True,
                )
                state.errors.append(f"source_monitor:{source_type.value}: {e}")

        self.log.info("source_monitor.total_docs", count=len(all_docs))
        state.raw_documents = all_docs
        return state

    async def _get_last_poll(self, source_type: SourceType) -> datetime:
        """Return the last poll time from Redis, or now - 24h if never polled."""
        key = f"{_REDIS_KEY_PREFIX}{source_type.value}"
        try:
            redis = get_redis()
            value = redis.get(key)
            if value:
                return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
        except Exception as e:
            self.log.warning("source_monitor.redis_read_failed", key=key, error=str(e))

        # Default: look back 24 hours on first run
        return datetime.now(tz=timezone.utc) - timedelta(hours=_DEFAULT_LOOKBACK_HOURS)

    async def _set_last_poll(self, source_type: SourceType) -> None:
        """Write current UTC timestamp to Redis."""
        key = f"{_REDIS_KEY_PREFIX}{source_type.value}"
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            redis = get_redis()
            redis.set(key, now, ex=60 * 60 * 24 * 30)  # expire after 30 days
            self.log.debug("source_monitor.poll_time_saved", key=key, value=now)
        except Exception as e:
            self.log.warning("source_monitor.redis_write_failed", key=key, error=str(e))
