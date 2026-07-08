from __future__ import annotations

import asyncio
import io
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import httpx
import qrcode

QR_TOKEN_API = "https://uop.quark.cn/cas/ajax/getTokenForQrcodeLogin"
QR_STATUS_API = "https://uop.quark.cn/cas/ajax/getServiceTicketByQrcodeToken"
ACCOUNT_INFO_API = "https://pan.quark.cn/account/info"
DRIVE_CONFIG_API = "https://drive-pc.quark.cn/1/clouddrive/config"
QR_PAGE_BASE = "https://su.quark.cn/4_eMHBJ"
CLIENT_ID = "532"

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class QuarkLoginError(RuntimeError):
    pass


class QuarkAuthStore:
    """Persist Quark web cookies outside source control.

    The QR login result is written atomically and chmod'ed to 0600. An optional
    environment cookie remains as a migration fallback, but a scanned login in
    the auth file always takes precedence.
    """

    def __init__(self, path: str, fallback_cookie: str = ""):
        self.path = Path(path).expanduser()
        self.fallback_cookie = fallback_cookie.strip()

    def load_cookie(self) -> str:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                cookie = str(data.get("cookie") or "").strip()
                if cookie:
                    return cookie
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return self.fallback_cookie

    def save_cookie(self, cookie: str, account: dict | None = None) -> None:
        cookie = cookie.strip()
        if not cookie:
            raise ValueError("不能保存空的夸克 Cookie")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cookie": cookie,
            "updated_at": int(time.time()),
            "login_method": "qr_code",
            "account": account or {},
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise QuarkLoginError(f"清除夸克登录信息失败：{exc}") from exc

    @property
    def is_authenticated(self) -> bool:
        return bool(self.load_cookie())

    @property
    def has_scanned_login(self) -> bool:
        try:
            if not self.path.exists():
                return False
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return bool(data.get("cookie")) and data.get("login_method") == "qr_code"
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False


@dataclass(slots=True)
class QuarkLoginSession:
    session_id: str
    qr_token: str
    qr_url: str
    created_at: float
    expires_at: float
    status: str = "waiting"
    message: str = "等待扫码"
    client: httpx.AsyncClient = field(repr=False, default=None)  # type: ignore[assignment]
    account: dict = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in {"success", "expired", "failed", "cancelled"}


@dataclass(slots=True)
class QuarkLoginStatus:
    session_id: str
    status: str
    message: str
    expires_at: float

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def terminal(self) -> bool:
        return self.status in {"success", "expired", "failed", "cancelled"}


