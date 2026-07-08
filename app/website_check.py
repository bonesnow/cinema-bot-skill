from __future__ import annotations

from .config import Settings
from .providers.website_config import load_website_configs


def main() -> int:
    settings = Settings.from_env()
    if not settings.website_config_path:
        print("❌ WEBSITE_CONFIG_PATH 未配置")
        return 1
    report = load_website_configs(settings.website_config_path)
    print(f"网站配置文件：{settings.website_config_path}")
    print(f"可用网站：{len(report.sources)} 个")
    for source in report.sources:
        print(f"✅ {source.name}｜模式：{source.mode}｜域名：{', '.join(source.allowed_domains)}")
    for warning in report.warnings:
        print(f"⚠️ {warning}")
    for error in report.errors:
        print(f"❌ {error}")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
