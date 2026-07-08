from __future__ import annotations

import json
from pathlib import Path

from app.models import ResourceResult
from .base import ResourceProvider


class LocalCatalogProvider(ResourceProvider):
    name = "local-catalog"

    def __init__(self, path: str):
        self.path = Path(path)

    async def search(self, query: str) -> list[ResourceResult]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        query_lower = query.lower()
        results: list[ResourceResult] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "")
            aliases = " ".join(str(x) for x in row.get("aliases", []))
            if query_lower not in f"{title} {aliases}".lower():
                continue
            share_url = str(row.get("share_url") or "")
            if "pan.quark.cn/s/" not in share_url:
                continue
            results.append(
                ResourceResult(
                    title=title,
                    share_url=share_url,
                    quality=str(row.get("quality") or ""),
                    size=str(row.get("size") or ""),
                    provider=self.name,
                    source="owned-catalog",
                )
            )
        return results
