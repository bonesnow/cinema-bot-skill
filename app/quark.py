from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx

from .quark_auth import QuarkAuthStore

QUARK_API_BASES = (
    "https://drive-pc.quark.cn/1/clouddrive",
    "https://drive-h.quark.cn/1/clouddrive",
)
QUARK_SEARCH_APIS = QUARK_API_BASES
QUARK_SHARE_API = "https://drive.quark.cn/1/clouddrive"
_SHARE_RE = re.compile(r"pan\.quark\.cn/s/([A-Za-z0-9_-]+)")


@dataclass(slots=True)
class QuarkSaveResult:
    ok: bool
    message: str
    raw: dict
    saved_fids: list[str] = field(default_factory=list)
    source_title: str = ""
    task_id: str = ""


@dataclass(slots=True)
class QuarkFileItem:
    name: str
    fid: str
    size: int = 0
    is_dir: bool = False
    path: str = ""
    raw: dict | None = None


@dataclass(slots=True)
class QuarkSearchResult:
    ok: bool
    message: str
    files: list[QuarkFileItem]
    raw: dict


class QuarkClient:
    """Isolated Quark web client for search, save and media-library operations."""

    def __init__(
        self,
        cookie: str = "",
        target_fid: str = "0",
        default_passcode: str = "",
        auth_store: QuarkAuthStore | None = None,
    ):
        self._fallback_cookie = cookie.strip()
        self.auth_store = auth_store
        self.target_fid = target_fid or "0"
        self.default_passcode = default_passcode

    @property
    def cookie(self) -> str:
        if self.auth_store:
            return self.auth_store.load_cookie()
        return self._fallback_cookie

    @property
    def is_authenticated(self) -> bool:
        return bool(self.cookie)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Cookie": self.cookie,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://pan.quark.cn/",
            "Origin": "https://pan.quark.cn",
        }

    @staticmethod
    def parse_share(share_url: str, explicit_passcode: str = "") -> tuple[str, str]:
        match = _SHARE_RE.search(share_url)
        if not match:
            raise ValueError("不是有效的夸克分享链接")
        parsed = urlparse(share_url)
        query = parse_qs(parsed.query)
        passcode = explicit_passcode or query.get("pwd", [""])[0] or query.get("passcode", [""])[0]
        return match.group(1), passcode

    async def search_files(self, keyword: str, limit: int = 100) -> QuarkSearchResult:
        keyword = keyword.strip()
        if not keyword:
            return QuarkSearchResult(False, "搜索关键词为空", [], {})
        if not self.cookie:
            return QuarkSearchResult(False, "夸克未登录，请发送“夸克登录”扫码", [], {})

        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "q": keyword,
            "_page": "1",
            "_size": str(max(1, min(limit, 100))),
            "_fetch_total": "1",
            "_sort": "file_name:asc,updated_at:desc",
            "_is_hl": "1",
        }
        last_data: dict = {}
        last_message = "夸克网盘搜索失败"
        data: dict = {}
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                for api_base in QUARK_SEARCH_APIS:
                    response = await client.get(f"{api_base}/file/search", params=params, headers=self.headers)
                    data = self._safe_json(response)
                    code = data.get("code")
                    status = data.get("status", response.status_code)
                    if response.status_code == 200 and code in (0, None) and status in (200, None):
                        break
                    last_data = data
                    if response.status_code in (401, 403) or status in (401, 403):
                        last_message = "夸克登录已失效，请重新发送“夸克登录”扫码"
                    else:
                        last_message = str(data.get("message") or data.get("msg") or last_message)
                else:
                    return QuarkSearchResult(False, last_message, [], last_data)
        except httpx.HTTPError as exc:
            return QuarkSearchResult(False, f"连接夸克网盘失败：{type(exc).__name__}", [], last_data)

        rows = ((data.get("data") or {}).get("list") or [])
        files = [item for row in rows if isinstance(row, dict) and (item := self._item_from_row(row))]
        return QuarkSearchResult(True, f"找到 {len(files)} 个网盘结果", files, data)

    async def list_files(self, parent_fid: str = "0", limit: int = 200) -> list[QuarkFileItem]:
        if not self.cookie:
            return []
        items: list[QuarkFileItem] = []
        page = 1
        page_size = min(100, max(1, limit))
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            while len(items) < limit:
                response = None
                data: dict = {}
                for _attempt in range(2):
                    for api_base in QUARK_API_BASES:
                        try:
                            response = await client.get(
                                f"{api_base}/file/sort",
                                params={
                                    "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                                    "pdir_fid": parent_fid or "0", "_page": str(page),
                                    "_size": str(page_size), "_fetch_total": "1",
                                    "_fetch_sub_dirs": "0", "_sort": "file_type:asc,updated_at:desc",
                                },
                                headers=self.headers,
                            )
                            data = self._safe_json(response)
                            if response.status_code == 200:
                                break
                        except httpx.HTTPError:
                            response = None
                            data = {}
                    if response is not None and response.status_code == 200:
                        break
                    await asyncio.sleep(0.5)
                if response is None:
                    break
                rows = ((data.get("data") or {}).get("list") or [])
                if response.status_code != 200 or not rows:
                    break
                for row in rows:
                    if isinstance(row, dict):
                        item = self._item_from_row(row)
                        if item:
                            items.append(item)
                if len(rows) < page_size:
                    break
                page += 1
        return items[:limit]

    async def get_items(self, fids: list[str], parent_hint: str = "0") -> list[QuarkFileItem]:
        wanted = {str(fid) for fid in fids if str(fid).strip()}
        if not wanted:
            return []
        rows = await self.list_files(parent_hint or "0", limit=max(200, len(wanted) * 4))
        found = {item.fid: item for item in rows if item.fid in wanted}
        if len(found) < len(wanted):
            # The task may become visible shortly after status=2.
            await asyncio.sleep(1)
            rows = await self.list_files(parent_hint or "0", limit=max(200, len(wanted) * 4))
            found.update({item.fid: item for item in rows if item.fid in wanted})
        return [found[fid] for fid in fids if fid in found]

    async def get_or_create_folder(self, name: str, parent_fid: str = "0") -> str:
        normalized = name.strip()
        if not normalized:
            return ""
        for item in await self.list_files(parent_fid, limit=300):
            if item.is_dir and item.name == normalized:
                return item.fid
        result = await self.create_folder(normalized, parent_fid)
        return str((result.get("data") or {}).get("fid") or "")

    async def create_folder(self, name: str, parent_fid: str = "0") -> dict:
        return await self._post_file_action(
            "file",
            {"pdir_fid": parent_fid or "0", "file_name": name, "dir_path": "", "dir_init_lock": False},
        )

    async def rename_file(self, fid: str, new_name: str) -> dict:
        return await self._post_file_action("file/rename", {"fid": fid, "file_name": new_name})

    async def move_files(self, fids: list[str], target_fid: str) -> dict:
        data = await self._post_file_action(
            "file/move",
            {"action_type": 1, "to_pdir_fid": target_fid, "filelist": fids, "exclude_fids": []},
        )
        task_id = str((data.get("data") or {}).get("task_id") or "")
        if task_id:
            return await self.query_task(task_id, timeout=20)
        return data

    async def query_task(self, task_id: str, timeout: int = 30) -> dict:
        if not task_id:
            return {}
        deadline = asyncio.get_running_loop().time() + max(1, timeout)
        retry_index = 0
        last: dict = {}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(
                    f"{QUARK_API_BASES[0]}/task",
                    params={
                        "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                        "task_id": task_id, "retry_index": str(retry_index),
                    },
                    headers=self.headers,
                )
                last = self._safe_json(response)
                task_data = last.get("data") or {}
                status = task_data.get("status")
                if status == 2:
                    return last
                if status in {3, 4, -1}:
                    return last
                retry_index += 1
                await asyncio.sleep(0.6)
        return last

    async def save_share(self, share_url: str, passcode: str = "") -> QuarkSaveResult:
        if not self.cookie:
            return QuarkSaveResult(False, "夸克未登录，请发送“夸克登录”扫码", {})

        try:
            pwd_id, resolved_passcode = self.parse_share(share_url, passcode or self.default_passcode)
        except ValueError as exc:
            return QuarkSaveResult(False, str(exc), {})

        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            token_resp = await client.post(
                f"{QUARK_SHARE_API}/share/sharepage/token",
                params=params,
                headers=self.headers,
                json={"pwd_id": pwd_id, "passcode": resolved_passcode},
            )
            token_data = self._safe_json(token_resp)
            if token_resp.status_code != 200 or token_data.get("code") not in (0, None):
                return QuarkSaveResult(False, token_data.get("message") or "获取分享信息失败", token_data)
            stoken = (token_data.get("data") or {}).get("stoken")
            if not stoken:
                return QuarkSaveResult(False, "分享令牌为空，可能需要提取码或链接已失效", token_data)

            detail_resp = await client.get(
                f"{QUARK_SHARE_API}/share/sharepage/detail",
                params={**params, "pwd_id": pwd_id, "stoken": stoken, "pdir_fid": "0", "_page": "1", "_size": "100"},
                headers=self.headers,
            )
            detail_data = self._safe_json(detail_resp)
            files = ((detail_data.get("data") or {}).get("list") or [])
            if detail_resp.status_code != 200 or not files:
                return QuarkSaveResult(False, "分享为空、已失效或无法读取", detail_data)
            source_title = str(
                (detail_data.get("data") or {}).get("title")
                or (files[0].get("file_name") if isinstance(files[0], dict) else "")
                or ""
            )

            save_resp = await client.post(
                f"{QUARK_SHARE_API}/share/sharepage/save",
                params=params,
                headers=self.headers,
                json={
                    "fid_list": [item["fid"] for item in files],
                    "fid_token_list": [item.get("share_fid_token", "") for item in files],
                    "to_pdir_fid": self.target_fid,
                    "pwd_id": pwd_id,
                    "stoken": stoken,
                    "pdir_fid": "0",
                    "pdir_save_all": True,
                    "exclude_fids": [],
                    "scene": "link",
                },
            )
            save_data = self._safe_json(save_resp)
            code = save_data.get("code")
            ok = save_resp.status_code == 200 and code in (0, None)
            if not ok:
                return QuarkSaveResult(False, save_data.get("message") or "转存失败", save_data, source_title=source_title)

            task_id = str((save_data.get("data") or {}).get("task_id") or "")
            task_data = await self.query_task(task_id, timeout=35) if task_id else save_data
            saved_fids = self._saved_fids(task_data) or self._saved_fids(save_data)
            task_status = (task_data.get("data") or {}).get("status") if isinstance(task_data, dict) else None
            if task_id and task_status not in (2, None):
                message = "转存任务已提交，仍在处理中"
            else:
                message = save_data.get("message") or "转存完成"
            raw = {"save": save_data, "task": task_data, "detail": detail_data}
            return QuarkSaveResult(True, message, raw, saved_fids=saved_fids, source_title=source_title, task_id=task_id)

    async def _post_file_action(self, path: str, payload: dict) -> dict:
        if not self.cookie:
            return {"status": 401, "message": "夸克未登录"}
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response = await client.post(
                f"{QUARK_API_BASES[0]}/{path}",
                params={"pr": "ucpro", "fr": "pc", "uc_param_str": ""},
                headers=self.headers,
                json=payload,
            )
        return self._safe_json(response)

    @staticmethod
    def _saved_fids(data: dict) -> list[str]:
        if not isinstance(data, dict):
            return []
        body = data.get("data") or {}
        save_as = body.get("save_as") or {}
        values = save_as.get("save_as_top_fids") or body.get("save_as_top_fids") or []
        return [str(value) for value in values if str(value).strip()]

    @staticmethod
    def _item_from_row(row: dict) -> QuarkFileItem | None:
        name = str(row.get("file_name") or row.get("name") or "").strip()
        fid = str(row.get("fid") or "").strip()
        if not name or not fid:
            return None
        file_type = str(row.get("file_type") or "").lower()
        is_dir = bool(row.get("dir") or row.get("is_dir")) or file_type in {"folder", "dir", "directory"}
        try:
            size = int(row.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        path = str(row.get("file_path") or row.get("path") or "").strip()
        return QuarkFileItem(name=name, fid=fid, size=size, is_dir=is_dir, path=path, raw=row)

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except Exception:
            return {"status_code": response.status_code, "text": response.text[:500]}
