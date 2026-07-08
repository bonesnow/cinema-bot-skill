from __future__ import annotations

from .config import Settings, build_configuration_report


def main() -> int:
    settings = Settings.from_env()
    report = build_configuration_report(settings, check_files=True)

    print("=" * 66)
    print("Cinema Bot 配置检查（不会显示任何密钥内容）")
    print("=" * 66)

    if settings.feishu_ready:
        print("✅ 飞书基础配置完整")
    else:
        print("❌ 飞书基础配置不完整")

    if report.provider_modes:
        modes = "、".join(report.provider_modes)
        print(f"✅ 已配置资源源：{modes}")
    else:
        print("❌ 尚未配置可用资源源")

    print("✅ 夸克默认使用扫码登录，无需预填 Cookie")
    print(f"ℹ️  演练模式 DRY_RUN：{'开启' if settings.dry_run else '关闭'}")
    print(f"ℹ️  自动转存 AUTO_SAVE：{'开启' if settings.auto_save else '关闭'}")
    print(f"ℹ️  目标目录 FID：{settings.quark_target_fid}")
    print(f"ℹ️  自动整理 ORGANIZE_AFTER_SAVE：{'开启' if settings.organize_after_save else '关闭'}")
    print(f"ℹ️  媒体库目录：{settings.library_root_name}")
    print(f"ℹ️  分类刮削：{'OMDb 已配置' if settings.omdb_api_key else '基础模式（按片名和来源信息分类）'}")

    if report.required_missing:
        print("\n🔴 必须补充：")
        for item in report.required_missing:
            print(f"  - {item}")

    if report.warnings:
        print("\n🟡 建议处理：")
        for item in report.warnings:
            print(f"  - {item}")

    print("\n" + ("✅ 配置可进入联调阶段" if report.ready else "❌ 配置尚未完成"))
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