class QuarkQRLoginManager:
    """Create and poll Quark QR login sessions."""

    def __init__(
        self,
        auth_store: QuarkAuthStore,
        timeout: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.auth_store = auth_store
        self.timeout = max(60, min(timeout, 600))
        self.transport = transport
        self._sessions: dict[str, QuarkLoginSession] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def build_qr_url(token: str) -> str:
        params = {
            "token": token,
            "client_id": CLIENT_ID,
            "ssb": "weblogin",
            "uc_param_str": "",
            "uc_biz_str": "S:custom|OPT:SAREA@0|OPT:IMMERSIVE@1|OPT:BACK_BTN_STYLE@0",
        }
        return f"{QR_PAGE_BASE}?{urlencode(params)}"

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=_BASE_HEADERS,
            timeout=30,
            follow_redirects=True,
            transport=self.transport,
        )

    async def start(self) -> QuarkLoginSession:
        client = self._new_client()
        try:
            response = await client.get(
                QR_TOKEN_API,
                params={
                    "client_id": CLIENT_ID,
                    "v": "1.2",
                    "request_id": str(uuid.uuid4()),
                },
            )
            data = self._safe_json(response)
            token = str((((data.get("data") or {}).get("members") or {}).get("token") or ""))
            if response.status_code != 200 or data.get("status") != 2000000 or not token:
                raise QuarkLoginError(str(data.get("message") or "获取夸克登录二维码失败"))

            now = time.time()
            session = QuarkLoginSession(
                session_id=uuid.uuid4().hex,
                qr_token=token,
                qr_url=self.build_qr_url(token),
                created_at=now,
                expires_at=now + self.timeout,
                client=client,
            )
            async with self._lock:
                await self._cleanup_locked()
                self._sessions[session.session_id] = session
            return session
        except Exception:
            await client.aclose()
            raise

    def qr_png(self, session_id: str) -> bytes:
        session = self._sessions.get(session_id)
        if not session:
            raise QuarkLoginError("夸克登录会话不存在或已清理")
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=8,
            border=4,
        )
        qr.add_data(session.qr_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    async def poll(self, session_id: str) -> QuarkLoginStatus:
        session = self._sessions.get(session_id)
        if not session:
            return QuarkLoginStatus(session_id, "failed", "登录会话不存在", 0)
        if session.terminal:
            return self._public_status(session)
        if time.time() >= session.expires_at:
            await self._finish(session, "expired", "二维码已过期，请重新发送“夸克登录”")
            return self._public_status(session)

        try:
            response = await session.client.get(
                QR_STATUS_API,
                params={
                    "client_id": CLIENT_ID,
                    "v": "1.2",
                    "token": session.qr_token,
                    "request_id": str(uuid.uuid4()),
                },
            )
            data = self._safe_json(response)
            status_code = data.get("status")
            message = str(data.get("message") or "")
            service_ticket = str(
                (((data.get("data") or {}).get("members") or {}).get("service_ticket") or "")
            )

            if response.status_code == 200 and status_code == 2000000 and service_ticket:
                await self._exchange_ticket(session, service_ticket)
                return self._public_status(session)

            if status_code in {50004002, 50004003, 50004004} or any(
                word in message.lower() for word in ("expired", "timeout", "invalid", "failed")
            ):
                await self._finish(session, "expired", "二维码已失效，请重新发送“夸克登录”")
                return self._public_status(session)

            session.status = "waiting"
            session.message = "等待使用夸克 App 扫码并确认"
            return self._public_status(session)
        except httpx.HTTPError as exc:
            session.message = f"检查扫码状态暂时失败：{type(exc).__name__}"
            return self._public_status(session)
        except Exception as exc:
            await self._finish(session, "failed", f"夸克扫码登录失败：{type(exc).__name__}")
            return self._public_status(session)

    async def wait(self, session_id: str, interval: float = 2.0) -> QuarkLoginStatus:
        while True:
            status = await self.poll(session_id)
            if status.terminal:
                return status
            await asyncio.sleep(max(1.0, interval))

    async def cancel(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session and not session.terminal:
            await self._finish(session, "cancelled", "登录已取消")

    async def _exchange_ticket(self, session: QuarkLoginSession, service_ticket: str) -> None:
        response = await session.client.get(
            ACCOUNT_INFO_API,
            params={"st": service_ticket, "lw": "scan"},
        )
        if response.status_code >= 400:
            raise QuarkLoginError(f"扫码成功，但换取登录态失败：HTTP {response.status_code}")

        account = self._safe_json(response)

        # The drive config request may issue an additional __puus cookie used by
        # some Quark web-drive endpoints. Keep login usable even when this
        # optional refresh endpoint changes or is temporarily unavailable.
        try:
            await session.client.get(
                DRIVE_CONFIG_API,
                params={"pr": "ucpro", "fr": "pc", "uc_param_str": ""},
                headers={"Referer": "https://pan.quark.cn/"},
            )
        except httpx.HTTPError:
            pass

        cookies: list[str] = []
        seen: set[str] = set()
        for cookie in session.client.cookies.jar:
            if cookie.domain and "quark.cn" in cookie.domain and cookie.name not in seen:
                cookies.append(f"{cookie.name}={cookie.value}")
                seen.add(cookie.name)
        cookie_string = "; ".join(cookies)
        if not cookie_string:
            raise QuarkLoginError("扫码成功，但没有获取到夸克 Cookie")

        self.auth_store.save_cookie(cookie_string, account=account)
        session.account = account
        await self._finish(session, "success", "夸克扫码登录成功，登录态已安全保存")

    async def _finish(self, session: QuarkLoginSession, status: str, message: str) -> None:
        session.status = status
        session.message = message
        await session.client.aclose()

    async def _cleanup_locked(self) -> None:
        now = time.time()
        stale = [
            key
            for key, session in self._sessions.items()
            if session.terminal or now - session.expires_at > 600
        ]
        for key in stale:
            session = self._sessions.pop(key)
            if not session.client.is_closed:
                await session.client.aclose()

    @staticmethod
    def _public_status(session: QuarkLoginSession) -> QuarkLoginStatus:
        return QuarkLoginStatus(
            session_id=session.session_id,
            status=session.status,
            message=session.message,
            expires_at=session.expires_at,
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except Exception:
            return {"status_code": response.status_code, "text": response.text[:500]}
