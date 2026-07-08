from __future__ import annotations

import asyncio
import html as html_lib
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.models import ResourceResult
from .base import ResourceProvider

_QUARK_RE = re.compile(r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s\"'<>]*", re.I)
_PASSCODE_RE = re.compile(r"(?:提取码|密码|passcode)\s*[:：]?\s*([A-Za-z0-9]{2,12})", re.I)
_SIZE_RE = re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB|KB)\b")
_QUALITY_RE = re.compile(
    r"(?i)\b(2160p|4k|uhd|1080p|1080i|720p|480p|remux|bluray|web[- .]?dl|webrip|hdr10\+?|hdr|dolby[ .]?vision|dv|atmos|truehd|dts[- .]?hd|dts|aac|hevc|h\.?(?:264|265)|x(?:264|265))\b"
)
_ASSET_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js", ".ico",
    ".woff", ".woff2", ".ttf", ".xml", ".json", ".zip", ".rar", ".7z",
)
_SKIP_PATH_PARTS = (
    "/tag/", "/category/", "/author/", "/login", "/register", "/privacy", "/about",
    "/feed", "/wp-json", "/wp-admin", "/wp-content", "/static/", "/assets/",
)


@dataclass(frozen=True, slots=True)
class HeuristicSiteProfile:
    name: str
    base_url: str
    search_templates: tuple[str, ...]
    article_url_patterns: tuple[str, ...] = ()
    cookie: str = ""
    timeout_seconds: int = 30
    max_results: int = 12
    detail_concurrency: int = 3
    request_delay_seconds: float = 0.35
    browser_fallback: bool = True

    @property
    def hostname(self) -> str:
        return (urlparse(self.base_url).hostname or "").lower()


@dataclass(slots=True)
class _Candidate:
    title: str
    url: str
    score: int


def _clean_share_url(value: str) -> str:
    return value.rstrip("，。；;)]}>\\")


def _decoded_variants(text: str) -> list[str]:
    variants = [text or ""]
    current = text or ""
    for _ in range(3):
        decoded = html_lib.unescape(current).replace("\\/", "/")
        try:
            decoded = unquote(decoded)
        except Exception:
            pass
        if decoded == current:
            break
        variants.append(decoded)
        current = decoded
    return variants


