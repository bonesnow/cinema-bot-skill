from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, Request

from .channels.feishu import FeishuChannel
from .channels.wecom import WeComChannel
from .config import Settings, build_configuration_report
from .service import MediaService

settings = Settings.from_env()
configuration_report = build_configuration_report(settings, check_files=True)
service = MediaService(settings)
feishu = FeishuChannel(settings, service)
wecom = WeComChannel(settings, service)

app = FastAPI(title="Cinema Bot Skill", version="6.0.0")


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "version": "6.0.0",
        "configuration_ready": configuration_report.ready,
        "missing_configuration": list(configuration_report.required_missing),
        "configured_channels": list(configuration_report.configured_channels),
        "provider_modes": list(configuration_report.provider_modes),
        "providers_loaded": len(service.providers),
        "website_sources_loaded": len(service.website_report.sources) if service.website_report else 0,
        "website_configuration_errors": list(service.website_report.errors) if service.website_report else [],
        "quark_authenticated": service.quark.is_authenticated,
        "quark_login_method": "qr_code" if service.quark_auth.has_scanned_login else ("env_cookie" if service.quark.is_authenticated else "none"),
    }


@app.get("/setup/status")
async def setup_status():
    """Return configuration state only; never expose secret values."""
    return configuration_report.as_dict()


@app.post("/webhooks/feishu")
@app.post("/webhook/feishu", include_in_schema=False)
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    """Feishu event callback. Both singular and plural paths are accepted."""
    return await feishu.webhook(request, background_tasks)


@app.get("/webhooks/wecom")
async def wecom_verify(request: Request):
    return await wecom.verify(request)


@app.post("/webhooks/wecom")
async def wecom_webhook(request: Request, background_tasks: BackgroundTasks):
    return await wecom.webhook(request, background_tasks)
