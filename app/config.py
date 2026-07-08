from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_PLACEHOLDER_MARKERS = (
    "__FILL_",
    "【请填写",
    "<FILL_",
    "YOUR_",
)


def _is_placeholder(value: str) -> bool:
    upper = value.strip().upper()
    return any(marker.upper() in upper for marker in _PLACEHOLDER_MARKERS)


def _text(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    return "" if _is_placeholder(value) else value


def _csv(name: str) -> set[str]:
    value = _text(name)
    return {item.strip() for item in value.split(",") if item.strip()}


def _int(name: str, default: int) -> int:
    try:
        value = _text(name, str(default))
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = _text(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    quark_cookie: str
    quark_target_fid: str
    quark_passcode: str
    quark_auth_file: str
    quark_qr_timeout: int
    provider_api_urls: tuple[str, ...]
    provider_api_token: str
    panhub_base_url: str
    panhub_cookie: str
    panhub_concurrency: int
    panhub_timeout: int
    jpmom_enabled: bool
    jpmom_base_url: str
    jpmom_cookie: str
    jpmom_timeout: int
    houtupan_enabled: bool
    houtupan_base_url: str
    houtupan_cookie: str
    houtupan_timeout: int
    local_catalog_path: str
    website_config_path: str
    website_allow_private_hosts: bool
    auto_save: bool
    dry_run: bool

    feishu_app_id: str
    feishu_app_secret: str
    feishu_verification_token: str
    feishu_allowed_open_ids: set[str]

    wecom_corp_id: str
    wecom_corp_secret: str
    wecom_agent_id: int
    wecom_callback_token: str
    wecom_encoding_aes_key: str
    wecom_allowed_user_ids: set[str]

    # Media library organization / metadata classification. Defaults preserve
    # compatibility with existing Settings(...) callers and upgrades.
    organize_after_save: bool = True
    library_root_name: str = "夸克影视"
    library_root_fid: str = ""
    library_genre_folders: bool = True
    library_keep_scene_names: bool = True
    omdb_api_key: str = ""
    metadata_cache_path: str = "/data/metadata_cache.json"

    @classmethod
    def from_env(cls) -> "Settings":
        urls_value = _text("PROVIDER_API_URLS")
        urls = tuple(item.strip() for item in urls_value.split(";") if item.strip())
        return cls(
            quark_cookie=_text("QUARK_COOKIE"),
            quark_target_fid=_text("QUARK_TARGET_FID", "0") or "0",
            quark_passcode=_text("QUARK_DEFAULT_PASSCODE"),
            quark_auth_file=_text("QUARK_AUTH_FILE", "/data/quark_auth.json") or "/data/quark_auth.json",
            quark_qr_timeout=max(60, min(_int("QUARK_QR_TIMEOUT", 300), 600)),
            provider_api_urls=urls,
            provider_api_token=_text("PROVIDER_API_TOKEN"),
            panhub_base_url=_text("PANHUB_BASE_URL"),
            panhub_cookie=_text("PANHUB_COOKIE"),
            panhub_concurrency=max(1, min(_int("PANHUB_CONCURRENCY", 4), 16)),
            panhub_timeout=max(5, min(_int("PANHUB_TIMEOUT", 30), 90)),
            jpmom_enabled=_bool("JPMOM_ENABLED", False),
            jpmom_base_url=_text("JPMOM_BASE_URL"),
            jpmom_cookie=_text("JPMOM_COOKIE"),
            jpmom_timeout=max(5, min(_int("JPMOM_TIMEOUT", 30), 90)),
            houtupan_enabled=_bool("HOUTUPAN_ENABLED", False),
            houtupan_base_url=_text("HOUTUPAN_BASE_URL"),
            houtupan_cookie=_text("HOUTUPAN_COOKIE"),
            houtupan_timeout=max(5, min(_int("HOUTUPAN_TIMEOUT", 30), 90)),
            local_catalog_path=_text("LOCAL_CATALOG_PATH"),
            website_config_path=_text("WEBSITE_CONFIG_PATH"),
            website_allow_private_hosts=_bool("WEBSITE_ALLOW_PRIVATE_HOSTS", False),
            auto_save=_bool("AUTO_SAVE", True),
            dry_run=_bool("DRY_RUN", True),
            feishu_app_id=_text("FEISHU_APP_ID"),
            feishu_app_secret=_text("FEISHU_APP_SECRET"),
            feishu_verification_token=_text("FEISHU_VERIFICATION_TOKEN"),
            feishu_allowed_open_ids=_csv("FEISHU_ALLOWED_OPEN_IDS"),
            wecom_corp_id=_text("WECOM_CORP_ID"),
            wecom_corp_secret=_text("WECOM_CORP_SECRET"),
            wecom_agent_id=_int("WECOM_AGENT_ID", 0),
            wecom_callback_token=_text("WECOM_CALLBACK_TOKEN"),
            wecom_encoding_aes_key=_text("WECOM_ENCODING_AES_KEY"),
            wecom_allowed_user_ids=_csv("WECOM_ALLOWED_USER_IDS"),
            organize_after_save=_bool("ORGANIZE_AFTER_SAVE", True),
            library_root_name=_text("LIBRARY_ROOT_NAME", "夸克影视") or "夸克影视",
            library_root_fid=_text("LIBRARY_ROOT_FID"),
            library_genre_folders=_bool("LIBRARY_GENRE_FOLDERS", True),
            library_keep_scene_names=_bool("LIBRARY_KEEP_SCENE_NAMES", True),
            omdb_api_key=_text("OMDB_API_KEY"),
            metadata_cache_path=_text("METADATA_CACHE_PATH", "/data/metadata_cache.json") or "/data/metadata_cache.json",
        )

    @property
    def feishu_ready(self) -> bool:
        return bool(
            self.feishu_app_id
            and self.feishu_app_secret
            and self.feishu_verification_token
        )

    @property
    def wecom_ready(self) -> bool:
        return bool(
            self.wecom_corp_id
            and self.wecom_corp_secret
            and self.wecom_agent_id
            and self.wecom_callback_token
            and self.wecom_encoding_aes_key
        )

    @property
    def provider_ready(self) -> bool:
        return bool(
            self.provider_api_urls
            or self.panhub_base_url
            or (self.jpmom_enabled and self.jpmom_base_url)
            or (self.houtupan_enabled and self.houtupan_base_url)
            or self.local_catalog_path
            or self.website_config_path
        )


@dataclass(frozen=True, slots=True)
class ConfigurationReport:
    required_missing: tuple[str, ...]
    warnings: tuple[str, ...]
    configured_channels: tuple[str, ...]
    provider_modes: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.required_missing

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "required_missing": list(self.required_missing),
            "warnings": list(self.warnings),
            "configured_channels": list(self.configured_channels),
            "provider_modes": list(self.provider_modes),
        }


def build_configuration_report(settings: Settings, check_files: bool = True) -> ConfigurationReport:
    missing: list[str] = []
    warnings: list[str] = []
    channels: list[str] = []
    providers: list[str] = []

    feishu_any = bool(
        settings.feishu_app_id
        or settings.feishu_app_secret
        or settings.feishu_verification_token
    )
    if settings.feishu_ready:
        channels.append("feishu")
        if not settings.feishu_allowed_open_ids:
            warnings.append("FEISHU_ALLOWED_OPEN_IDS 未配置；生产环境应设置用户白名单")
    elif feishu_any:
        if not settings.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not settings.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not settings.feishu_verification_token:
            missing.append("FEISHU_VERIFICATION_TOKEN")

    wecom_any = bool(
        settings.wecom_corp_id
        or settings.wecom_corp_secret
        or settings.wecom_agent_id
        or settings.wecom_callback_token
        or settings.wecom_encoding_aes_key
    )
    if settings.wecom_ready:
        channels.append("wecom")
        if not settings.wecom_allowed_user_ids:
            warnings.append("WECOM_ALLOWED_USER_IDS 未配置；生产环境应设置用户白名单")
    elif wecom_any:
        if not settings.wecom_corp_id:
            missing.append("WECOM_CORP_ID")
        if not settings.wecom_corp_secret:
            missing.append("WECOM_CORP_SECRET")
        if not settings.wecom_agent_id:
            missing.append("WECOM_AGENT_ID")
        if not settings.wecom_callback_token:
            missing.append("WECOM_CALLBACK_TOKEN")
        if not settings.wecom_encoding_aes_key:
            missing.append("WECOM_ENCODING_AES_KEY")

    if not channels and not (feishu_any or wecom_any):
        missing.extend(
            [
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "FEISHU_VERIFICATION_TOKEN",
            ]
        )

    if settings.provider_api_urls:
        providers.append("authorized_api")
    if settings.panhub_base_url:
        providers.append("panhub")
    if settings.jpmom_enabled and settings.jpmom_base_url:
        providers.append("jpmom")
    elif settings.jpmom_enabled:
        missing.append("JPMOM_BASE_URL")
    if settings.houtupan_enabled and settings.houtupan_base_url:
        providers.append("houtupan")
    elif settings.houtupan_enabled:
        missing.append("HOUTUPAN_BASE_URL")
    if settings.local_catalog_path:
        providers.append("local_catalog")
        if check_files and not Path(settings.local_catalog_path).exists():
            warnings.append(
                f"本地资源目录不存在：{settings.local_catalog_path}；请复制 catalog.example.json"
            )
    if settings.website_config_path:
        if check_files and not Path(settings.website_config_path).exists():
            warnings.append(
                f"资源网站配置不存在：{settings.website_config_path}；请复制 websites.example.yaml"
            )
        else:
            try:
                from .providers.website_config import load_website_configs

                website_report = load_website_configs(settings.website_config_path)
                if website_report.sources:
                    providers.append("website")
                elif not providers:
                    missing.append("websites.yaml 中至少启用一个 authorized=true 的网站")
                else:
                    warnings.append("websites.yaml 中没有启用的网站；当前将使用其他资源源")
                warnings.extend(website_report.warnings)
                warnings.extend(website_report.errors)
            except Exception as exc:
                warnings.append(f"网站配置检查失败：{type(exc).__name__}")
    if not providers:
        missing.append("PANHUB_BASE_URL、JPMOM_BASE_URL、HOUTUPAN_BASE_URL、WEBSITE_CONFIG_PATH、PROVIDER_API_URLS 或 LOCAL_CATALOG_PATH（至少一个）")

    if not settings.feishu_allowed_open_ids and "feishu" in channels:
        pass
    if not settings.dry_run:
        warnings.append("DRY_RUN=false：当前会执行真实转存")
    if settings.quark_cookie:
        warnings.append("检测到 QUARK_COOKIE；推荐清空并改用机器人扫码登录")
    if settings.organize_after_save and not settings.omdb_api_key:
        warnings.append("自动整理已开启但未配置 OMDB_API_KEY：仍会按片名和来源信息做基础分类")

    # Keep deterministic order while removing duplicates.
    missing = list(dict.fromkeys(missing))
    warnings = list(dict.fromkeys(warnings))
    return ConfigurationReport(
        required_missing=tuple(missing),
        warnings=tuple(warnings),
        configured_channels=tuple(channels),
        provider_modes=tuple(providers),
    )
