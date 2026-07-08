from __future__ import annotations

from .website import WebsiteProvider
from .website_config import WebsiteConfigReport, load_website_configs


def load_website_providers(path: str, allow_private_hosts: bool = False) -> tuple[list[WebsiteProvider], WebsiteConfigReport]:
    report = load_website_configs(path)
    providers = [WebsiteProvider(config, allow_private_hosts=allow_private_hosts) for config in report.sources]
    return providers, report
