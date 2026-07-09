from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .config import Settings
from .models import ResourceResult
from .library import LibraryManager, MetadataScraper, parse_media_info
from .providers import (
    AuthorizedJsonProvider,
    LocalCatalogProvider,
    PanHubProvider,
    HeuristicSiteProvider,
    jpmom_profile,
    houtupan_profile,
    ResourceProvider,
    load_website_providers,
)
from .quark import QuarkClient, QuarkFileItem
from .quark_auth import QuarkAuthStore, QuarkLoginSession, QuarkLoginStatus, QuarkQRLoginManager
from .scoring import score_resource
from .source_sites import SourceSiteUpdate, WebsiteSourceStore, writable_website_config_path

QUARK_URL_RE = re.compile(r"https?://pan\.quark\.cn/s/[A-Za-z0-9_-]+[^\s]*")
PASSCODE_RE = re.compile(r"(?:提取码|密码|passcode)\s*[:：]?\s*([A-Za-z0-9]{2,12})", re.I)
QUARK_LOGIN_COMMANDS = {
    "夸克登录", "登录夸克", "夸克扫码登录", "扫码登录夸克",
    "/quark-login", "/quark_login",
}
ORGANIZE_ALL_COMMANDS = {"整理网盘", "整理媒体库", "整理夸克网盘", "/organize-all", "/organize_all"}
ORGANIZE_RE = re.compile(r"^(?:整理|归档)\s*[:：]?\s*(.+)$", re.I)
SCRAPE_RE = re.compile(r"^(?:刮削|识别信息|查询信息)\s*[:：]?\s*(.+)$", re.I)
SOURCE_ADD_RE = re.compile(r"^(?:配置|添加|新增|加入)(?:资源站|资源网站|网站)\s*[:：]?\s*(.+)$", re.I)
SOURCE_REMOVE_RE = re.compile(r"^(?:删除|移除)(?:资源站|资源网站|网站)\s*[:：]?\s*(.+)$", re.I)
SOURCE_LIST_COMMANDS = {"资源站列表", "资源网站列表", "网站列表", "查看资源站", "查看资源网站"}
SOURCE_CLEAR_COMMANDS = {"清空资源站", "清空资源网站", "清空网站"}

QUARK_LOGOUT_COMMANDS = {
    "退出夸克", "夸克退出", "清除夸克登录", "重新登录夸克",
    "/quark-logout", "/quark_logout",
}

INTENT_PATTERNS = (
    re.compile(r"^(?:/search|搜索|搜一下|帮我找|帮我搜)\s*[:：]?\s*(.+)$", re.I),
    re.compile(r"^(?:我要看|我想看|想看)\s*[:：]?\s*(.+)$", re.I),
)
QUALITY_HINT_RE = re.compile(
    r"(?i)(?:\b(?:2160p|1080p|1080i|720p|480p|4k|uhd|remux|bluray|web[- .]?dl|webrip|hdr10\+?|hdr|dolby[ .]?vision|dv|atmos|中字|中英|双语)\b)"
)
PUNCT_RE = re.compile(r"[\s._\-—:：·,，。!！?？()（）\[\]【】]+")


@dataclass(slots=True)
class ParsedIntent:
    action: str
    query: str = ""
    share_url: str = ""
    passcode: str = ""


