from __future__ import annotations

from app.config import Settings, build_configuration_report


def _settings(**changes) -> Settings:
    base = dict(
        quark_cookie="",
        quark_target_fid="0",
        quark_passcode="",
        quark_auth_file="/tmp/quark.json",
        quark_qr_timeout=300,
        provider_api_urls=("https://example.test/search",),
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
        dry_run=True,
        feishu_app_id="cli_x",
        feishu_app_secret="secret",
        feishu_verification_token="verify",
        feishu_allowed_open_ids={"ou_x"},
        wecom_corp_id="",
        wecom_corp_secret="",
        wecom_agent_id=0,
        wecom_callback_token="",
        wecom_encoding_aes_key="",
        wecom_allowed_user_ids=set(),
    )
    base.update(changes)
    return Settings(**base)


def test_complete_feishu_and_provider_are_ready():
    report = build_configuration_report(_settings(), check_files=False)
    assert report.ready
    assert report.configured_channels == ("feishu",)
    assert report.provider_modes == ("authorized_api",)


def test_missing_feishu_secret_is_reported():
    report = build_configuration_report(
        _settings(feishu_app_secret=""), check_files=False
    )
    assert not report.ready
    assert "FEISHU_APP_SECRET" in report.required_missing


def test_no_provider_is_reported():
    report = build_configuration_report(
        _settings(provider_api_urls=(), panhub_base_url="", local_catalog_path="", website_config_path=""), check_files=False
    )
    assert not report.ready
    assert "PANHUB_BASE_URL、JPMOM_BASE_URL、HOUTUPAN_BASE_URL、WEBSITE_CONFIG_PATH、PROVIDER_API_URLS 或 LOCAL_CATALOG_PATH（至少一个）" in report.required_missing


def test_panhub_provider_is_ready():
    report = build_configuration_report(
        _settings(provider_api_urls=(), panhub_base_url="https://source-api.example"),
        check_files=False,
    )
    assert report.ready
    assert report.provider_modes == ("panhub",)


def test_builtin_sites_are_reported_as_providers():
    report = build_configuration_report(
        _settings(
            provider_api_urls=(),
            jpmom_enabled=True,
            houtupan_enabled=True,
        ),
        check_files=False,
    )
    assert report.ready
    assert report.provider_modes == ("jpmom", "houtupan")


def test_enabled_site_requires_base_url():
    report = build_configuration_report(
        _settings(provider_api_urls=(), jpmom_enabled=True, jpmom_base_url=""),
        check_files=False,
    )
    assert not report.ready
    assert "JPMOM_BASE_URL" in report.required_missing
