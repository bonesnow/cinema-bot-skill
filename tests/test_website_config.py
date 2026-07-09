from __future__ import annotations

from pathlib import Path

from app.providers.website_config import load_website_configs
from app.providers.website_loader import load_website_providers


def test_load_valid_html_website_config(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
websites:
  - name: demo
    enabled: true
    authorized: true
    mode: html
    allowed_domains: [example.com]
    search:
      url: https://example.com/search
      method: GET
      query_param: q
    selectors:
      result_item: .item
      title: .title
      detail_url: a
    detail:
      share_url_selector: a.quark
""",
        encoding="utf-8",
    )
    report = load_website_configs(str(config_file))
    assert report.errors == ()
    assert len(report.sources) == 1
    assert report.sources[0].name == "demo"
    assert report.sources[0].mode == "html"


def test_website_requires_explicit_authorization(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
websites:
  - name: demo
    enabled: true
    authorized: false
    mode: html
    allowed_domains: [example.com]
    search:
      url: https://example.com/search
    selectors:
      result_item: .item
      title: .title
""",
        encoding="utf-8",
    )
    report = load_website_configs(str(config_file))
    assert not report.sources
    assert any("authorized" in error for error in report.errors)


def test_search_domain_must_be_allowlisted(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
websites:
  - name: demo
    enabled: true
    authorized: true
    mode: html
    allowed_domains: [allowed.example]
    search:
      url: https://other.example/search
    selectors:
      result_item: .item
      title: .title
""",
        encoding="utf-8",
    )
    report = load_website_configs(str(config_file))
    assert not report.sources
    assert any("allowed_domains" in error for error in report.errors)


def test_simple_site_only_requires_authorized_url(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
simple_sites:
  - url: https://media.example
    enabled: true
    authorized: true
""",
        encoding="utf-8",
    )
    report = load_website_configs(str(config_file))
    assert report.errors == ()
    assert len(report.sources) == 1
    source = report.sources[0]
    assert source.name == "media.example"
    assert source.url == "https://media.example"


def test_simple_site_becomes_heuristic_provider(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
simple_sites:
  - url: media.example
    enabled: true
    authorized: true
""",
        encoding="utf-8",
    )
    providers, report = load_website_providers(str(config_file))
    assert report.errors == ()
    assert len(providers) == 1
    assert providers[0].name == "site:media.example"


def test_simple_site_rejects_private_host(tmp_path: Path):
    config_file = tmp_path / "websites.yaml"
    config_file.write_text(
        """
simple_sites:
  - url: http://127.0.0.1:8080
    enabled: true
    authorized: true
""",
        encoding="utf-8",
    )
    report = load_website_configs(str(config_file))
    assert not report.sources
    assert any("私有 IP" in error for error in report.errors)
