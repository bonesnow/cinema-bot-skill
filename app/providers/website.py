from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.models import ResourceResult

from .base import ResourceProvider
from .website_config import WebsiteSourceConfig

QUARK_SHARE_RE = re.compile(r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s\"'<>]*", re.I)


class WebsiteSecurityError(RuntimeError):
    pass


def _host_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = (host or "").lower().strip(".")
    return any(normalized == domain or normalized.endswith(f".{domain}") for domain in allowed_domains)


def _is_public_host(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for entry in addresses:
        address = entry[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def validate_site_url(url: str, allowed_domains: tuple[str, ...], allow_private_hosts: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WebsiteSecurityError("网站 URL 只允许 http/https")
    host = parsed.hostname or ""
    if not _host_allowed(host, allowed_domains):
        raise WebsiteSecurityError(f"目标域名不在 allowed_domains 中：{host}")
    if not allow_private_hosts and not _is_public_host(host):
        raise WebsiteSecurityError(f"拒绝访问本地或内网地址：{host}")
    return url


def _extract_value(node: Tag, selector: str, attribute: str = "") -> str:
    if not selector:
        return ""
    selected = node.select_one(selector)
    if selected is None:
        return ""
    if attribute and attribute.lower() != "text":
        return str(selected.get(attribute) or "").strip()
    return selected.get_text(" ", strip=True)


def _extract_quark_url(text: str, regex: str = "") -> str:
    if not text:
        return ""
    pattern = re.compile(regex, re.I) if regex else QUARK_SHARE_RE
    match = pattern.search(text)
    if not match:
        return ""
    value = match.group(0).rstrip("，。；;)]}>")
    return value if QUARK_SHARE_RE.match(value) else ""


def _build_search_url(config: WebsiteSourceConfig, query: str) -> str:
    if "{query}" in config.search.url:
        return config.search.url.replace("{query}", quote_plus(query))
    return config.search.url


def _parse_cookie_header(value: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, cookie_value = part.split("=", 1)
        name = name.strip()
        if name:
            cookies[name] = cookie_value.strip()
    return cookies


class WebsiteProvider(ResourceProvider):
    def __init__(self, config: WebsiteSourceConfig, allow_private_hosts: bool = False):
        self.config = config
        self.name = config.provider_name
        self.allow_private_hosts = allow_private_hosts

    async def search(self, query: str) -> list[ResourceResult]:
        if self.config.mode == "browser":
            return await self._search_browser(query)
        return await self._search_html(query)

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        headers.update(self.config.headers)
        cookie = self.config.cookie_value()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    async def _request_html(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        validate_site_url(url, self.config.allowed_domains, self.allow_private_hosts)
        response = await client.request(method, url, params=params, data=data)
        response.raise_for_status()
        validate_site_url(str(response.url), self.config.allowed_domains, self.allow_private_hosts)
        content_type = response.headers.get("content-type", "")
        if content_type and not any(value in content_type.lower() for value in ("text", "html", "json")):
            raise RuntimeError(f"不支持的响应类型：{content_type}")
        return response.text

    async def _search_html(self, query: str) -> list[ResourceResult]:
        url = _build_search_url(self.config, query)
        params = dict(self.config.search.extra_params)
        data: dict[str, str] | None = None
        if "{query}" not in self.config.search.url:
            if self.config.search.method == "POST":
                data = {**params, self.config.search.query_param: query}
                params = {}
            else:
                params[self.config.search.query_param] = query

        limits = httpx.Limits(max_connections=max(4, self.config.detail_concurrency + 1))
        async with httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            headers=self._headers(),
            limits=limits,
        ) as client:
            html = await self._request_html(
                client,
                self.config.search.method,
                url,
                params=params or None,
                data=data,
            )
            soup = BeautifulSoup(html, "html.parser")
            nodes = soup.select(self.config.selectors.result_item)[: self.config.max_results]
            candidates = [self._candidate_from_node(node, url) for node in nodes]
            return await self._resolve_html_details(client, candidates)

    def _candidate_from_node(self, node: Tag, page_url: str) -> dict[str, str]:
        title = _extract_value(node, self.config.selectors.title)
        quality = _extract_value(node, self.config.selectors.quality)
        size = _extract_value(node, self.config.selectors.size)
        direct_share = _extract_value(
            node,
            self.config.selectors.share_url,
            self.config.selectors.share_url_attribute,
        )
        share_url = _extract_quark_url(direct_share) or _extract_quark_url(str(node))
        detail_url_value = _extract_value(
            node,
            self.config.selectors.detail_url,
            self.config.selectors.detail_url_attribute,
        )
        detail_url = urljoin(page_url, detail_url_value) if detail_url_value else ""
        return {
            "title": title,
            "quality": quality,
            "size": size,
            "share_url": share_url,
            "detail_url": detail_url,
        }

    async def _resolve_html_details(
        self,
        client: httpx.AsyncClient,
        candidates: list[dict[str, str]],
    ) -> list[ResourceResult]:
        semaphore = asyncio.Semaphore(self.config.detail_concurrency)

        async def resolve(candidate: dict[str, str]) -> ResourceResult | None:
            share_url = candidate["share_url"]
            detail_url = candidate["detail_url"]
            if not share_url and detail_url:
                async with semaphore:
                    if self.config.request_delay_seconds:
                        await asyncio.sleep(self.config.request_delay_seconds)
                    detail_html = await self._request_html(client, "GET", detail_url)
                detail_soup = BeautifulSoup(detail_html, "html.parser")
                selected_value = ""
                if self.config.detail.share_url_selector:
                    selected = detail_soup.select_one(self.config.detail.share_url_selector)
                    if selected:
                        selected_value = str(
                            selected.get(self.config.detail.share_url_attribute)
                            or selected.get_text(" ", strip=True)
                        )
                share_url = (
                    _extract_quark_url(selected_value, self.config.detail.share_url_regex)
                    or _extract_quark_url(detail_html, self.config.detail.share_url_regex)
                )
            if not candidate["title"] or not share_url:
                return None
            return ResourceResult(
                title=candidate["title"],
                share_url=share_url,
                source="website",
                quality=candidate["quality"],
                size=candidate["size"],
                provider=self.config.name,
                extra={"detail_url": detail_url, "mode": "html"},
            )

        outcomes = await asyncio.gather(*(resolve(item) for item in candidates), return_exceptions=True)
        results: list[ResourceResult] = []
        for outcome in outcomes:
            if isinstance(outcome, ResourceResult):
                results.append(outcome)
        return results

    async def _search_browser(self, query: str) -> list[ResourceResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("browser 网站需要安装 playwright") from exc

        search_url = _build_search_url(self.config, query)
        validate_site_url(search_url, self.config.allowed_domains, self.allow_private_hosts)
        storage_state = self.config.storage_state_path
        storage_option: str | None = storage_state if storage_state and Path(storage_state).exists() else None

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.config.browser_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                extra_http_headers=self.config.headers,
                storage_state=storage_option,
            )
            cookie_value = self.config.cookie_value()
            if cookie_value:
                cookies = []
                for domain in self.config.allowed_domains:
                    for name, value in _parse_cookie_header(cookie_value).items():
                        cookies.append(
                            {
                                "name": name,
                                "value": value,
                                "domain": f".{domain}",
                                "path": "/",
                                "secure": True,
                            }
                        )
                if cookies:
                    await context.add_cookies(cookies)

            page = await context.new_page()
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=self.config.timeout_seconds * 1000)
                validate_site_url(page.url, self.config.allowed_domains, self.allow_private_hosts)
                if "{query}" not in self.config.search.url:
                    await page.locator(self.config.search.input_selector).fill(query)
                    await page.locator(self.config.search.submit_selector).click()
                wait_selector = self.config.search.result_wait_selector or self.config.selectors.result_item
                await page.wait_for_selector(wait_selector, timeout=self.config.timeout_seconds * 1000)
                locators = page.locator(self.config.selectors.result_item)
                count = min(await locators.count(), self.config.max_results)
                candidates: list[dict[str, str]] = []
                for index in range(count):
                    node = locators.nth(index)
                    title = await self._browser_value(node, self.config.selectors.title)
                    quality = await self._browser_value(node, self.config.selectors.quality)
                    size = await self._browser_value(node, self.config.selectors.size)
                    direct_share = await self._browser_value(
                        node,
                        self.config.selectors.share_url,
                        self.config.selectors.share_url_attribute,
                    )
                    node_html = await node.evaluate("el => el.outerHTML")
                    detail_value = await self._browser_value(
                        node,
                        self.config.selectors.detail_url,
                        self.config.selectors.detail_url_attribute,
                    )
                    candidates.append(
                        {
                            "title": title,
                            "quality": quality,
                            "size": size,
                            "share_url": _extract_quark_url(direct_share) or _extract_quark_url(node_html),
                            "detail_url": urljoin(page.url, detail_value) if detail_value else "",
                        }
                    )

                results: list[ResourceResult] = []
                for candidate in candidates:
                    share_url = candidate["share_url"]
                    if not share_url and candidate["detail_url"]:
                        validate_site_url(candidate["detail_url"], self.config.allowed_domains, self.allow_private_hosts)
                        detail_page = await context.new_page()
                        try:
                            await detail_page.goto(
                                candidate["detail_url"],
                                wait_until="domcontentloaded",
                                timeout=self.config.timeout_seconds * 1000,
                            )
                            validate_site_url(detail_page.url, self.config.allowed_domains, self.allow_private_hosts)
                            if self.config.detail.share_url_selector:
                                locator = detail_page.locator(self.config.detail.share_url_selector).first
                                value = await self._browser_locator_value(
                                    locator,
                                    self.config.detail.share_url_attribute,
                                )
                                share_url = _extract_quark_url(value, self.config.detail.share_url_regex)
                            if not share_url:
                                share_url = _extract_quark_url(
                                    await detail_page.content(),
                                    self.config.detail.share_url_regex,
                                )
                        finally:
                            await detail_page.close()
                    if candidate["title"] and share_url:
                        results.append(
                            ResourceResult(
                                title=candidate["title"],
                                share_url=share_url,
                                source="website",
                                quality=candidate["quality"],
                                size=candidate["size"],
                                provider=self.config.name,
                                extra={"detail_url": candidate["detail_url"], "mode": "browser"},
                            )
                        )
                    if self.config.request_delay_seconds:
                        await asyncio.sleep(self.config.request_delay_seconds)

                if storage_state:
                    Path(storage_state).parent.mkdir(parents=True, exist_ok=True)
                    await context.storage_state(path=storage_state)
                return results
            finally:
                await context.close()
                await browser.close()

    async def _browser_value(self, node: Any, selector: str, attribute: str = "") -> str:
        if not selector:
            return ""
        locator = node.locator(selector).first
        return await self._browser_locator_value(locator, attribute)

    async def _browser_locator_value(self, locator: Any, attribute: str = "") -> str:
        try:
            if await locator.count() == 0:
                return ""
            if attribute and attribute.lower() != "text":
                return str(await locator.get_attribute(attribute) or "").strip()
            return str(await locator.inner_text() or "").strip()
        except Exception:
            return ""
