from __future__ import annotations

import asyncio
import sys

from .config import Settings
from .providers.website_loader import load_website_providers
from .scoring import score_resource


async def _run(query: str) -> int:
    settings = Settings.from_env()
    providers, report = load_website_providers(
        settings.website_config_path,
        allow_private_hosts=settings.website_allow_private_hosts,
    )
    if report.errors:
        for error in report.errors:
            print(f"❌ {error}")
        return 1
    if not providers:
        print("❌ 没有启用的网站")
        return 1

    outcomes = await asyncio.gather(
        *(provider.search(query) for provider in providers),
        return_exceptions=True,
    )
    results = []
    for provider, outcome in zip(providers, outcomes):
        if isinstance(outcome, Exception):
            print(f"⚠️ {provider.name}: {type(outcome).__name__}: {outcome}")
        else:
            results.extend(outcome)
    results.sort(key=score_resource, reverse=True)
    if not results:
        print("未找到包含夸克分享链接的结果。")
        return 2
    for index, item in enumerate(results[:20], start=1):
        print(f"{index}. [{item.provider}] {item.title}｜{item.quality or '未标注'}｜{item.size or '未标注'}｜评分 {score_resource(item)}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print('用法：python -m app.website_test "影片名称"')
        return 1
    return asyncio.run(_run(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