def parse_intent(text: str) -> ParsedIntent:
    cleaned = text.strip()
    if not cleaned:
        return ParsedIntent("help")
    if cleaned.lower() in {"help", "/help", "帮助", "菜单"}:
        return ParsedIntent("help")
    if cleaned.lower() in {"status", "/status", "状态"}:
        return ParsedIntent("status")
    if cleaned.lower() in QUARK_LOGIN_COMMANDS:
        return ParsedIntent("quark_login")
    if cleaned.lower() in QUARK_LOGOUT_COMMANDS:
        return ParsedIntent("quark_logout")
    if cleaned.lower() in ORGANIZE_ALL_COMMANDS:
        return ParsedIntent("organize_all")
    source_add_match = SOURCE_ADD_RE.match(cleaned)
    if source_add_match:
        return ParsedIntent("source_add", query=source_add_match.group(1).strip(" ，。"))
    source_remove_match = SOURCE_REMOVE_RE.match(cleaned)
    if source_remove_match:
        return ParsedIntent("source_remove", query=source_remove_match.group(1).strip(" ，。"))
    if cleaned in SOURCE_LIST_COMMANDS:
        return ParsedIntent("source_list")
    if cleaned in SOURCE_CLEAR_COMMANDS:
        return ParsedIntent("source_clear")
    organize_match = ORGANIZE_RE.match(cleaned)
    if organize_match:
        return ParsedIntent("organize", query=organize_match.group(1).strip(" ，。"))
    scrape_match = SCRAPE_RE.match(cleaned)
    if scrape_match:
        return ParsedIntent("scrape", query=scrape_match.group(1).strip(" ，。"))

    url_match = QUARK_URL_RE.search(cleaned)
    if url_match:
        passcode_match = PASSCODE_RE.search(cleaned)
        return ParsedIntent(
            "save",
            share_url=url_match.group(0).rstrip("，。；;"),
            passcode=passcode_match.group(1) if passcode_match else "",
        )

    for pattern in INTENT_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return ParsedIntent("search", query=match.group(1).strip(" ，。"))

    if len(cleaned) <= 80 and "http" not in cleaned.lower():
        return ParsedIntent("search", query=cleaned)
    return ParsedIntent("help")


def title_only_query(query: str) -> str:
    """Remove quality preferences before checking whether the title already exists."""
    stripped = QUALITY_HINT_RE.sub(" ", query)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ，。")
    return stripped or query.strip()


def normalize_title(text: str) -> str:
    text = QUALITY_HINT_RE.sub(" ", text).lower()
    return PUNCT_RE.sub("", text)


