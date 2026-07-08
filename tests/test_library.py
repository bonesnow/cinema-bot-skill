import asyncio

from app.library import LibraryManager, LibraryResult, MetadataScraper, parse_media_info
from app.quark import QuarkFileItem


class FakeQuark:
    target_fid = "inbox"

    def __init__(self):
        self.folders = {("0", "夸克影视"): "root"}
        self.items = {
            "movie1": QuarkFileItem(
                "星际穿越.2014.超清中字.mkv", "movie1", 10, False, raw={"pdir_fid": "inbox"}
            )
        }
        self.renames = []
        self.moves = []

    async def get_items(self, fids, parent_hint="0"):
        return [self.items[fid] for fid in fids if fid in self.items]

    async def get_or_create_folder(self, name, parent_fid="0"):
        key = (parent_fid, name)
        if key not in self.folders:
            self.folders[key] = f"folder-{len(self.folders)}"
        return self.folders[key]

    async def rename_file(self, fid, new_name):
        self.renames.append((fid, new_name))
        return {"code": 0}

    async def move_files(self, fids, target_fid):
        self.moves.append((list(fids), target_fid))
        return {"code": 0}


def test_parse_movie_and_tv_info():
    movie = parse_media_info("星际穿越 2014 2160p REMUX HDR")
    assert movie.title == "星际穿越"
    assert movie.year == "2014"
    assert movie.content_type == "movie"

    tv = parse_media_info("庆余年 第二季 S02E03 2160p WEB-DL")
    assert tv.title == "庆余年"
    assert tv.content_type == "tv"
    assert tv.season == 2
    assert tv.episode == 3


def test_movie_is_organized_into_compatible_library_path(tmp_path):
    quark = FakeQuark()
    manager = LibraryManager(
        quark,
        root_name="夸克影视",
        metadata=MetadataScraper(cache_path=str(tmp_path / "metadata.json")),
    )

    result = asyncio.run(
        manager.organize(["movie1"], "星际穿越 2014 2160p REMUX", parent_hint="inbox")
    )

    assert result.ok
    assert result.path == "夸克影视/电影/外语电影/星际穿越 (2014)"
    assert quark.renames == [("movie1", "星际穿越 (2014).mkv")]
    movie_root = quark.folders[("root", "电影")]
    foreign_movie = quark.folders[(movie_root, "外语电影")]
    destination = quark.folders[(foreign_movie, "星际穿越 (2014)")]
    assert quark.moves == [(["movie1"], destination)]
