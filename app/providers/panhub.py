from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.models import ResourceResult
from .base import ResourceProvider

_QUARK_SHARE_RE = re.compile(r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s\"'<>]*", re.I)
_SIZE_RE = re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB|KB)\b")


def _extract_merged(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Normalize PanHub API response into a ``type -> rows`` mapping."""
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return {}

    merged = data.get("merged_by_type")
    if isinstance(merged, dict):
        return {
            str(key): [item for item in value if isinstance(item, dict)]
            for key, value in merged.items()
            if isinstance(value, list)
        }

    results = data.get("results")
    if not isinstance(results, list):
        return {}

    normalized: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        links = result.get("links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                link_type = str(link.get("type") or "others")
                normalized.setdefault(link_type, []).append(
                    {
                        "url": link.get("url", ""),
                        "password": link.get("password", ""),
                        "note": result.get("title") or result.get("content") or "",
                        "datetime": result.get("datetime", ""),
                        "source": result.get("channel", ""),
                    }
                )
        elif result.get("url"):
            link_type = str(result.get("type") or "others")
            normalized.setdefault(link_type, []).append(result)
    return normalized


def _extract_size(text: str) -> str:
    match = _SIZE_RE.search(text or "")
    return f"{match.group(1)}{match.group(2).upper()}" if match else ""


class PanHubProvider(ResourceProvider):
    """Use PanHub's own JSON search endpoint instead of scraping the Vue UI.

    Only Quark share links are accepted. A PanHub instance protected by its
    optional password gate can be accessed by setting ``cookie`` to the full
    browser Cookie header (normally containing ``panhub_unlock=...``).
    """

    def __init__(
        self,
        base_url: str,
        cookie: str = "",
        *,
        concurrency: int = 4,
        timeout_seconds: int = 30,
    ):
        cleaned = base_url.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("PANHUB_BASE_URL 必须是有效的 http/https 地址")
        self.base_url = cleaned
        self.search_url = urljoin(f"{cleaned}/", "api/search")
        self.cookie = cookie.strip()
        self.concurrency = max(1, min(int(concurrency), 16))
        self.timeout_seconds = max(5, min(int(timeout_seconds), 90))
        self.name = f"panhub:{parsed.hostname}"

    async def search(self, query: str) -> list[ResourceResult]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "CinemaBot/5.4 (+personal media automation)",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie

        params = {
            "kw": query,
            "res": "merged_by_type",
            "src": "plugin",
            "plugins": "pansearch",
            "cloud_types": "quark",
            "conc": str(self.concurrency),
            "ext": '{"__plugin_timeout_ms":8000}',
        }
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(self.search_url, params=params)

        if response.status_code == 401:
            raise RuntimeError(
                "PanHub 搜索被密码门锁定；请先在浏览器解锁，再把完整 Cookie 写入 PANHUB_COOKIE"
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("PanHub 返回的不是有效 JSON") from exc

        merged = _extract_merged(payload)
        rows = merged.get("quark", [])
        results: list[ResourceResult] = []
        for row in rows:
            share_url = str(row.get("url") or "").strip()
            match = _QUARK_SHARE_RE.search(share_url)
            if not match:
                continue
            share_url = match.group(0).rstrip("，。；;)]}>")
            note = str(row.get("note") or "").strip()
            title = note or query
            password = str(row.get("password") or "").strip()
            results.append(
                ResourceResult(
                    title=title,
                    share_url=share_url,
                    source="panhub",
                    quality="",
                    size=_extract_size(note),
                    provider=self.name,
                    extra={
                        "password": password,
                        "datetime": str(row.get("datetime") or ""),
                        "panhub_source": str(row.get("source") or ""),
                    },
                )
            )
        return results
