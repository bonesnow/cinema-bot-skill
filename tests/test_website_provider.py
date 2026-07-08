from __future__ import annotations

import types

import pytest

from app.providers.website import WebsiteProvider
from app.providers.website_config import (
    WebsiteDetail,
    WebsiteSearch,
    WebsiteSelectors,
    WebsiteSourceConfig,
)


def make_config() -> WebsiteSourceConfig:
    return WebsiteSourceConfig(
        name="demo",
        enabled=True,
        authorized=True,
        mode="html",
        allowed_domains=("example.com",),
        search=WebsiteSearch(url="https://example.com/search", query_param="q"),
        selectors=WebsiteSelectors(
            result_item=".item",
            title=".title",
            detail_url="a.detail",
            quality=".quality",
            size=".size",
        ),
        detail=WebsiteDetail(share_url_selector="a.quark"),
        headers={},
        cookie_env="",
        storage_state_path="",
        timeout_seconds=20,
        max_results=10,
        detail_concurrency=2,
        request_delay_seconds=0,
        browser_headless=True,
    )


@pytest.mark.asyncio
async def test_html_provider_extracts_direct_quark_link():
    provider = WebsiteProvider(make_config())

    async def fake_request(self, client, method, url, **kwargs):
        return """
        <div class='item'>
          <span class='title'>测试电影 2160p REMUX</span>
          <span class='quality'>2160p REMUX</span>
          <span class='size'>65GB</span>
          <a class='detail' href='/detail/1'>详情</a>
          <a href='https://pan.quark.cn/s/abc123'>保存</a>
        </div>
        """

    provider._request_html = types.MethodType(fake_request, provider)
    results = await provider.search("测试电影")
    assert len(results) == 1
    assert results[0].share_url == "https://pan.quark.cn/s/abc123"
    assert results[0].provider == "demo"


@pytest.mark.asyncio
async def test_html_provider_follows_detail_page():
    provider = WebsiteProvider(make_config())

    async def fake_request(self, client, method, url, **kwargs):
        if "/detail/1" in url:
            return "<a class='quark' href='https://pan.quark.cn/s/detail456'>夸克</a>"
        return """
        <div class='item'>
          <span class='title'>测试电影 1080p WEB-DL</span>
          <span class='quality'>1080p WEB-DL</span>
          <a class='detail' href='/detail/1'>详情</a>
        </div>
        """

    provider._request_html = types.MethodType(fake_request, provider)
    results = await provider.search("测试电影")
    assert len(results) == 1
    assert results[0].share_url == "https://pan.quark.cn/s/detail456"
