import asyncio
from pathlib import Path

import httpx

from app.quark_auth import (
    ACCOUNT_INFO_API,
    DRIVE_CONFIG_API,
    QR_STATUS_API,
    QR_TOKEN_API,
    QuarkAuthStore,
    QuarkQRLoginManager,
)


def test_auth_store_persists_and_clears_cookie(tmp_path: Path):
    path = tmp_path / "quark_auth.json"
    store = QuarkAuthStore(str(path))
    store.save_cookie("__pus=abc; __puus=def", {"nickname": "test"})

    assert store.load_cookie() == "__pus=abc; __puus=def"
    assert store.has_scanned_login is True
    assert oct(path.stat().st_mode & 0o777) == "0o600"

    store.clear()
    assert store.load_cookie() == ""


def test_qr_login_exchanges_ticket_and_saves_cookie(tmp_path: Path):
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url).split("?")[0]
            if url == QR_TOKEN_API:
                return httpx.Response(
                    200,
                    json={
                        "status": 2000000,
                        "message": "ok",
                        "data": {"members": {"token": "qr-token"}},
                    },
                )
            if url == QR_STATUS_API:
                return httpx.Response(
                    200,
                    json={
                        "status": 2000000,
                        "message": "ok",
                        "data": {"members": {"service_ticket": "ticket-1"}},
                    },
                )
            if url == ACCOUNT_INFO_API:
                return httpx.Response(
                    200,
                    headers={
                        "set-cookie": "__pus=scan-cookie; Domain=.quark.cn; Path=/; HttpOnly"
                    },
                    json={"data": {"nickname": "扫码用户"}},
                )
            if url == DRIVE_CONFIG_API:
                return httpx.Response(
                    200,
                    headers={
                        "set-cookie": "__puus=drive-cookie; Domain=.quark.cn; Path=/; HttpOnly"
                    },
                    json={"status": 200, "code": 0},
                )
            raise AssertionError(f"unexpected request: {request.url}")

        path = tmp_path / "quark_auth.json"
        store = QuarkAuthStore(str(path))
        manager = QuarkQRLoginManager(
            store,
            timeout=300,
            transport=httpx.MockTransport(handler),
        )
        session = await manager.start()
        assert "token=qr-token" in session.qr_url
        assert manager.qr_png(session.session_id).startswith(b"\x89PNG")

        status = await manager.poll(session.session_id)
        assert status.ok is True
        assert "__pus=scan-cookie" in store.load_cookie()
        assert "__puus=drive-cookie" in store.load_cookie()

    asyncio.run(run())
