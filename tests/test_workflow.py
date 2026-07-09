import asyncio
from dataclasses import replace

from app.config import Settings
from app.models import ResourceResult
from app.providers.website_config import load_website_configs
from app.providers.base import ResourceProvider
from app.quark import QuarkFileItem, QuarkSaveResult, QuarkSearchResult
from app.service import MediaService, title_only_query


def make_settings() -> Settings:
    return Settings(
        quark_cookie="cookie",
        quark_target_fid="target",
        quark_passcode="",
        quark_auth_file="/tmp/cinema-bot-test-quark-auth.json",
        quark_qr_timeout=300,
        provider_api_urls=(),
        provider_api_token="",
        panhub_base_url="",
        panhub_cookie="",
        panhub_concurrency=4,
        panhub_timeout=30,
        jpmom_enabled=False,
        jpmom_base_url="https://site-a.example",
        jpmom_cookie="",
        jpmom_timeout=30,
        houtupan_enabled=False,
        houtupan_base_url="https://site-b.example",
        houtupan_cookie="",
        houtupan_timeout=30,
        local_catalog_path="",
        website_config_path="",
        website_allow_private_hosts=False,
        auto_save=True,
        dry_run=False,
        feishu_app_id="",
        feishu_app_secret="",
        feishu_verification_token="",
        feishu_allowed_open_ids=set(),
        wecom_corp_id="",
        wecom_corp_secret="",
        wecom_agent_id=0,
        wecom_callback_token="",
        wecom_encoding_aes_key="",
        wecom_allowed_user_ids=set(),
    )


class FailingProvider(ResourceProvider):
    name = "should-not-run"

    async def search(self, query: str) -> list[ResourceResult]:
        raise AssertionError("provider should not run when drive already has a match")


class ResultProvider(ResourceProvider):
    name = "test-provider"

    async def search(self, query: str) -> list[ResourceResult]:
        assert query == "星际穿越"
        return [
            ResourceResult(
                title="星际穿越 2014 1080p WEB-DL 中字",
                share_url="https://pan.quark.cn/s/fullhd",
                quality="1080p WEB-DL",
                size="8GB",
            ),
            ResourceResult(
                title="星际穿越 2014 2160p REMUX HDR Atmos 中英字幕",
                share_url="https://pan.quark.cn/s/fourk",
                quality="2160p REMUX HDR Atmos",
                size="70GB",
            ),
        ]


class DriveHitQuark:
    async def search_files(self, keyword: str):
        assert keyword == "星际穿越"
        return QuarkSearchResult(
            True,
            "ok",
            [
                QuarkFileItem("星际穿越.2014.1080p.WEB-DL.mkv", "1", 8 * 1024**3),
                QuarkFileItem("星际穿越.2014.2160p.REMUX.HDR.mkv", "2", 70 * 1024**3),
            ],
            {},
        )

    async def save_share(self, share_url: str, passcode: str = ""):
        raise AssertionError("save should not run when drive already has a match")


class DriveMissQuark:
    def __init__(self):
        self.saved_url = ""

    async def search_files(self, keyword: str):
        return QuarkSearchResult(True, "ok", [], {})

    async def save_share(self, share_url: str, passcode: str = ""):
        self.saved_url = share_url
        return QuarkSaveResult(True, "已提交夸克转存任务", {})


def test_title_only_query_removes_quality_hints():
    assert title_only_query("星际穿越 4K HDR REMUX") == "星际穿越"


def test_drive_hit_stops_provider_search_and_selects_best_existing_version():
    service = MediaService(make_settings())
    service.providers = [FailingProvider()]
    service.quark = DriveHitQuark()

    reply = asyncio.run(service.handle("我要看 星际穿越"))

    assert "已经有" in reply
    assert "2160p.REMUX" in reply
    assert "无需重复转存" in reply


def test_drive_miss_searches_provider_and_saves_highest_quality():
    service = MediaService(replace(make_settings(), organize_after_save=False))
    service.providers = [ResultProvider()]
    quark = DriveMissQuark()
    service.quark = quark

    reply = asyncio.run(service.handle("我想看 星际穿越 4K"))

    assert quark.saved_url == "https://pan.quark.cn/s/fourk"
    assert "2160p REMUX HDR Atmos" in reply
    assert "共找到 2 个候选" in reply
    assert "已提交夸克转存任务" in reply


def test_dialog_adds_source_site_and_reloads_provider(tmp_path):
    config_path = tmp_path / "websites.yaml"
    service = MediaService(
        replace(
            make_settings(),
            provider_api_urls=(),
            website_config_path=str(config_path),
        )
    )

    reply = asyncio.run(service.handle("配置资源站 https://media.example"))

    assert "已添加资源站" in reply
    report = load_website_configs(str(config_path))
    assert report.errors == ()
    assert [source.name for source in report.sources] == ["media.example"]
    assert any(provider.name == "site:media.example" for provider in service.providers)


def test_dialog_lists_and_removes_source_sites(tmp_path):
    config_path = tmp_path / "websites.yaml"
    service = MediaService(
        replace(
            make_settings(),
            provider_api_urls=(),
            website_config_path=str(config_path),
        )
    )

    asyncio.run(service.handle("配置资源站 https://a.example https://b.example"))
    listing = asyncio.run(service.handle("资源站列表"))
    assert "a.example" in listing
    assert "b.example" in listing

    removed = asyncio.run(service.handle("删除资源站 a.example"))
    assert "已删除资源站" in removed
    listing = asyncio.run(service.handle("资源站列表"))
    assert "a.example" not in listing
    assert "b.example" in listing

    cleared = asyncio.run(service.handle("清空资源站"))
    assert "已清空" in cleared
    assert "尚未配置" in asyncio.run(service.handle("资源站列表"))
