from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


DEFAULT_LOCAL_WEBSITE_CONFIG_PATH = "data/websites.yaml"
DEFAULT_DOCKER_WEBSITE_CONFIG_PATH = "/data/websites.yaml"

_URL_CANDIDATE_RE = re.compile(
    r"https?://[^\s，,；;]+|(?<!@)\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
    r"(?::\d+)?(?:/[^\s，,；;]*)?"
)


@dataclass(frozen=True, slots=True)
class SourceSiteEntry:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class SourceSiteUpdate:
    added: tuple[SourceSiteEntry, ...] = ()
    existing: tuple[SourceSiteEntry, ...] = ()
    removed: tuple[SourceSiteEntry, ...] = ()
    errors: tuple[str, ...] = ()
    path: str = ""
    env_updated: bool = False


def discover_website_config_path(configured_path: str = "") -> str:
    """Find an existing website config when env is unset."""
    if configured_path:
        return configured_path
    for candidate in (
        DEFAULT_DOCKER_WEBSITE_CONFIG_PATH,
        DEFAULT_LOCAL_WEBSITE_CONFIG_PATH,
    ):
        if Path(candidate).exists():
            return candidate
    return ""


def writable_website_config_path(configured_path: str = "") -> str:
    """Choose where a chat command should create website config."""
    if configured_path:
        return configured_path
    data_root = Path("/data")
    if data_root.exists() and os.access(data_root, os.W_OK):
        return DEFAULT_DOCKER_WEBSITE_CONFIG_PATH
    return DEFAULT_LOCAL_WEBSITE_CONFIG_PATH


def extract_site_urls(text: str) -> tuple[str, ...]:
    return tuple(
        match.group(0).strip(" \t\r\n，,；;。")
        for match in _URL_CANDIDATE_RE.finditer(text or "")
    )


def normalize_site_url(value: str) -> str:
    text = (value or "").strip().strip(" \t\r\n，,；;。")
    if text and "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError(f"无效网址：{value}")
    if host == "pan.quark.cn":
        raise ValueError("夸克分享链接不是资源站网址")
    if _is_private_host(host):
        raise ValueError(f"不能添加本机、局域网或私有 IP：{host}")
    return text.rstrip("/")


def _site_name(url: str) -> str:
    return (urlparse(url).hostname or url).lower()


def _site_key(url: str) -> str:
    parsed = urlparse(normalize_site_url(url))
    path = (parsed.path or "").rstrip("/")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{(parsed.hostname or '').lower()}{port}{path}"


def _is_private_host(host: str) -> bool:
    cleaned = (host or "").lower().strip(".")
    if cleaned in {"localhost", "local"} or cleaned.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    return not ip.is_global


class WebsiteSourceStore:
    def __init__(self, path: str, env_path: str = ".env"):
        self.path = path
        self.env_path = env_path

    def list_sites(self) -> tuple[SourceSiteEntry, ...]:
        payload = self._read()
        entries: list[SourceSiteEntry] = []
        for item in self._simple_sites(payload):
            if not bool(item.get("enabled", True)):
                continue
            try:
                url = normalize_site_url(str(item.get("url") or ""))
            except ValueError:
                continue
            entries.append(SourceSiteEntry(_site_name(url), url))
        return tuple(entries)

    def add_from_text(self, text: str) -> SourceSiteUpdate:
        urls = extract_site_urls(text)
        if not urls:
            return SourceSiteUpdate(
                errors=("请发送：配置资源站 https://example.com",),
                path=self.path,
            )
        return self.add(urls)

    def add(self, urls: tuple[str, ...] | list[str]) -> SourceSiteUpdate:
        payload = self._read()
        sites = self._simple_sites(payload)
        existing_by_key: dict[str, dict] = {}
        for item in sites:
            try:
                existing_by_key[_site_key(str(item.get("url") or ""))] = item
            except ValueError:
                continue

        added: list[SourceSiteEntry] = []
        existing: list[SourceSiteEntry] = []
        errors: list[str] = []
        for raw in urls:
            try:
                url = normalize_site_url(raw)
                key = _site_key(url)
            except ValueError as exc:
                errors.append(str(exc))
                continue

            entry = SourceSiteEntry(_site_name(url), url)
            if key in existing_by_key:
                existing.append(entry)
                continue
            item = {
                "name": entry.name,
                "enabled": True,
                "authorized": True,
                "url": entry.url,
            }
            sites.append(item)
            existing_by_key[key] = item
            added.append(entry)

        if added:
            payload["simple_sites"] = sites
            self._write(payload)
        env_updated = self._sync_env_path() if added else False
        return SourceSiteUpdate(
            tuple(added),
            tuple(existing),
            (),
            tuple(errors),
            self.path,
            env_updated,
        )

    def remove_from_text(self, text: str) -> SourceSiteUpdate:
        urls = extract_site_urls(text)
        if not urls and text.strip():
            urls = (text.strip(),)
        if not urls:
            return SourceSiteUpdate(
                errors=("请发送：删除资源站 https://example.com",),
                path=self.path,
            )
        return self.remove(urls)

    def remove(self, urls: tuple[str, ...] | list[str]) -> SourceSiteUpdate:
        payload = self._read()
        sites = self._simple_sites(payload)
        targets: set[str] = set()
        errors: list[str] = []
        for raw in urls:
            try:
                targets.add(_site_key(raw))
            except ValueError as exc:
                errors.append(str(exc))

        kept: list[dict] = []
        removed: list[SourceSiteEntry] = []
        for item in sites:
            url = str(item.get("url") or "")
            try:
                key = _site_key(url)
                entry = SourceSiteEntry(_site_name(url), normalize_site_url(url))
            except ValueError:
                kept.append(item)
                continue
            if key in targets:
                removed.append(entry)
            else:
                kept.append(item)

        if removed:
            payload["simple_sites"] = kept
            self._write(payload)
        return SourceSiteUpdate(removed=tuple(removed), errors=tuple(errors), path=self.path)

    def clear(self) -> SourceSiteUpdate:
        payload = self._read()
        removed = self.list_sites()
        if removed:
            payload["simple_sites"] = []
            self._write(payload)
        return SourceSiteUpdate(removed=removed, path=self.path)

    def _read(self) -> dict:
        file_path = Path(self.path)
        if not file_path.exists():
            return {"simple_sites": [], "websites": []}
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"网站配置必须是 YAML 对象：{self.path}")
        raw.setdefault("simple_sites", [])
        raw.setdefault("websites", [])
        if not isinstance(raw["simple_sites"], list):
            raise ValueError("simple_sites 必须是数组")
        if not isinstance(raw["websites"], list):
            raise ValueError("websites 必须是数组")
        return raw

    def _write(self, payload: dict) -> None:
        file_path = Path(self.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _sync_env_path(self) -> bool:
        env_file = Path(self.env_path)
        if not env_file.exists():
            return False
        lines = env_file.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        found = False
        for line in lines:
            if line.startswith("WEBSITE_CONFIG_PATH="):
                out.append(f"WEBSITE_CONFIG_PATH={self.path}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"WEBSITE_CONFIG_PATH={self.path}")
        env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True

    @staticmethod
    def _simple_sites(payload: dict) -> list[dict]:
        return [
            item for item in payload.get("simple_sites", []) if isinstance(item, dict)
        ]
