from __future__ import annotations

import os
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

_PLACEHOLDER_MARKERS = ("__FILL_", "【请填写", "<FILL_", "YOUR_")


def _clean(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    upper = text.upper()
    if any(marker.upper() in upper for marker in _PLACEHOLDER_MARKERS):
        return ""
    return text


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


@dataclass(frozen=True, slots=True)
class WebsiteSelectors:
    result_item: str
    title: str
    detail_url: str = ""
    detail_url_attribute: str = "href"
    quality: str = ""
    size: str = ""
    share_url: str = ""
    share_url_attribute: str = "href"


@dataclass(frozen=True, slots=True)
class WebsiteDetail:
    share_url_selector: str = ""
    share_url_attribute: str = "href"
    share_url_regex: str = r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s\"'<>]*"


@dataclass(frozen=True, slots=True)
class WebsiteSearch:
    url: str
    method: str = "GET"
    query_param: str = "q"
    extra_params: dict[str, str] = field(default_factory=dict)
    input_selector: str = ""
    submit_selector: str = ""
    result_wait_selector: str = ""


@dataclass(frozen=True, slots=True)
class WebsiteSourceConfig:
    name: str
    enabled: bool
    authorized: bool
    mode: str
    allowed_domains: tuple[str, ...]
    search: WebsiteSearch
    selectors: WebsiteSelectors
    detail: WebsiteDetail
    headers: dict[str, str]
    cookie_env: str
    storage_state_path: str
    timeout_seconds: int
    max_results: int
    detail_concurrency: int
    request_delay_seconds: float
    browser_headless: bool

    @property
    def provider_name(self) -> str:
        return f"website:{self.name}"

    def cookie_value(self) -> str:
        if not self.cookie_env:
            return ""
        return os.getenv(self.cookie_env, "").strip()


@dataclass(frozen=True, slots=True)
class SimpleSiteSourceConfig:
    name: str
    enabled: bool
    authorized: bool
    url: str
    search_templates: tuple[str, ...]
    article_url_patterns: tuple[str, ...]
    cookie_env: str = ""
    timeout_seconds: int = 30
    max_results: int = 12
    detail_concurrency: int = 3
    request_delay_seconds: float = 0.35
    browser_fallback: bool = True

    def cookie_value(self) -> str:
        if not self.cookie_env:
            return ""
        return os.getenv(self.cookie_env, "").strip()


@dataclass(frozen=True, slots=True)
class WebsiteConfigReport:
    sources: tuple[WebsiteSourceConfig | SimpleSiteSourceConfig, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return bool(self.sources) and not self.errors


def _domain(value: str) -> str:
    cleaned = value.strip().lower().lstrip(".")
    if "://" in cleaned:
        cleaned = (urlparse(cleaned).hostname or "").lower()
    return cleaned


def _site_url(value: str) -> str:
    text = _clean(value)
    if text and "://" not in text:
        text = f"https://{text}"
    return text.rstrip("/")


def _site_name(url: str, fallback: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host or fallback


def _is_obvious_private_host(hostname: str) -> bool:
    host = (hostname or "").lower().strip(".")
    if host in {"localhost", "local"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def _as_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        clean_key = _clean(key)
        clean_value = _clean(item)
        if clean_key and clean_value:
            result[clean_key] = clean_value
    return result


def load_website_configs(path: str) -> WebsiteConfigReport:
    file_path = Path(path)
    if not path:
        return WebsiteConfigReport((), (), ())
    if not file_path.exists():
        return WebsiteConfigReport((), (f"网站配置文件不存在：{path}",), ())

    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return WebsiteConfigReport((), (f"网站配置 YAML 解析失败：{exc}",), ())

    entries = raw.get("websites", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        return WebsiteConfigReport((), ("websites 必须是数组",), ())
    simple_entries = raw.get("simple_sites", []) if isinstance(raw, dict) else []
    if not isinstance(simple_entries, list):
        return WebsiteConfigReport((), ("simple_sites 必须是数组",), ())

    sources: list[WebsiteSourceConfig | SimpleSiteSourceConfig] = []
    errors: list[str] = []
    warnings: list[str] = []

    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {index} 个网站配置必须是对象")
            continue
        if not _bool(item.get("enabled"), False):
            continue

        name = _clean(item.get("name")) or f"site-{index}"
        prefix = f"网站 {name}"
        authorized = _bool(item.get("authorized"), False)
        if not authorized:
            errors.append(f"{prefix}：authorized 必须明确设置为 true")
            continue

        mode = _clean(item.get("mode"), "html").lower() or "html"
        if mode not in {"html", "browser"}:
            errors.append(f"{prefix}：mode 只支持 html 或 browser")
            continue

        domains_raw = item.get("allowed_domains", [])
        domains = tuple(
            domain for domain in (_domain(str(value)) for value in domains_raw if value) if domain
        ) if isinstance(domains_raw, list) else ()
        if not domains:
            errors.append(f"{prefix}：allowed_domains 至少填写一个域名")
            continue

        search_raw = item.get("search") if isinstance(item.get("search"), dict) else {}
        selectors_raw = item.get("selectors") if isinstance(item.get("selectors"), dict) else {}
        detail_raw = item.get("detail") if isinstance(item.get("detail"), dict) else {}

        search_url = _clean(search_raw.get("url"))
        method = (_clean(search_raw.get("method"), "GET") or "GET").upper()
        if method not in {"GET", "POST"}:
            errors.append(f"{prefix}：search.method 只支持 GET 或 POST")
            continue

        result_item = _clean(selectors_raw.get("result_item"))
        title_selector = _clean(selectors_raw.get("title"))
        if not search_url:
            errors.append(f"{prefix}：search.url 未填写")
        if not result_item:
            errors.append(f"{prefix}：selectors.result_item 未填写")
        if not title_selector:
            errors.append(f"{prefix}：selectors.title 未填写")
        if not search_url or not result_item or not title_selector:
            continue

        parsed_host = (urlparse(search_url).hostname or "").lower()
        if parsed_host and not any(parsed_host == d or parsed_host.endswith(f".{d}") for d in domains):
            errors.append(f"{prefix}：search.url 域名不在 allowed_domains 中")
            continue

        if mode == "browser" and not (
            "{query}" in search_url
            or (_clean(search_raw.get("input_selector")) and _clean(search_raw.get("submit_selector")))
        ):
            errors.append(
                f"{prefix}：browser 模式需在 search.url 使用 {{query}}，或同时填写 input_selector 和 submit_selector"
            )
            continue

        cookie_env = _clean(item.get("cookie_env"))
        if cookie_env and not cookie_env.replace("_", "").isalnum():
            errors.append(f"{prefix}：cookie_env 只能填写环境变量名")
            continue

        headers = _as_string_dict(item.get("headers"))
        storage_state_path = _clean(item.get("storage_state_path"))
        if storage_state_path and not storage_state_path.startswith("/data/"):
            warnings.append(f"{prefix}：storage_state_path 建议放在 /data 下以便持久化")

        source = WebsiteSourceConfig(
            name=name,
            enabled=True,
            authorized=True,
            mode=mode,
            allowed_domains=domains,
            search=WebsiteSearch(
                url=search_url,
                method=method,
                query_param=_clean(search_raw.get("query_param"), "q") or "q",
                extra_params=_as_string_dict(search_raw.get("extra_params")),
                input_selector=_clean(search_raw.get("input_selector")),
                submit_selector=_clean(search_raw.get("submit_selector")),
                result_wait_selector=_clean(search_raw.get("result_wait_selector")),
            ),
            selectors=WebsiteSelectors(
                result_item=result_item,
                title=title_selector,
                detail_url=_clean(selectors_raw.get("detail_url")),
                detail_url_attribute=_clean(selectors_raw.get("detail_url_attribute"), "href") or "href",
                quality=_clean(selectors_raw.get("quality")),
                size=_clean(selectors_raw.get("size")),
                share_url=_clean(selectors_raw.get("share_url")),
                share_url_attribute=_clean(selectors_raw.get("share_url_attribute"), "href") or "href",
            ),
            detail=WebsiteDetail(
                share_url_selector=_clean(detail_raw.get("share_url_selector")),
                share_url_attribute=_clean(detail_raw.get("share_url_attribute"), "href") or "href",
                share_url_regex=_clean(detail_raw.get("share_url_regex"))
                or r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s\"'<>]*",
            ),
            headers=headers,
            cookie_env=cookie_env,
            storage_state_path=storage_state_path,
            timeout_seconds=_int(item.get("timeout_seconds"), 20, 5, 90),
            max_results=_int(item.get("max_results"), 10, 1, 50),
            detail_concurrency=_int(item.get("detail_concurrency"), 3, 1, 10),
            request_delay_seconds=_float(item.get("request_delay_seconds"), 0.5, 0.0, 10.0),
            browser_headless=_bool(item.get("browser_headless"), True),
        )
        sources.append(source)

    for index, item in enumerate(simple_entries, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {index} 个简化网站配置必须是对象")
            continue
        if not _bool(item.get("enabled"), False):
            continue
        url = _site_url(item.get("url"))
        name = _clean(item.get("name")) or _site_name(url, f"simple-site-{index}")
        prefix = f"简化网站 {name}"
        if not _bool(item.get("authorized"), False):
            errors.append(f"{prefix}：authorized 必须明确设置为 true")
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            errors.append(f"{prefix}：url 必须是有效网址")
            continue
        if _is_obvious_private_host(parsed.hostname):
            errors.append(f"{prefix}：url 不能是本机、局域网或私有 IP")
            continue
        cookie_env = _clean(item.get("cookie_env"))
        if cookie_env and not cookie_env.replace("_", "").isalnum():
            errors.append(f"{prefix}：cookie_env 只能填写环境变量名")
            continue
        templates_raw = item.get("search_templates")
        templates = tuple(
            _clean(value) for value in templates_raw if _clean(value)
        ) if isinstance(templates_raw, list) else ()
        if not templates:
            templates = (
                "?s={query}",
                "search?keyword={query}",
                "search?q={query}",
                "search/{query}",
            )
        patterns_raw = item.get("article_url_patterns")
        patterns = tuple(
            _clean(value) for value in patterns_raw if _clean(value)
        ) if isinstance(patterns_raw, list) else ()
        if not patterns:
            patterns = (
                r"/\d+\.html(?:$|[?#])",
                r"/(?:post|article|detail|resource|movie|tv)/",
            )
        sources.append(
            SimpleSiteSourceConfig(
                name=name,
                enabled=True,
                authorized=True,
                url=url,
                search_templates=templates,
                article_url_patterns=patterns,
                cookie_env=cookie_env,
                timeout_seconds=_int(item.get("timeout_seconds"), 30, 5, 90),
                max_results=_int(item.get("max_results"), 12, 1, 50),
                detail_concurrency=_int(item.get("detail_concurrency"), 3, 1, 10),
                request_delay_seconds=_float(item.get("request_delay_seconds"), 0.35, 0.0, 10.0),
                browser_fallback=_bool(item.get("browser_fallback"), True),
            )
        )

    if path and not sources and not errors:
        warnings.append("网站配置文件中没有启用的网站")
    return WebsiteConfigReport(tuple(sources), tuple(errors), tuple(warnings))
