"""
Notion source connector.

Searches all pages updated since `since` using the Notion Search API.
Fetches the full page content as plain text via the Blocks API.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.documents import RawDocument, SourceType
from .base import BaseSource

settings = get_settings()
_NOTION_VERSION = "2022-06-28"


class NotionSource(BaseSource):
    source_type = SourceType.NOTION
    _BASE = "https://api.notion.com/v1"

    def is_configured(self) -> bool:
        return bool(settings.notion_token)

    async def fetch_since(self, since: datetime) -> list[RawDocument]:
        if not self.is_configured():
            self.log.warning("notion.not_configured", reason="NOTION_TOKEN missing")
            return []

        self.log.info("notion.fetch_start", since=since.isoformat())
        headers = {
            "Authorization": f"Bearer {settings.notion_token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }
        docs: list[RawDocument] = []

        async with httpx.AsyncClient(timeout=30) as client:
            pages = await self._search_pages(client, headers, since)
            self.log.info("notion.pages_found", count=len(pages))

            for page in pages:
                try:
                    page_id = page["id"]
                    title = self._extract_title(page)
                    url = page.get("url", "")
                    author = page.get("created_by", {}).get("id", "")
                    created_at = datetime.fromisoformat(
                        page.get("created_time", datetime.utcnow().isoformat())
                        .replace("Z", "+00:00")
                    )
                    content = await self._fetch_page_content(client, headers, page_id)
                    if not content.strip():
                        continue
                    docs.append(RawDocument(
                        source_type=SourceType.NOTION,
                        source_id=page_id,
                        source_url=url,
                        title=title,
                        content=content,
                        author=author,
                        created_at=created_at,
                        metadata={"page_id": page_id},
                    ))
                except Exception as e:
                    self.log.error("notion.page_fetch_failed", page_id=page.get("id"), error=str(e), exc_info=True)

        self.log.info("notion.fetch_complete", docs_found=len(docs))
        return docs

    async def _search_pages(
        self, client: httpx.AsyncClient, headers: dict, since: datetime
    ) -> list[dict]:
        resp = await client.post(
            f"{self._BASE}/search",
            headers=headers,
            json={
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 50,
            },
        )
        data = resp.json()
        pages = data.get("results", [])
        # Filter by last edited time
        return [
            p for p in pages
            if datetime.fromisoformat(
                p.get("last_edited_time", "2000-01-01T00:00:00Z").replace("Z", "+00:00")
            ) > since.replace(tzinfo=timezone.utc)
        ]

    async def _fetch_page_content(
        self, client: httpx.AsyncClient, headers: dict, page_id: str
    ) -> str:
        resp = await client.get(
            f"{self._BASE}/blocks/{page_id}/children",
            headers=headers,
            params={"page_size": 100},
        )
        blocks = resp.json().get("results", [])
        lines: list[str] = []
        for block in blocks:
            text = self._block_to_text(block)
            if text:
                lines.append(text)
        return "\n".join(lines)

    def _block_to_text(self, block: dict) -> str:
        btype = block.get("type", "")
        rich_texts = block.get(btype, {}).get("rich_text", [])
        return "".join(rt.get("plain_text", "") for rt in rich_texts)

    def _extract_title(self, page: dict) -> str:
        props = page.get("properties", {})
        for key in ("title", "Name", "Title"):
            prop = props.get(key, {})
            rich_texts = prop.get("title", [])
            if rich_texts:
                return "".join(rt.get("plain_text", "") for rt in rich_texts)
        return "Untitled"
