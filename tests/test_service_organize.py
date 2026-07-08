import asyncio

from app.library import LibraryResult
from app.quark import QuarkSaveResult, QuarkSearchResult
from app.service import MediaService
from tests.test_workflow import ResultProvider, make_settings


class SavingQuark:
    is_authenticated = True

    async def search_files(self, keyword: str, limit: int = 100):
        return QuarkSearchResult(True, "ok", [], {})

    async def save_share(self, share_url: str, passcode: str = ""):
        return QuarkSaveResult(
            True,
            "转存完成",
            {},
            saved_fids=["fid1"],
            source_title="星际穿越 2014",
        )


class FakeLibrary:
    def __init__(self):
        self.calls = []

    async def organize(self, fids, title, parent_hint="0"):
        self.calls.append((list(fids), title, parent_hint))
        return LibraryResult(
            True,
            "已按电影规则整理",
            path="夸克影视/电影/外语电影/星际穿越 (2014)",
            genre="外语电影",
        )


def test_successful_save_is_followed_by_library_organization():
    service = MediaService(make_settings())
    service.providers = [ResultProvider()]
    service.quark = SavingQuark()
    service.library = FakeLibrary()

    reply = asyncio.run(service.handle("我要看 星际穿越 4K"))

    assert service.library.calls == [
        (["fid1"], "星际穿越 2014 2160p REMUX HDR Atmos 中英字幕", "target")
    ]
    assert "转存完成" in reply
    assert "已完成自动刮削与媒体库整理" in reply
    assert "夸克影视/电影/外语电影/星际穿越 (2014)" in reply
