from __future__ import annotations

import time

import httpx
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse
from wechatpy.enterprise import parse_message
from wechatpy.enterprise.crypto import WeChatCrypto

from app.config import Settings
from app.service import MediaService, parse_intent


class WeComChannel:
    """Enterprise WeChat self-built app callback.

    Personal WeChat automation is intentionally not implemented because it
    normally depends on unofficial client hooks and is prone to account bans.
    """

    def __init__(self, settings: Settings, service: MediaService):
        self.settings = settings
        self.service = service
        self._access_token = ""
        self._access_token_expire_at = 0.0

    def _crypto(self) -> WeChatCrypto:
        if not (
            self.settings.wecom_callback_token
            and self.settings.wecom_encoding_aes_key
            and self.settings.wecom_corp_id
        ):
            raise RuntimeError("企业微信回调参数未完整配置")
        return WeChatCrypto(
            self.settings.wecom_callback_token,
            self.settings.wecom_encoding_aes_key,
            self.settings.wecom_corp_id,
        )

    async def verify(self, request: Request):
        query = request.query_params
        signature = query.get("msg_signature") or query.get("signature") or ""
        timestamp = query.get("timestamp") or ""
        nonce = query.get("nonce") or ""
        echostr = query.get("echostr") or ""
        try:
            plain = self._crypto().check_signature(signature, timestamp, nonce, echostr)
        except Exception as exc:
            raise HTTPException(status_code=403, detail="signature check failed") from exc
        if isinstance(plain, bytes):
            plain = plain.decode("utf-8")
        return PlainTextResponse(str(plain))

    async def webhook(self, request: Request, background_tasks: BackgroundTasks):
        query = request.query_params
        signature = query.get("msg_signature") or query.get("signature") or ""
        timestamp = query.get("timestamp") or ""
        nonce = query.get("nonce") or ""
        encrypted_xml = (await request.body()).decode("utf-8")
        try:
            plain_xml = self._crypto().decrypt_message(
                encrypted_xml, signature, timestamp, nonce
            )
            message = parse_message(plain_xml)
        except Exception as exc:
            raise HTTPException(status_code=403, detail="decrypt failed") from exc

        user_id = str(getattr(message, "source", "") or "")
        if not user_id:
            return PlainTextResponse("success")
        if self.settings.wecom_allowed_user_ids and user_id not in self.settings.wecom_allowed_user_ids:
            background_tasks.add_task(self.send_text, user_id, "无权限使用此机器人。")
            return PlainTextResponse("success")

        if getattr(message, "type", "") != "text":
            background_tasks.add_task(self.send_text, user_id, "目前只支持文本消息。")
            return PlainTextResponse("success")

        text = str(getattr(message, "content", "") or "").strip()
        background_tasks.add_task(self._process_and_reply, user_id, text)
        return PlainTextResponse("success")

    async def _process_and_reply(self, user_id: str, text: str):
        try:
            intent = parse_intent(text)
            if intent.action == "quark_login":
                await self._quark_qr_login(user_id)
                return
            reply = await self.service.handle(text)
        except Exception as exc:
            reply = f"处理失败：{type(exc).__name__}"
        await self.send_text(user_id, reply)

    async def _quark_qr_login(self, user_id: str):
        await self.send_text(user_id, "正在生成夸克登录二维码，请扫码后在夸克 App 中确认。")
        session = await self.service.start_quark_login()
        png = self.service.quark_login_qr_png(session.session_id)
        await self.send_image(user_id, png)
        remaining = max(1, int(session.expires_at - time.time()))
        await self.send_text(
            user_id,
            f"请在 {remaining // 60} 分钟内扫描上方二维码。登录成功后机器人会自动通知你。",
        )
        status = await self.service.wait_quark_login(session.session_id)
        await self.send_text(user_id, f"{'✅' if status.ok else '❌'} {status.message}")

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expire_at:
            return self._access_token
        if not self.settings.wecom_corp_id or not self.settings.wecom_corp_secret:
            raise RuntimeError("WECOM_CORP_ID/WECOM_CORP_SECRET 未配置")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={
                    "corpid": self.settings.wecom_corp_id,
                    "corpsecret": self.settings.wecom_corp_secret,
                },
            )
            data = response.json()
            if response.status_code != 200 or data.get("errcode") != 0:
                raise RuntimeError(data.get("errmsg") or "获取企业微信 access_token 失败")
            self._access_token = data["access_token"]
            self._access_token_expire_at = time.time() + int(data.get("expires_in", 7200)) - 120
            return self._access_token

    async def send_image(self, user_id: str, image_bytes: bytes):
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=20) as client:
            upload = await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/media/upload",
                params={"access_token": token, "type": "image"},
                files={"media": ("quark-login.png", image_bytes, "image/png")},
            )
            upload_data = upload.json()
            if upload.status_code != 200 or upload_data.get("errcode") != 0:
                raise RuntimeError(upload_data.get("errmsg") or "上传企业微信二维码失败")
            media_id = str(upload_data.get("media_id") or "").strip()
            if not media_id:
                raise RuntimeError("企业微信二维码 media_id 为空")

            response = await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": token},
                json={
                    "touser": user_id,
                    "msgtype": "image",
                    "agentid": self.settings.wecom_agent_id,
                    "image": {"media_id": media_id},
                    "safe": 0,
                },
            )
            data = response.json()
            if response.status_code != 200 or data.get("errcode") != 0:
                raise RuntimeError(data.get("errmsg") or "企业微信发送二维码失败")

    async def send_text(self, user_id: str, text: str):
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": token},
                json={
                    "touser": user_id,
                    "msgtype": "text",
                    "agentid": self.settings.wecom_agent_id,
                    "text": {"content": text},
                    "safe": 0,
                },
            )
            data = response.json()
            if response.status_code != 200 or data.get("errcode") != 0:
                raise RuntimeError(data.get("errmsg") or "企业微信发送消息失败")
