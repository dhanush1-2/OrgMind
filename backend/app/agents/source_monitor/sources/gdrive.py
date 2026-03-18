"""
Google Drive source connector.

Searches for Docs/files updated since `since` using the Drive v3 API.
Exports Google Docs as plain text for downstream processing.
Requires: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.documents import RawDocument, SourceType
from .base import BaseSource

settings = get_settings()
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_BASE = "https://www.googleapis.com/drive/v3"


class GoogleDriveSource(BaseSource):
    source_type = SourceType.GOOGLE_DRIVE

    def is_configured(self) -> bool:
        return bool(settings.google_client_id and settings.google_client_secret and settings.google_refresh_token)

    async def fetch_since(self, since: datetime) -> list[RawDocument]:
        if not self.is_configured():
            self.log.warning("gdrive.not_configured", reason="Google OAuth credentials missing")
            return []

        self.log.info("gdrive.fetch_start", since=since.isoformat())
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        docs: list[RawDocument] = []

        async with httpx.AsyncClient(timeout=30) as client:
            files = await self._list_files(client, headers, since)
            self.log.info("gdrive.files_found", count=len(files))

            for f in files:
                try:
                    file_id = f["id"]
                    name = f.get("name", "Untitled")
                    mime = f.get("mimeType", "")
                    web_url = f.get("webViewLink", "")
                    modified = datetime.fromisoformat(
                        f.get("modifiedTime", datetime.utcnow().isoformat()).replace("Z", "+00:00")
                    )

                    if "google-apps.document" in mime:
                        content = await self._export_doc(client, headers, file_id)
                    else:
                        # Skip non-text files
                        continue

                    if not content.strip():
                        continue

                    docs.append(RawDocument(
                        source_type=SourceType.GOOGLE_DRIVE,
                        source_id=file_id,
                        source_url=web_url,
                        title=name,
                        content=content,
                        author=f.get("lastModifyingUser", {}).get("displayName", ""),
                        created_at=modified,
                        metadata={"file_id": file_id, "mime_type": mime},
                    ))
                except Exception as e:
                    self.log.error("gdrive.file_failed", file_id=f.get("id"), error=str(e), exc_info=True)

        self.log.info("gdrive.fetch_complete", docs_found=len(docs))
        return docs

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": settings.google_refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            token = resp.json().get("access_token")
            self.log.info("gdrive.token_refreshed")
            return token

    async def _list_files(
        self, client: httpx.AsyncClient, headers: dict, since: datetime
    ) -> list[dict]:
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await client.get(
            f"{_DRIVE_BASE}/files",
            headers=headers,
            params={
                "q": f"modifiedTime > '{since_str}' and trashed = false",
                "fields": "files(id,name,mimeType,webViewLink,modifiedTime,lastModifyingUser)",
                "pageSize": 50,
            },
        )
        resp.raise_for_status()
        return resp.json().get("files", [])

    async def _export_doc(
        self, client: httpx.AsyncClient, headers: dict, file_id: str
    ) -> str:
        resp = await client.get(
            f"{_DRIVE_BASE}/files/{file_id}/export",
            headers=headers,
            params={"mimeType": "text/plain"},
        )
        resp.raise_for_status()
        return resp.text
