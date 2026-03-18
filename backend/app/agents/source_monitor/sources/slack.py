"""
Slack source connector.

Polls all public channels for messages that look like decisions
(messages containing decision-signal keywords or posted to #decisions).
Uses the Slack Web API (bot token).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.documents import RawDocument, SourceType
from .base import BaseSource

settings = get_settings()

_DECISION_KEYWORDS = [
    "we decided", "decision:", "agreed to", "moving forward with",
    "we will use", "chosen:", "approved:", "rejected:", "RFC:", "ADR:",
]


class SlackSource(BaseSource):
    source_type = SourceType.SLACK
    _BASE = "https://slack.com/api"

    def is_configured(self) -> bool:
        return bool(settings.slack_bot_token)

    async def fetch_since(self, since: datetime) -> list[RawDocument]:
        if not self.is_configured():
            self.log.warning("slack.not_configured", reason="SLACK_BOT_TOKEN missing")
            return []

        self.log.info("slack.fetch_start", since=since.isoformat())
        headers = {"Authorization": f"Bearer {settings.slack_bot_token}"}
        docs: list[RawDocument] = []

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Get all public channels
            channels = await self._list_channels(client, headers)
            self.log.info("slack.channels_fetched", count=len(channels))

            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)
                try:
                    messages = await self._fetch_messages(client, headers, channel_id, since)
                    for msg in messages:
                        text = msg.get("text", "")
                        if not self._is_decision_signal(text):
                            continue
                        docs.append(RawDocument(
                            source_type=SourceType.SLACK,
                            source_id=msg["ts"],
                            source_url=f"https://slack.com/archives/{channel_id}/p{msg['ts'].replace('.', '')}",
                            title=f"Slack #{channel_name}",
                            content=text,
                            author=msg.get("user", ""),
                            created_at=datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc),
                            metadata={"channel": channel_name, "channel_id": channel_id},
                        ))
                except Exception as e:
                    self.log.error("slack.channel_fetch_failed", channel=channel_name, error=str(e), exc_info=True)

        self.log.info("slack.fetch_complete", docs_found=len(docs))
        return docs

    async def _list_channels(self, client: httpx.AsyncClient, headers: dict) -> list[dict]:
        resp = await client.get(
            f"{self._BASE}/conversations.list",
            headers=headers,
            params={"types": "public_channel", "limit": 200},
        )
        data = resp.json()
        if not data.get("ok"):
            self.log.error("slack.list_channels_failed", error=data.get("error"))
            return []
        return data.get("channels", [])

    async def _fetch_messages(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        channel_id: str,
        since: datetime,
    ) -> list[dict]:
        oldest = str(since.timestamp())
        resp = await client.get(
            f"{self._BASE}/conversations.history",
            headers=headers,
            params={"channel": channel_id, "oldest": oldest, "limit": 100},
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")
        return data.get("messages", [])

    def _is_decision_signal(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in _DECISION_KEYWORDS)
