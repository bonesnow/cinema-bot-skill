from __future__ import annotations

import asyncio
import sys

from .config import Settings
from .providers import HeuristicSiteProvider, houtupan_profile, jpmom_profile
from .scoring import score_resource


async def _run(query: str) -> int:
    settings = Settings.from_env()
    providers = []
    if settings.jpmom_enabled and settings.jpmom_base_url:
        providers.append(
            HeuristicSiteProvider(
                jpmom_profile(
                    settings.jpmom_base_url,
                    settings.jpmom_cookie,
                    settings.jpmom_timeout,
                )
            )
        )
    if settings.houtupan_enabled and settings.houtupan_base_url:
        providers.append(
            HeuristicSiteProvider(
                houtupan_profile(
                    settings.houtupan_base_url,
                    settings.houtupan_cookie,
                    settings.houtupan_timeout,
                )
            )
        )

    if not providers:
        print("❌ 未配置可测试的站点适配器；请先启用并填写对应 BASE_URL")
        return 2

    print(f"测试关键词：{query}")
    print(f"启用站点：{', '.join(provider.name for provider in providers)}")
    outcomes = await asyncio.gather(
        *(provider.search(query) for provider in providers),
        return_exceptions=True,
    )

    total = 0
    for provider, outcome in zip(providers, outcomes):
        print("\n" + "=" * 60)
        print(provider.name)
        if isinstance(outcome, Exception):
            print(f"❌ {type(outcome).__name__}: {outcome}")
            continue
        print(f"✅ 找到 {len(outcome)} 个夸克候选")
        total += len(outcome)
        ranked = sorted(outcome, key=score_resource, reverse=True)
        for index, item in enumerate(ranked[:5], start=1):
            print(
                f"{index}. {item.title}\n"
                f"   质量：{item.quality or '未标注'}｜大小：{item.size or '未标注'}｜评分：{score_resource(item)}\n"
                f"   链接：{item.share_url}"
            )

    print("\n" + "=" * 60)
    print(f"总候选：{total}")
    return 0 if total else 1


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("用法：python -m app.site_test '片名'")
        return 2
    return asyncio.run(_run(query))


if __name__ == "__main__":
    raise SystemExit(main())
