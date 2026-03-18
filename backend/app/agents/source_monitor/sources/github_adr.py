"""
GitHub ADR source connector.

Fetches Architecture Decision Records (ADRs) from public GitHub repositories.
Reads markdown files from configured repo paths via the GitHub Contents API.
No auth required for public repos (60 req/hr unauthenticated).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.models.documents import RawDocument, SourceType
from .base import BaseSource

# Public ADR repos to ingest on first run / re-poll
_DEFAULT_ADR_REPOS = [
    {
        "owner": "joelparkerhenderson",
        "repo": "architecture-decision-record",
        "path": "examples",
    },
    {
        "owner": "npryce",
        "repo": "adr-tools",
        "path": "tests/samples",
    },
]


class GitHubADRSource(BaseSource):
    source_type = SourceType.GITHUB_ADR

    def __init__(self, repos: list[dict] | None = None) -> None:
        super().__init__()
        self.repos = repos or _DEFAULT_ADR_REPOS

    def is_configured(self) -> bool:
        return True  # Public repos — no token needed

    async def fetch_since(self, since: datetime) -> list[RawDocument]:
        self.log.info("github_adr.fetch_start", repos=len(self.repos), since=since.isoformat())
        docs: list[RawDocument] = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for repo_cfg in self.repos:
                try:
                    fetched = await self._fetch_repo_adrs(client, repo_cfg, since)
                    docs.extend(fetched)
                    self.log.info(
                        "github_adr.repo_fetched",
                        repo=f"{repo_cfg['owner']}/{repo_cfg['repo']}",
                        count=len(fetched),
                    )
                except Exception as e:
                    self.log.error(
                        "github_adr.repo_failed",
                        repo=f"{repo_cfg['owner']}/{repo_cfg['repo']}",
                        error=str(e),
                        exc_info=True,
                    )

        self.log.info("github_adr.fetch_complete", docs_found=len(docs))
        return docs

    async def _fetch_repo_adrs(
        self, client: httpx.AsyncClient, repo_cfg: dict, since: datetime
    ) -> list[RawDocument]:
        owner = repo_cfg["owner"]
        repo = repo_cfg["repo"]
        path = repo_cfg.get("path", "")

        # List directory contents
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 404:
            self.log.warning("github_adr.path_not_found", url=url)
            return []
        resp.raise_for_status()
        items = resp.json()

        docs: list[RawDocument] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name: str = item.get("name", "")
            if not (name.endswith(".md") or name.endswith(".txt")):
                continue

            try:
                content_resp = await client.get(
                    item["download_url"],
                    headers={"Accept": "text/plain"},
                )
                content_resp.raise_for_status()
                content = content_resp.text
                source_url = item.get("html_url", "")
                docs.append(RawDocument(
                    source_type=SourceType.GITHUB_ADR,
                    source_id=f"{owner}/{repo}/{item.get('path', name)}",
                    source_url=source_url,
                    title=name.replace("-", " ").replace("_", " ").removesuffix(".md"),
                    content=content,
                    author=f"{owner}/{repo}",
                    created_at=datetime.now(tz=timezone.utc),
                    metadata={"owner": owner, "repo": repo, "file": name},
                ))
            except Exception as e:
                self.log.error("github_adr.file_failed", file=name, error=str(e), exc_info=True)

        return docs
