from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.models import ResourceResult
from .base import ResourceProvider


class AuthorizedJsonProvider(ResourceProvider):
    """Search a user-controlled or licensed JSON API.

    Accepted response formats:
      [{"title": "...", "share_url": "https://pan.quark.cn/s/..."}]
      {"results": [...]}.
    """

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url
        self.token = token
        host = urlparse(base_url).hostname or "authorized-json"
        self.name = f"json:{host}"

    async def search(self, query: str) -> list[ResourceResult]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(self.base_url, params={"q": query}, headers=headers)
            response.raise_for_status()
            payload = response.json()

        rows = payload.get("results", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("provider response must be a list or {'results': [...]} object")

        results: list[ResourceResult] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            share_url = str(row.get("share_url") or row.get("url") or "").strip()
            # Deliberately accept Quark share links only; no magnets/torrents.
            if "pan.quark.cn/s/" not in share_url:
                continue
            title = str(row.get("title") or query).strip()
            results.append(
                ResourceResult(
                    title=title,
                    share_url=share_url,
                    source=str(row.get("source") or "authorized"),
                    quality=str(row.get("quality") or ""),
                    size=str(row.get("size") or ""),
                    provider=self.name,
                    extra={k: v for k, v in row.items() if k not in {"title", "share_url", "url"}},
                )
            )
        return results
