from __future__ import annotations

from .base import ResourceProvider
from .heuristic_site import HeuristicSiteProfile, HeuristicSiteProvider
from .website import WebsiteProvider
from .website_config import SimpleSiteSourceConfig, WebsiteConfigReport, WebsiteSourceConfig, load_website_configs


def load_website_providers(path: str, allow_private_hosts: bool = False) -> tuple[list[ResourceProvider], WebsiteConfigReport]:
    report = load_website_configs(path)
    providers = []
    for config in report.sources:
        if isinstance(config, WebsiteSourceConfig):
            providers.append(WebsiteProvider(config, allow_private_hosts=allow_private_hosts))
            continue
        if isinstance(config, SimpleSiteSourceConfig):
            providers.append(
                HeuristicSiteProvider(
                    HeuristicSiteProfile(
                        name=config.name,
                        base_url=config.url,
                        search_templates=config.search_templates,
                        article_url_patterns=config.article_url_patterns,
                        cookie=config.cookie_value(),
                        timeout_seconds=config.timeout_seconds,
                        max_results=config.max_results,
                        detail_concurrency=config.detail_concurrency,
                        request_delay_seconds=config.request_delay_seconds,
                        browser_fallback=config.browser_fallback,
                    )
                )
            )
    return providers, report