def _title_relevance(query: str, candidate: str) -> float:
    q = normalize_title(title_only_query(query))
    c = normalize_title(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c:
        return 0.95
    if c in q:
        return 0.85
    return SequenceMatcher(None, q, c).ratio()


def _format_bytes(size: int) -> str:
    if size <= 0:
        return "未标注"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"



def _parse_size_value(size: str) -> float:
    match = re.search(r"(?i)([0-9]+(?:\.[0-9]+)?)\s*(tb|gb|mb|kb|b)?", size or "")
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    factors = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
    return value * factors[unit]

def _disk_quality_score(item: QuarkFileItem) -> int:
    virtual = ResourceResult(title=item.name, share_url="", size=str(item.size))
    return score_resource(virtual)


class MediaService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers: list[ResourceProvider] = [
            AuthorizedJsonProvider(url, settings.provider_api_token)
            for url in settings.provider_api_urls
        ]
        if settings.panhub_base_url:
            self.providers.append(
                PanHubProvider(
                    settings.panhub_base_url,
                    settings.panhub_cookie,
                    concurrency=settings.panhub_concurrency,
                    timeout_seconds=settings.panhub_timeout,
                )
            )
        if settings.jpmom_enabled and settings.jpmom_base_url:
            self.providers.append(
                HeuristicSiteProvider(
                    jpmom_profile(
                        settings.jpmom_base_url,
                        settings.jpmom_cookie,
                        settings.jpmom_timeout,
                    )
                )
            )
        if settings.houtupan_enabled and settings.houtupan_base_url:
            self.providers.append(
                HeuristicSiteProvider(
                    houtupan_profile(
                        settings.houtupan_base_url,
                        settings.houtupan_cookie,
                        settings.houtupan_timeout,
                    )
                )
            )
        if settings.local_catalog_path:
            self.providers.append(LocalCatalogProvider(settings.local_catalog_path))
        self.website_report = None
        self._website_providers: list[ResourceProvider] = []
        if settings.website_config_path:
            self._replace_website_providers(settings.website_config_path)
        self.quark_auth = QuarkAuthStore(
            settings.quark_auth_file,
            fallback_cookie=settings.quark_cookie,
        )
        self.quark_login = QuarkQRLoginManager(
            self.quark_auth,
            timeout=settings.quark_qr_timeout,
        )
        self.quark = QuarkClient(
            settings.quark_cookie,
            settings.quark_target_fid,
            settings.quark_passcode,
            auth_store=self.quark_auth,
        )
        self.metadata = MetadataScraper(settings.omdb_api_key, settings.metadata_cache_path)
        self.library = LibraryManager(
            self.quark,
            root_name=settings.library_root_name,
            root_fid=settings.library_root_fid,
            genre_folders=settings.library_genre_folders,
            keep_scene_names=settings.library_keep_scene_names,
            metadata=self.metadata,
        )
        self._title_locks: dict[str, asyncio.Lock] = {}

    async def handle(self, text: str) -> str:
        intent = parse_intent(text)
        if intent.action == "help":
            return self.help_text()
        if intent.action == "status":
            return self.status_text()
        if intent.action == "quark_login":
            session = await self.start_quark_login()
            return (
                "请使用夸克 App 扫描二维码登录。当前渠道无法直接显示二维码时，"
                f"请打开此登录地址：\n{session.qr_url}"
            )
        if intent.action == "quark_logout":
            self.quark_auth.clear()
            return "✅ 已清除夸克扫码登录信息，请发送“夸克登录”重新扫码。"
        if intent.action == "source_add":
            return self._add_source_sites(intent.query)
        if intent.action == "source_list":
            return self._list_source_sites()
        if intent.action == "source_remove":
            return self._remove_source_sites(intent.query)
        if intent.action == "source_clear":
            return self._clear_source_sites()
        if intent.action == "save":
            return await self._save_direct(intent.share_url, intent.passcode)
        if intent.action == "organize":
            return await self._organize_existing(intent.query)
        if intent.action == "organize_all":
            return await self._organize_inbox()
        if intent.action == "scrape":
            return await self._scrape_metadata(intent.query)
        if intent.action == "search":
            return await self._search_drive_then_providers(intent.query)
        return self.help_text()

    def help_text(self) -> str:
        return (
            "可用指令：\n"
            "1. 我要看 星际穿越\n"
            "2. 搜索 流浪地球2 4K\n"
            "3. 直接发送夸克分享链接（可附提取码）\n"
            "4. 夸克登录（接收二维码并扫码）\n"
            "5. 退出夸克\n"
            "6. 整理 星际穿越（整理已有文件）\n"
            "7. 整理网盘（整理转存目标目录的顶层项目）\n"
            "8. 刮削 星际穿越（查看分类元数据）\n"
            "9. 配置资源站 https://example.com\n"
            "10. 资源站列表 / 删除资源站 https://example.com / 清空资源站\n"
            "11. 状态\n\n"
            "处理顺序：先查你的夸克网盘；没有才查询已配置的 PanHub/JPMOM/HouTuPan/资源网站/API/本地目录；"
            "多个结果自动选择画质评分最高的版本。转存成功后会自动整理为 Plex/Jellyfin/Infuse 兼容目录。"
        )

    def status_text(self) -> str:
        authenticated = self._quark_authenticated()
        method = "扫码登录" if self.quark_auth.has_scanned_login else ("环境变量 Cookie" if authenticated else "未登录")
        website_count = len(self.website_report.sources) if self.website_report else 0
        website_state = (
            f"{website_count} 个已启用"
            if not self.website_report or not self.website_report.errors
            else f"配置有 {len(self.website_report.errors)} 个错误"
        )
        return (
            f"资源源：{len(self.providers)} 个\n"
            f"网站配置：{website_state}\n"
            f"夸克登录：{'已登录' if authenticated else '未登录'}（{method}）\n"
            f"网盘优先检索：{'开启' if authenticated else '不可用，请发送“夸克登录”'}\n"
            f"目标目录 FID：{self.settings.quark_target_fid}\n"
            f"登录信息文件：{self.settings.quark_auth_file}\n"
            f"自动转存：{'开启' if self.settings.auto_save else '关闭'}\n"
            f"演练模式：{'开启' if self.settings.dry_run else '关闭'}\n"
            f"自动整理：{'开启' if self.settings.organize_after_save else '关闭'}\n"
            f"媒体库目录：{self.settings.library_root_name}"
            f"{'（固定 FID：' + self.settings.library_root_fid + '）' if self.settings.library_root_fid else '（自动创建）'}\n"
            f"类型刮削：{'OMDb' if self.settings.omdb_api_key else '未配置 OMDb，降级为其他'}"
        )

    def _website_store(self) -> WebsiteSourceStore:
        return WebsiteSourceStore(writable_website_config_path(self.settings.website_config_path))

    def _replace_website_providers(self, path: str) -> None:
        self.providers = [
            provider for provider in self.providers if provider not in self._website_providers
        ]
        website_providers, self.website_report = load_website_providers(
            path,
            allow_private_hosts=self.settings.website_allow_private_hosts,
        )
        self._website_providers = website_providers
        self.providers.extend(website_providers)

    def _reload_source_sites(self, store: WebsiteSourceStore) -> None:
        self._replace_website_providers(store.path)

    def _add_source_sites(self, text: str) -> str:
        store = self._website_store()
        update = store.add_from_text(text)
        if update.added:
            self._reload_source_sites(store)
        return self._format_source_update(update, "添加")

    def _list_source_sites(self) -> str:
        store = self._website_store()
        sites = store.list_sites()
        if not sites:
            return "尚未配置对话添加的资源站。发送：配置资源站 https://example.com"
        lines = [f"已配置资源站（{len(sites)} 个）："]
        lines.extend(f"- {site.name}：{site.url}" for site in sites)
        lines.append(f"配置文件：{store.path}")
        return "\n".join(lines)

    def _remove_source_sites(self, text: str) -> str:
        store = self._website_store()
        update = store.remove_from_text(text)
        if update.removed:
            self._reload_source_sites(store)
        return self._format_source_update(update, "删除")

    def _clear_source_sites(self) -> str:
        store = self._website_store()
        update = store.clear()
        if update.removed:
            self._reload_source_sites(store)
        if not update.removed:
            return "对话添加的资源站已经是空的。"
        return f"✅ 已清空 {len(update.removed)} 个对话添加的资源站。"

    def _format_source_update(self, update: SourceSiteUpdate, action: str) -> str:
        lines: list[str] = []
        if update.added:
            lines.append(f"✅ 已添加资源站：{', '.join(site.name for site in update.added)}")
        if update.removed:
            lines.append(f"✅ 已删除资源站：{', '.join(site.name for site in update.removed)}")
        if update.existing:
            lines.append(f"ℹ️ 已存在：{', '.join(site.name for site in update.existing)}")
        if update.errors:
            lines.append("⚠️ 未处理：")
            lines.extend(f"- {error}" for error in update.errors)
        if not lines:
            lines.append(f"没有可{action}的资源站。")
        if update.added:
            lines.append(f"配置文件：{update.path}")
            if update.env_updated:
                lines.append("已同步 .env：WEBSITE_CONFIG_PATH")
            lines.append("之后可以直接发送：我要看 星际穿越")
        return "\n".join(lines)

    def _quark_authenticated(self) -> bool:
        value = getattr(self.quark, "is_authenticated", None)
        if value is not None:
            return bool(value)
        return bool(self.settings.quark_cookie)

    async def start_quark_login(self) -> QuarkLoginSession:
        return await self.quark_login.start()

    def quark_login_qr_png(self, session_id: str) -> bytes:
        return self.quark_login.qr_png(session_id)

    async def wait_quark_login(self, session_id: str) -> QuarkLoginStatus:
        return await self.quark_login.wait(session_id)

    async def _save_direct(self, share_url: str, passcode: str) -> str:
        if not self._quark_authenticated():
            return "❌ 夸克尚未登录，请先发送“夸克登录”并扫码。"
        if self.settings.dry_run:
            return f"演练模式：已识别夸克链接，不会实际转存。\n{share_url}"
        result = await self.quark.save_share(share_url, passcode)
        return await self._save_result_text(result, result.source_title or "夸克分享")

    async def _search_drive_then_providers(self, query: str) -> str:
        title_query = title_only_query(query)
        lock_key = normalize_title(title_query) or title_query.lower()
        lock = self._title_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            return await self._search_drive_then_providers_locked(query, title_query)

    async def _search_drive_then_providers_locked(self, query: str, title_query: str) -> str:
        drive_warning = ""

        if self._quark_authenticated():
            drive_result = await self.quark.search_files(title_query)
            if drive_result.ok:
                matches = [
                    item for item in drive_result.files
                    if _title_relevance(title_query, item.name) >= 0.55
                ]
                if matches:
                    matches.sort(
                        key=lambda item: (
                            _disk_quality_score(item),
                            _title_relevance(title_query, item.name),
                            item.size,
                        ),
                        reverse=True,
                    )
                    best = matches[0]
                    location = f"\n位置：{best.path}" if best.path else ""
                    kind = "文件夹" if best.is_dir else "文件"
                    return (
                        f"✅ 你的夸克网盘里已经有“{title_query}”，无需重复转存。\n"
                        f"最佳现有版本：{best.name}\n"
                        f"类型：{kind}｜大小：{_format_bytes(best.size)}｜匹配结果：{len(matches)} 个"
                        f"{location}"
                    )
            else:
                drive_warning = f"\n⚠️ 网盘检索异常：{drive_result.message}；已继续搜索资源源。"
        else:
            drive_warning = "\n⚠️ 夸克尚未登录，已跳过网盘检查；发送“夸克登录”可扫码登录。"

        if not self.providers:
            return (
                f"夸克网盘中没有找到“{title_query}”，且尚未配置资源源。\n"
                "请设置 WEBSITE_CONFIG_PATH、PROVIDER_API_URLS 或 LOCAL_CATALOG_PATH。"
                f"{drive_warning}"
            )

        searches = await asyncio.gather(
            *(provider.search(title_query) for provider in self.providers),
            return_exceptions=True,
        )
        results: list[ResourceResult] = []
        errors: list[str] = []
        for provider, outcome in zip(self.providers, searches):
            if isinstance(outcome, Exception):
                errors.append(f"{provider.name}: {outcome}")
            else:
                results.extend(outcome)

        # Deduplicate identical share links before ranking.
        unique: dict[str, ResourceResult] = {}
        for item in results:
            unique.setdefault(item.share_url, item)
        results = list(unique.values())

        relevant = [item for item in results if _title_relevance(title_query, item.title) >= 0.45]
        results = relevant

        if not results:
            suffix = f"\n部分资源源异常：{'；'.join(errors[:2])}" if errors else ""
            return f"网盘和已配置资源源中都没有找到“{title_query}”。{drive_warning}{suffix}"

        ranked = sorted(
            results,
            key=lambda item: (
                score_resource(item),
                _title_relevance(title_query, item.title),
                _parse_size_value(item.size),
            ),
            reverse=True,
        )
        best = ranked[0]
        score = score_resource(best)
        summary = (
            f"夸克网盘中未找到“{title_query}”。\n"
            f"资源源共找到 {len(ranked)} 个候选，已选择画质最佳版本：\n"
            f"{best.title}\n"
            f"质量：{best.quality or '未标注'}｜大小：{best.size or '未标注'}｜画质评分：{score}\n"
            f"来源：{best.provider or best.source or '未标注'}"
        )

        if not self.settings.auto_save:
            return f"{summary}\n自动转存已关闭。{drive_warning}"
        if self.settings.dry_run:
            return f"{summary}\n演练模式：不会实际转存。{drive_warning}"

        saved = await self.quark.save_share(
            best.share_url, str(best.extra.get("password") or "")
        )
        saved_text = await self._save_result_text(saved, best.title)
        return f"{summary}\n{saved_text}{drive_warning}"

    async def _save_result_text(self, saved, title: str) -> str:
        prefix = "✅" if saved.ok else "❌"
        base = f"{prefix} {saved.message}"
        if not saved.ok or not self.settings.organize_after_save:
            return base
        saved_fids = saved.saved_fids or await self._locate_saved_fids(title or saved.source_title)
        if not saved_fids:
            return (
                f"{base}\n⚠️ 转存成功，但夸克暂未返回保存位置，自动刮削整理未能完成。"
                "请稍后再次搜索同名资源，机器人会优先识别网盘中已有项目。"
            )
        try:
            result = await self.library.organize(
                saved_fids,
                title or saved.source_title,
                parent_hint=self.settings.quark_target_fid,
            )
        except Exception as exc:
            return f"{base}\n⚠️ 自动整理异常：{type(exc).__name__}"
        if result.ok:
            return (
                f"{base}\n"
                "✅ 已完成自动刮削与媒体库整理\n"
                f"📁 媒体库路径：{result.path}\n"
                f"🎭 分类：{result.genre}"
            )
        return f"{base}\n⚠️ 自动整理未完成：{result.message}"

    async def _locate_saved_fids(self, title: str) -> list[str]:
        """Best-effort fallback when Quark's save task omits saved FIDs."""
        query = title_only_query(title)
        if not query:
            return []
        for _attempt in range(8):
            rows = await self.quark.list_files(self.settings.quark_target_fid, limit=200)
            matches = [
                item for item in rows
                if item.name != self.settings.library_root_name
                and _title_relevance(query, item.name) >= 0.45
            ]
            if matches:
                matches.sort(
                    key=lambda item: (
                        _title_relevance(query, item.name),
                        _disk_quality_score(item),
                        item.size,
                    ),
                    reverse=True,
                )
                return [matches[0].fid]
            await asyncio.sleep(2)
        found = await self.quark.search_files(query, limit=50)
        if found.ok:
            matches = [
                item for item in found.files
                if _title_relevance(query, item.name) >= 0.55
            ]
            matches.sort(
                key=lambda item: (
                    _title_relevance(query, item.name),
                    _disk_quality_score(item),
                    item.size,
                ),
                reverse=True,
            )
            if matches:
                return [matches[0].fid]
        return []

    async def _organize_existing(self, query: str) -> str:
        if not self._quark_authenticated():
            return "❌ 夸克尚未登录，请先发送“夸克登录”并扫码。"
        title = title_only_query(query)
        found = await self.quark.search_files(title, limit=100)
        if not found.ok:
            return f"❌ 无法检索夸克网盘：{found.message}"
        matches = [
            item for item in found.files if _title_relevance(title, item.name) >= 0.55
        ]
        if not matches:
            return f"没有在夸克网盘找到可整理的“{title}”。"
        matches.sort(
            key=lambda item: (
                _title_relevance(title, item.name),
                _disk_quality_score(item),
                item.size,
            ),
            reverse=True,
        )
        best = matches[0]
        parent_hint = str(
            (best.raw or {}).get("pdir_fid") or self.settings.quark_target_fid
        )
        result = await self.library.organize(
            [best.fid], query or best.name, parent_hint=parent_hint
        )
        if result.ok:
            return (
                f"✅ 已整理：{best.name}\n"
                f"📁 {result.path}\n"
                f"🎭 分类：{result.genre}"
            )
        return f"❌ 整理失败：{result.message}"

    async def _organize_inbox(self) -> str:
        if not self._quark_authenticated():
            return "❌ 夸克尚未登录，请先发送“夸克登录”并扫码。"
        all_items = await self.quark.list_files(self.settings.quark_target_fid, limit=50)
        items = [item for item in all_items if self.library.should_batch_organize(item)]
        skipped = len(all_items) - len(items)
        if not items:
            return "转存目标目录没有检测到需要整理的影视项目。"
        success: list[str] = []
        failed: list[str] = []
        for item in items[:20]:
            try:
                result = await self.library.organize(
                    [item.fid], item.name, parent_hint=self.settings.quark_target_fid
                )
                if result.ok:
                    success.append(result.path)
                else:
                    failed.append(f"{item.name}：{result.message}")
            except Exception as exc:
                failed.append(f"{item.name}：{type(exc).__name__}")
        lines = [f"媒体库整理完成：成功 {len(success)}，失败 {len(failed)}，跳过非影视项目 {skipped}。"]
        if success:
            lines.append("已整理：\n" + "\n".join(f"- {value}" for value in success[:10]))
        if failed:
            lines.append("未完成：\n" + "\n".join(f"- {value}" for value in failed[:5]))
        if len(items) > 20:
            lines.append(f"本次只处理前 20 个影视候选，目录中还有 {len(items) - 20} 个候选。")
        return "\n".join(lines)

    async def _scrape_metadata(self, query: str) -> str:
        info = parse_media_info(query)
        record = await self.metadata.lookup(info)
        if record.source != "omdb":
            reason = (
                "OMDb 未命中，已使用标题信息做基础整理。"
                if self.settings.omdb_api_key
                else "未配置 OMDB_API_KEY，当前只能做片名解析和标准化整理。"
            )
            return (
                f"识别结果：{info.title}\n"
                f"类型：{'剧集' if info.content_type == 'tv' else '电影'}\n"
                f"年份：{info.year or '未识别'}\n"
                f"分类：{record.category or record.genre or '未分类'}\n"
                f"{reason}"
            )
        return (
            f"🎬 {record.title} ({record.year or '未知年份'})\n"
            f"类型：{'剧集' if record.content_type == 'tv' else '电影'}\n"
            f"分类：{record.category or record.genre}\n"
            f"类型词：{record.genre or '未提供'}\n"
            f"IMDb：{record.imdb_id or '未提供'}\n"
            f"简介：{record.plot or '未提供'}"
        )
