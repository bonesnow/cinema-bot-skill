from __future__ import annotations

from pathlib import Path

from app.providers.website_config import load_website_configs


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
