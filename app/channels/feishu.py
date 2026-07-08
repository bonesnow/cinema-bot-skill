from __future__ import annotations

import json
import time

import httpx
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.service import MediaService, parse_intent


class FeishuChannel:
    def __init__(self, settings: Settings, service: MediaService):
        self.settings = settings
        self.service = service
        self._tenant_token = ""
        self._tenant_token_expire_at = 0.0
        self._seen_events: dict[str, float] = {}

    async def webhook(self, request: Request, background_tasks: BackgroundTasks):
        body = await request.json()

        # URL verification challenge.
        if "challenge" in body:
            token = body.get("token", "")
            if self.settings.feishu_verification_token and token != self.settings.feishu_verification_token:
                raise HTTPException(status_code=403, detail="invalid verification token")
            return JSONResponse({"challenge": body["challenge"]})

        header = body.get("header") or {}
        if self.settings.feishu_verification_token:
            token = header.get("token") or body.get("token") or ""
            if token != self.settings.feishu_verification_token:
                raise HTTPException(status_code=403, detail="invalid verification token")

        event_id = str(header.get("event_id") or "")
        if event_id and self._is_duplicate(event_id):
            return JSONResponse({"code": 0})

        event = body.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        open_id = str(sender_id.get("open_id") or "")
        if not open_id:
            return JSONResponse({"code": 0})
        if self.settings.feishu_allowed_open_ids and open_id not in self.settings.feishu_allowed_open_ids:
            background_tasks.add_task(self.send_text, open_id, "无权限使用此机器人。", "open_id")
            return JSONResponse({"code": 0})

        if message.get("message_type") != "text":
            chat_id = str(message.get("chat_id") or "")
            background_tasks.add_task(self.send_text, chat_id or open_id, "目前只支持文本消息。", "chat_id" if chat_id else "open_id")
            return JSONResponse({"code": 0})

        try:
            content = json.loads(message.get("content") or "{}")
            text = str(content.get("text") or "").strip()
        except json.JSONDecodeError:
            text = ""

        chat_id = str(message.get("chat_id") or "")
        background_tasks.add_task(
            self._process_and_reply,
            chat_id or open_id,
            "chat_id" if chat_id else "open_id",
            text,
        )
        return JSONResponse({"code": 0})

    def _is_duplicate(self, event_id: str) -> bool:
        now = time.time()
        self._seen_events = {key: ts for key, ts in self._seen_events.items() if now - ts < 600}
        if event_id in self._seen_events:
            return True
        self._seen_events[event_id] = now
        return False

    async def _process_and_reply(self, receive_id: str, receive_id_type: str, text: str):
        try:
            intent = parse_intent(text)
            if intent.action == "quark_login":
                await self._quark_qr_login(receive_id, receive_id_type)
                return
            if intent.action == "search":
                await self.send_text(
                    receive_id,
                    f"收到，正在先检查夸克网盘：{intent.query}",
                    receive_id_type,
                )
            reply = await self.service.handle(text)
        except Exception as exc:
            reply = f"处理失败：{type(exc).__name__}"
        await self.send_text(receive_id, reply, receive_id_type)


    async def _quark_qr_login(self, receive_id: str, receive_id_type: str):
        await self.send_text(
            receive_id,
            "正在生成夸克登录二维码，扫码后请在夸克 App 中确认登录。",
            receive_id_type,
        )
        session = await self.service.start_quark_login()
        png = self.service.quark_login_qr_png(session.session_id)
        await self.send_image(receive_id, png, receive_id_type)
        remaining = max(1, int(session.expires_at - time.time()))
        await self.send_text(
            receive_id,
            f"请在 {remaining // 60} 分钟内使用夸克 App 扫描上方二维码。登录成功后机器人会自动通知你。",
            receive_id_type,
        )
        status = await self.service.wait_quark_login(session.session_id)
        prefix = "✅" if status.ok else "❌"
        await self.send_text(receive_id, f"{prefix} {status.message}", receive_id_type)

    async def _get_tenant_token(self) -> str:
        if self._tenant_token and time.time() < self._tenant_token_expire_at:
            return self._tenant_token
        if not self.settings.feishu_app_id or not self.settings.feishu_app_secret:
            raise RuntimeError("FEISHU_APP_ID/FEISHU_APP_SECRET 未配置")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.settings.feishu_app_id,
                    "app_secret": self.settings.feishu_app_secret,
                },
            )
            data = response.json()
            if response.status_code != 200 or data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "获取飞书 tenant_access_token 失败")
            self._tenant_token = data["tenant_access_token"]
            self._tenant_token_expire_at = time.time() + int(data.get("expire", 7200)) - 120
            return self._tenant_token

    async def send_image(self, receive_id: str, image_bytes: bytes, receive_id_type: str = "open_id"):
        token = await self._get_tenant_token()
        async with httpx.AsyncClient(timeout=20) as client:
            upload = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                data={"image_type": "message"},
                files={"image": ("quark-login.png", image_bytes, "image/png")},
            )
            upload_data = upload.json()
            if upload.status_code != 200 or upload_data.get("code") != 0:
                raise RuntimeError(upload_data.get("msg") or "上传飞书二维码图片失败")
            image_key = ((upload_data.get("data") or {}).get("image_key") or "").strip()
            if not image_key:
                raise RuntimeError("飞书二维码 image_key 为空")

            response = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": receive_id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "image",
                    "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
                },
            )
            data = response.json()
            if response.status_code != 200 or data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "发送飞书二维码图片失败")

    async def send_text(self, receive_id: str, text: str, receive_id_type: str = "open_id"):
        token = await self._get_tenant_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": receive_id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            response.raise_for_status()