def extract_quark_links(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for variant in _decoded_variants(text):
        for match in _QUARK_RE.finditer(variant):
            url = _clean_share_url(match.group(0))
            if url not in seen:
                seen.add(url)
                found.append(url)
    return found


def _normalize_for_match(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").lower())


def _same_site(host: str, expected: str) -> bool:
    host = (host or "").lower().strip(".")
    expected = (expected or "").lower().strip(".")
    return host == expected or host.endswith(f".{expected}") or expected.endswith(f".{host}")


def _is_candidate_url(url: str, hostname: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not _same_site(parsed.hostname or "", hostname):
        return False
    path = (parsed.path or "/").lower()
    if path in {"", "/"} or path.endswith(_ASSET_EXTENSIONS):
        return False
    return not any(part in path for part in _SKIP_PATH_PARTS)


def _candidate_score(
    title: str,
    url: str,
    query: str,
    article_patterns: Iterable[str],
    node: Tag,
) -> int:
    title_n = _normalize_for_match(title)
    query_n = _normalize_for_match(query)
    score = 0
    if query_n and query_n in title_n:
        score += 120
    elif query_n and title_n:
        # Reward substantial character overlap for Chinese titles.
        overlap = len(set(query_n) & set(title_n)) / max(1, len(set(query_n)))
        score += int(overlap * 55)
    for pattern in article_patterns:
        if re.search(pattern, url, re.I):
            score += 70
            break
    parent_text = (
        str(node.get("class") or "")
        + " "
        + (str(node.parent.get("class") or "") if isinstance(node.parent, Tag) else "")
    ).lower()
    if any(word in parent_text for word in ("post", "article", "result", "card", "item", "entry")):
        score += 25
    path = urlparse(url).path
    score += min(path.count("/"), 4) * 3
    if 2 <= len(title.strip()) <= 120:
        score += 10
    return score


def parse_candidates(
    html: str,
    page_url: str,
    query: str,
    hostname: str,
    article_patterns: Iterable[str],
    limit: int,
) -> list[_Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    best_by_url: dict[str, _Candidate] = {}
    for node in soup.select("a[href]"):
        href = str(node.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        url = urljoin(page_url, href)
        if not _is_candidate_url(url, hostname):
            continue
        title = (
            str(node.get("title") or "").strip()
            or node.get_text(" ", strip=True)
            or (node.find_parent(["article", "li", "div"]).get_text(" ", strip=True)
                if node.find_parent(["article", "li", "div"]) else "")
        )
        score = _candidate_score(title, url, query, article_patterns, node)
        if score < 20:
            continue
        previous = best_by_url.get(url)
        if previous is None or score > previous.score:
            best_by_url[url] = _Candidate(title=title[:240], url=url, score=score)
    return sorted(best_by_url.values(), key=lambda item: item.score, reverse=True)[:limit]



def _result_relevance(query: str, title: str) -> float:
    query_n = _normalize_for_match(query)
    title_n = _normalize_for_match(title)
    if not query_n or not title_n:
        return 0.0
    if query_n in title_n:
        return 1.0
    overlap = len(set(query_n) & set(title_n)) / max(1, len(set(query_n)))
    # Prefix/suffix noise is common in article titles, so character coverage is
    # more useful than strict token equality for Chinese names.
    return overlap


def _relevant_results(query: str, results: list[ResourceResult]) -> list[ResourceResult]:
    return [item for item in results if _result_relevance(query, item.title) >= 0.45]

def _page_title(soup: BeautifulSoup, fallback: str) -> str:
    for selector, attribute in (
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
        ("h1", ""),
        ("title", ""),
    ):
        node = soup.select_one(selector)
        if not node:
            continue
        value = str(node.get(attribute) or "").strip() if attribute else node.get_text(" ", strip=True)
        if value:
            return re.sub(r"\s*[-_|].*$", "", value).strip() or value.strip()
    return fallback.strip()


def _quality_text(text: str) -> str:
    seen: list[str] = []
    for match in _QUALITY_RE.finditer(text or ""):
        value = match.group(1).upper().replace("WEB DL", "WEB-DL").replace("WEB.DL", "WEB-DL")
        if value not in seen:
            seen.append(value)
    return " ".join(seen[:8])


def _size_text(text: str) -> str:
    match = _SIZE_RE.search(text or "")
    return f"{match.group(1)}{match.group(2).upper()}" if match else ""


def _passcode(text: str) -> str:
    match = _PASSCODE_RE.search(text or "")
    return match.group(1) if match else ""


class HeuristicSiteProvider(ResourceProvider):
    """Best-effort adapter for public HTML/JavaScript search sites.

    It never follows third-party hosts and only returns direct Quark share URLs.
    Site layouts may change; failures are isolated from other providers.
    """

    def __init__(self, profile: HeuristicSiteProfile):
        parsed = urlparse(profile.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("站点地址必须是有效的 http/https URL")
        self.profile = profile
        self.name = f"site:{profile.name}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Referer": f"{self.profile.base_url.rstrip('/')}/",
        }
        if self.profile.cookie:
            headers["Cookie"] = self.profile.cookie
        return headers

    def _search_urls(self, query: str) -> list[str]:
        encoded = quote_plus(query)
        return [
            urljoin(f"{self.profile.base_url.rstrip('/')}/", template.replace("{query}", encoded).lstrip("/"))
            for template in self.profile.search_templates
        ]

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str:
        parsed = urlparse(url)
        if not _same_site(parsed.hostname or "", self.profile.hostname):
            raise RuntimeError("拒绝访问站点白名单之外的地址")
        response = await client.get(url)
        response.raise_for_status()
        final_host = urlparse(str(response.url)).hostname or ""
        if not _same_site(final_host, self.profile.hostname):
            raise RuntimeError("站点重定向到了白名单之外的地址")
        return response.text

    def _results_from_document(self, document: str, fallback_title: str, detail_url: str) -> list[ResourceResult]:
        links = extract_quark_links(document)
        if not links:
            return []
        soup = BeautifulSoup(document, "html.parser")
        plain_text = soup.get_text(" ", strip=True)
        title = _page_title(soup, fallback_title)
        password = _passcode(plain_text)
        quality = _quality_text(f"{title} {plain_text[:5000]}")
        size = _size_text(plain_text)
        return [
            ResourceResult(
                title=title,
                share_url=url,
                source="website",
                quality=quality,
                size=size,
                provider=self.name,
                extra={
                    "password": password,
                    "detail_url": detail_url,
                    "adapter": "heuristic",
                },
            )
            for url in links
        ]

    async def _resolve_candidates(
        self,
        client: httpx.AsyncClient,
        candidates: list[_Candidate],
    ) -> list[ResourceResult]:
        semaphore = asyncio.Semaphore(self.profile.detail_concurrency)

        async def resolve(candidate: _Candidate) -> list[ResourceResult]:
            async with semaphore:
                if self.profile.request_delay_seconds:
                    await asyncio.sleep(self.profile.request_delay_seconds)
                document = await self._fetch(client, candidate.url)
            return self._results_from_document(document, candidate.title, candidate.url)

        outcomes = await asyncio.gather(*(resolve(item) for item in candidates), return_exceptions=True)
        results: list[ResourceResult] = []
        for outcome in outcomes:
            if isinstance(outcome, list):
                results.extend(outcome)
        return results

    async def _search_http(self, query: str) -> list[ResourceResult]:
        errors: list[str] = []
        async with httpx.AsyncClient(
            timeout=self.profile.timeout_seconds,
            follow_redirects=True,
            headers=self._headers(),
            limits=httpx.Limits(max_connections=max(5, self.profile.detail_concurrency + 2)),
        ) as client:
            for search_url in self._search_urls(query):
                try:
                    document = await self._fetch(client, search_url)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    continue
                direct = self._results_from_document(document, query, search_url)
                candidates = parse_candidates(
                    document,
                    search_url,
                    query,
                    self.profile.hostname,
                    self.profile.article_url_patterns,
                    self.profile.max_results,
                )
                detailed = await self._resolve_candidates(client, candidates) if candidates else []
                combined = _relevant_results(query, _deduplicate(direct + detailed))
                if combined:
                    return combined
        if errors and len(errors) == len(self.profile.search_templates):
            raise RuntimeError(f"{self.profile.name} 搜索请求全部失败：{','.join(errors[:3])}")
        return []

    async def _search_browser(self, query: str) -> list[ResourceResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            browser_headers = {key: value for key, value in self._headers().items() if key.lower() != "cookie"}
            context = await browser.new_context(extra_http_headers=browser_headers)
            if self.profile.cookie:
                cookies = []
                for part in self.profile.cookie.split(";"):
                    if "=" not in part:
                        continue
                    name, value = part.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": self.profile.hostname,
                        "path": "/",
                    })
                if cookies:
                    await context.add_cookies(cookies)
            try:
                for search_url in self._search_urls(query):
                    page = await context.new_page()
                    try:
                        await page.goto(
                            search_url,
                            wait_until="domcontentloaded",
                            timeout=self.profile.timeout_seconds * 1000,
                        )
                        await page.wait_for_timeout(2500)
                        document = await page.content()
                    except Exception:
                        await page.close()
                        continue
                    finally:
                        if not page.is_closed():
                            await page.close()
                    direct = _relevant_results(
                        query, _deduplicate(self._results_from_document(document, query, search_url))
                    )
                    if direct:
                        return direct
                    candidates = parse_candidates(
                        document,
                        search_url,
                        query,
                        self.profile.hostname,
                        self.profile.article_url_patterns,
                        self.profile.max_results,
                    )
                    results: list[ResourceResult] = []
                    for candidate in candidates[: min(6, self.profile.max_results)]:
                        detail = await context.new_page()
                        try:
                            await detail.goto(
                                candidate.url,
                                wait_until="domcontentloaded",
                                timeout=self.profile.timeout_seconds * 1000,
                            )
                            await detail.wait_for_timeout(1200)
                            detail_html = await detail.content()
                            results.extend(
                                self._results_from_document(detail_html, candidate.title, candidate.url)
                            )
                        except Exception:
                            pass
                        finally:
                            await detail.close()
                    results = _relevant_results(query, _deduplicate(results))
                    if results:
                        return results
            finally:
                await context.close()
                await browser.close()
        return []

    async def search(self, query: str) -> list[ResourceResult]:
        http_error: Exception | None = None
        try:
            results = await self._search_http(query)
        except Exception as exc:
            http_error = exc
            results = []
        if results or not self.profile.browser_fallback:
            if http_error and not results:
                raise http_error
            return results
        browser_results = await self._search_browser(query)
        if browser_results:
            return browser_results
        if http_error:
            raise http_error
        return []


def _deduplicate(results: list[ResourceResult]) -> list[ResourceResult]:
    unique: dict[str, ResourceResult] = {}
    for item in results:
        unique.setdefault(item.share_url, item)
    return list(unique.values())


def jpmom_profile(
    base_url: str = "",
    cookie: str = "",
    timeout_seconds: int = 30,
) -> HeuristicSiteProfile:
    return HeuristicSiteProfile(
        name="jpmom",
        base_url=base_url,
        search_templates=("?s={query}",),
        article_url_patterns=(r"/\d+\.html(?:$|[?#])",),
        cookie=cookie,
        timeout_seconds=timeout_seconds,
        browser_fallback=True,
    )


def houtupan_profile(
    base_url: str = "",
    cookie: str = "",
    timeout_seconds: int = 30,
) -> HeuristicSiteProfile:
    return HeuristicSiteProfile(
        name="houtupan",
        base_url=base_url,
        search_templates=(
            "?s={query}",
            "search?keyword={query}",
            "search?q={query}",
            "search/{query}",
        ),
        article_url_patterns=(
            r"/\d+\.html(?:$|[?#])",
            r"/(?:post|article|detail|resource|movie|tv)/",
        ),
        cookie=cookie,
        timeout_seconds=timeout_seconds,
        browser_fallback=True,
    )
