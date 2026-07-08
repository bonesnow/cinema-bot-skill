from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .quark import QuarkClient, QuarkFileItem

VIDEO_EXTS = {"mkv", "mp4", "avi", "mov", "wmv", "m2ts", "ts", "webm", "strm"}
SUBTITLE_EXTS = {"srt", "ass", "ssa", "sub", "vtt", "sup"}
SCENE_TAGS = (
    r"\b(?:2160p|1080p|1080i|720p|480p|4k|uhd)\b",
    r"\b(?:web[- .]?dl|webrip|bluray|remux|bdremux|bdrip|hdtv)\b",
    r"\b(?:hdr10\+?|hdr|dolby[ .]?vision|dv)\b",
    r"\b(?:x26[45]|h\.?26[45]|hevc|avc|av1)\b",
    r"\b(?:atmos|truehd|dts(?:-hd)?|eac3|ddp?|aac)\b",
)
QUALITY_SPLIT_RE = re.compile(
    r"(?i)(?=\b(?:2160p|1080p|1080i|720p|480p|4k|uhd|web[- .]?dl|webrip|bluray|remux|bdremux|bdrip|hdtv|hdr10\+?|hdr|dolby[ .]?vision|dv|x26[45]|h\.?26[45]|hevc|avc|av1|atmos|truehd|dts(?:-hd)?|eac3|ddp?|aac)\b)"
)
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
SEASON_EPISODE_RE = re.compile(r"(?i)\bS(\d{1,2})(?:E(\d{1,3}))?\b")
CHINESE_SEASON_RE = re.compile(r"第\s*([一二三四五六七八九十百\d]+)\s*季")
CHINESE_EPISODE_RE = re.compile(r"第\s*(\d{1,3})\s*[集话期]")
MEDIA_TITLE_HINT_RE = re.compile(
    r"(?i)(?:"
    r"(?:19|20)\d{2}|"
    r"2160p|1080p|720p|4k|uhd|remux|bluray|web[- .]?dl|hdr|dv|"
    r"S\d{1,2}(?:E\d{1,3})?|"
    r"电影|影片|电视剧|剧集|全集|第\s*[一二三四五六七八九十百\d]+\s*季|第\s*\d{1,3}\s*[集话]|"
    r"动作|冒险|动画|喜剧|犯罪|纪录|剧情|家庭|奇幻|历史|恐怖|音乐|悬疑|爱情|科幻|惊悚|战争|传记|"
    r"中字|中英|双语|豆瓣"
    r")"
)
NON_MEDIA_TITLE_HINT_RE = re.compile(
    r"(?:简历|述职|报告|ppt|pptx|pdf|表格|xlsx|docx|文档|扫描|备份|快传|课程|讲义|真题|试卷|三支一扶|公基|行测|申论|时政|题库|夸克文档|文档工具)",
    re.I,
)

GENRE_MAP = {
    "Action": "动作", "Adventure": "冒险", "Animation": "动画",
    "Comedy": "喜剧", "Crime": "犯罪", "Documentary": "纪录片",
    "Drama": "剧情", "Family": "家庭", "Fantasy": "奇幻",
    "History": "历史", "Horror": "恐怖", "Music": "音乐",
    "Mystery": "悬疑", "Romance": "爱情", "Sci-Fi": "科幻",
    "Science Fiction": "科幻", "Thriller": "惊悚", "War": "战争",
    "Western": "西部", "Biography": "传记", "Sport": "运动",
    "Reality-TV": "真人秀", "Talk-Show": "脱口秀",
}

CHINESE_GENRE_HINTS = (
    ("科幻", "科幻"),
    ("悬疑", "悬疑"),
    ("惊悚", "惊悚"),
    ("恐怖", "恐怖"),
    ("犯罪", "犯罪"),
    ("动作", "动作"),
    ("冒险", "冒险"),
    ("奇幻", "奇幻"),
    ("动画", "动画"),
    ("喜剧", "喜剧"),
    ("爱情", "爱情"),
    ("剧情", "剧情"),
    ("战争", "战争"),
    ("历史", "历史"),
    ("纪录", "纪录片"),
    ("传记", "传记"),
    ("音乐", "音乐"),
    ("家庭", "家庭"),
)


def _cn_number(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if value in digits:
        return digits[value]
    if value.startswith("十"):
        return 10 + digits.get(value[1:], 0)
    if "十" in value:
        left, _, right = value.partition("十")
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return 1


def clean_display_name(name: str) -> str:
    name = os.path.basename(name or "")
    name = re.sub(r"\.(?:mkv|mp4|avi|mov|wmv|m2ts|ts|webm|strm|srt|ass|ssa|sub|vtt|sup)$", "", name, flags=re.I)
    name = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE00-\uFE0F]", "", name)
    name = re.sub(r"[\[【].*?[\]】]", " ", name)
    name = re.sub(r"^[#\s]*(?:电影资源标题|电影名称|电视剧名称|名称|资源标题|标题|电影|片名)[：:]?\s*", "", name)
    name = QUALITY_SPLIT_RE.split(name, maxsplit=1)[0]
    name = re.sub(r"\bS\d{1,2}(?:E\d{1,3})?\b", " ", name, flags=re.I)
    name = CHINESE_SEASON_RE.sub(" ", name)
    name = CHINESE_EPISODE_RE.sub(" ", name)
    name = re.sub(r"\s*[（(]?(?:19|20)\d{2}[）)]?\s*$", "", name)
    name = re.sub(r"(?:夸克网盘|百度网盘|迅雷云盘|网盘链接|链接)\s*$", "", name)
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -—·：:，,。")
    return name or "未识别影视"


def is_scene_name(filename: str) -> bool:
    return sum(bool(re.search(pattern, filename, re.I)) for pattern in SCENE_TAGS) >= 2


def infer_chinese_genre(text: str) -> str:
    for marker, genre in CHINESE_GENRE_HINTS:
        if marker in text:
            return genre
    return "其他"


def should_query_omdb(title: str) -> bool:
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", title))
    has_latin_word = bool(re.search(r"[A-Za-z]{3,}", title))
    return (not has_cjk) or has_latin_word


def is_media_title(text: str) -> bool:
    if not text:
        return False
    if NON_MEDIA_TITLE_HINT_RE.search(text):
        return False
    return bool(MEDIA_TITLE_HINT_RE.search(text))


@dataclass(slots=True)
class MediaInfo:
    title: str
    year: str = ""
    content_type: str = "movie"
    season: int = 1
    episode: int = 0
    source_text: str = ""

    @property
    def folder_name(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass(slots=True)
class MetadataRecord:
    title: str
    year: str = ""
    genre: str = "其他"
    category: str = ""
    plot: str = ""
    imdb_id: str = ""
    content_type: str = "movie"
    source: str = "inference"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LibraryResult:
    ok: bool
    message: str
    path: str = ""
    genre: str = "其他"
    moved_fids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def parse_media_info(text: str, content_type_hint: str = "auto") -> MediaInfo:
    raw = text or ""
    year_match = YEAR_RE.search(raw)
    year = year_match.group(1) if year_match else ""

    season = 1
    episode = 0
    se_match = SEASON_EPISODE_RE.search(raw)
    if se_match:
        season = int(se_match.group(1))
        episode = int(se_match.group(2) or 0)
    else:
        season_match = CHINESE_SEASON_RE.search(raw)
        episode_match = CHINESE_EPISODE_RE.search(raw)
        if season_match:
            season = _cn_number(season_match.group(1))
        if episode_match:
            episode = int(episode_match.group(1))

    tv_marked = bool(
        se_match
        or CHINESE_SEASON_RE.search(raw)
        or CHINESE_EPISODE_RE.search(raw)
        or re.search(r"电视剧|剧集|全集|全\d+集|season\s*\d+|episode\s*\d+", raw, re.I)
    )
    content_type = content_type_hint if content_type_hint in {"movie", "tv"} else ("tv" if tv_marked else "movie")

    title = clean_display_name(raw)
    if year_match:
        leading_title = clean_display_name(raw[: year_match.start()])
        if leading_title and leading_title != "未识别影视" and not NON_MEDIA_TITLE_HINT_RE.search(leading_title):
            title = leading_title
    if year:
        title = re.sub(rf"\s*[（(]?{re.escape(year)}[）)]?\s*", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
    title = title.strip(" -—·：:，,。()（）")
    return MediaInfo(
        title=title or "未识别影视",
        year=year,
        content_type=content_type,
        season=season,
        episode=episode,
        source_text=raw,
    )


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def classify_nastool_category(info: MediaInfo, record: MetadataRecord) -> str:
    raw = record.raw or {}
    genre_text = " ".join(
        str(value or "")
        for value in (record.genre, raw.get("Genre"), info.source_text, info.title)
    )
    country_text = " ".join(
        str(value or "")
        for value in (raw.get("Country"), raw.get("Production"), info.source_text)
    )
    language_text = " ".join(str(value or "") for value in (raw.get("Language"), info.source_text))

    animation = _has_any(genre_text, ("Animation", "动画", "动漫", "anime"))
    documentary = _has_any(genre_text, ("Documentary", "纪录"))
    child = _has_any(genre_text, ("Family", "儿童", "少儿"))
    variety = _has_any(genre_text, ("Reality-TV", "Talk-Show", "Game-Show", "综艺", "真人秀", "脱口秀"))
    chinese_area = _has_any(
        country_text + " " + language_text,
        ("China", "Hong Kong", "Taiwan", "Mandarin", "Cantonese", "Chinese", "中国", "大陆", "内地", "香港", "台湾", "华语", "国产"),
    )
    western_area = _has_any(
        country_text,
        ("United States", "USA", "U.S.", "America", "美国", "United Kingdom", "UK", "英国", "France", "法国", "Germany", "德国", "Spain", "西班牙", "Italy", "意大利", "Netherlands", "荷兰", "Portugal", "葡萄牙", "Russia", "俄罗斯", "欧美"),
    )
    east_asia_area = _has_any(
        country_text,
        ("Japan", "日本", "Korea", "South Korea", "韩国", "Thailand", "泰国", "India", "印度", "Singapore", "新加坡", "日韩"),
    )

    if info.content_type == "tv":
        if animation:
            return "动漫"
        if documentary:
            return "纪录片"
        if child:
            return "儿童"
        if variety:
            return "综艺"
        if chinese_area:
            return "国产剧"
        if western_area:
            return "欧美剧"
        if east_asia_area:
            return "日韩剧"
        return "未分类"

    # Mirror NAStool's default-category idea: language/area first, animation
    # next, then foreign movies as the catch-all.
    if chinese_area:
        return "华语电影"
    if animation:
        return "动画电影"
    return "外语电影"


class MetadataScraper:
    """Small OMDb-backed classifier used for folder naming and genre grouping.

    This mirrors the original cinema-manager's scope: metadata is used to classify
    and name the cloud-drive library. Plex/Jellyfin/Infuse perform their own rich
    poster/NFO scraping after the media path is standardized.
    """

    def __init__(self, omdb_api_key: str = "", cache_path: str = "/data/metadata_cache.json"):
        self.api_key = (omdb_api_key or "").strip()
        self.cache_path = Path(cache_path) if cache_path else None
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        self._cache = {}
        if self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._cache = data
            except (OSError, json.JSONDecodeError):
                pass
        return self._cache

    def _save_cache(self) -> None:
        if not self.cache_path or self._cache is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.cache_path)
        except OSError:
            pass

    async def lookup(self, info: MediaInfo) -> MetadataRecord:
        key = f"{info.content_type}:{info.title}:{info.year}".lower()
        cached = self._load_cache().get(key)
        if isinstance(cached, dict):
            return MetadataRecord(
                title=str(cached.get("title") or info.title),
                year=str(cached.get("year") or info.year),
                genre=str(cached.get("genre") or "其他"),
                category=str(cached.get("category") or ""),
                plot=str(cached.get("plot") or ""),
                imdb_id=str(cached.get("imdb_id") or ""),
                content_type=str(cached.get("content_type") or info.content_type),
                source=str(cached.get("source") or "cache"),
                raw=cached.get("raw") if isinstance(cached.get("raw"), dict) else {},
            )

        record = MetadataRecord(
            title=info.title,
            year=info.year,
            content_type=info.content_type,
        )
        inferred_genre = infer_chinese_genre(info.title)
        if inferred_genre != "其他":
            record.genre = inferred_genre
        record.category = classify_nastool_category(info, record)
        if not self.api_key:
            return record
        if not should_query_omdb(info.title):
            return record

        params = {
            "apikey": self.api_key,
            "t": info.title,
            "plot": "short",
            "r": "json",
        }
        if info.year:
            params["y"] = info.year
        if info.content_type == "movie":
            params["type"] = "movie"
        elif info.content_type == "tv":
            params["type"] = "series"

        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                response = await client.get("https://www.omdbapi.com/", params=params)
            data = response.json() if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            data = {}

        if isinstance(data, dict) and data.get("Response") == "True":
            first_genre = str(data.get("Genre") or "").split(",")[0].strip()
            record = MetadataRecord(
                title=str(data.get("Title") or info.title).strip(),
                year=str(data.get("Year") or info.year).split("–")[0].strip(),
                genre=GENRE_MAP.get(first_genre, first_genre or "其他"),
                plot=str(data.get("Plot") or "").strip(),
                imdb_id=str(data.get("imdbID") or "").strip(),
                content_type="tv" if str(data.get("Type") or "").lower() in {"series", "episode"} else info.content_type,
                source="omdb",
                raw=data,
            )
            record.category = classify_nastool_category(info, record)
            self._load_cache()[key] = {
                "title": record.title,
                "year": record.year,
                "genre": record.genre,
                "category": record.category,
                "plot": record.plot,
                "imdb_id": record.imdb_id,
                "content_type": record.content_type,
                "source": record.source,
                "raw": record.raw,
            }
            self._save_cache()
        else:
            record.category = classify_nastool_category(info, record)
        return record


class LibraryManager:
    def __init__(
        self,
        quark: QuarkClient,
        *,
        root_name: str = "夸克影视",
        root_fid: str = "",
        genre_folders: bool = True,
        keep_scene_names: bool = True,
        metadata: MetadataScraper | None = None,
    ):
        self.quark = quark
        self.root_name = clean_display_name(root_name) or "夸克影视"
        self.root_fid = (root_fid or "").strip()
        self.genre_folders = genre_folders
        self.keep_scene_names = keep_scene_names
        self.metadata = metadata or MetadataScraper()
        self._resolved_root_fid = ""

    def should_batch_organize(self, item: QuarkFileItem) -> bool:
        if item.name == self.root_name:
            return False
        if NON_MEDIA_TITLE_HINT_RE.search(item.name):
            return False
        return is_media_title(item.name) or (not item.is_dir and self._ext(item.name) in VIDEO_EXTS)

    async def ensure_root(self) -> str:
        if self.root_fid:
            return self.root_fid
        if self._resolved_root_fid:
            return self._resolved_root_fid
        self._resolved_root_fid = await self.quark.get_or_create_folder(self.root_name, "0")
        return self._resolved_root_fid

    async def organize(
        self,
        saved_fids: list[str],
        source_title: str,
        *,
        content_type_hint: str = "auto",
        parent_hint: str | None = None,
    ) -> LibraryResult:
        fids = [str(fid) for fid in saved_fids if str(fid).strip()]
        if not fids:
            return LibraryResult(False, "未取得已转存文件的 FID，无法自动整理")

        items = await self.quark.get_items(fids, parent_hint=parent_hint or self.quark.target_fid)
        if not items:
            return LibraryResult(False, "转存已完成，但暂时无法读取已保存文件；可稍后发送“整理 片名”重试")
        if not await self._looks_like_media(items, source_title):
            return LibraryResult(False, "未检测到影视文件或影视标题，已跳过整理")

        info = parse_media_info(source_title or items[0].name, content_type_hint)
        metadata = await self.metadata.lookup(info)
        if info.title == "未识别影视" and metadata.title and metadata.source == "omdb":
            info.title = clean_display_name(metadata.title)
        if metadata.year and not info.year:
            info.year = metadata.year
        if metadata.content_type in {"movie", "tv"}:
            info.content_type = metadata.content_type

        root_id = await self.ensure_root()
        if not root_id:
            return LibraryResult(False, "无法创建或读取媒体库根目录")

        parent_id = root_id
        genre = metadata.category or classify_nastool_category(info, metadata)
        media_root = "电视剧" if info.content_type == "tv" else "电影"
        if self.genre_folders:
            type_id = await self.quark.get_or_create_folder(media_root, root_id)
            parent_id = await self.quark.get_or_create_folder(genre, type_id or root_id)
            if not parent_id:
                parent_id = type_id or root_id

        if info.content_type == "tv":
            return await self._organize_tv(items, info, genre, parent_id)
        return await self._organize_movie(items, info, genre, parent_id)

    async def _looks_like_media(self, items: list[QuarkFileItem], source_title: str) -> bool:
        names = " ".join([source_title] + [item.name for item in items])
        if NON_MEDIA_TITLE_HINT_RE.search(names):
            return False
        if is_media_title(names):
            return True
        if any((not item.is_dir) and self._ext(item.name) in VIDEO_EXTS for item in items):
            return True
        for item in items:
            if not item.is_dir:
                continue
            children = await self.quark.list_files(item.fid, limit=80)
            if any((not child.is_dir) and self._ext(child.name) in VIDEO_EXTS for child in children):
                return True
        return False

    async def _organize_movie(
        self, items: list[QuarkFileItem], info: MediaInfo, genre: str, parent_id: str
    ) -> LibraryResult:
        folder_name = info.folder_name
        if len(items) == 1 and items[0].is_dir:
            item = items[0]
            if item.name != folder_name:
                await self.quark.rename_file(item.fid, folder_name)
            await self.quark.move_files([item.fid], parent_id)
            return LibraryResult(
                True,
                "已按电影规则整理",
                path=self._path(genre, folder_name),
                genre=genre,
                moved_fids=[item.fid],
            )

        folder_id = await self.quark.get_or_create_folder(folder_name, parent_id)
        if not folder_id:
            return LibraryResult(False, f"无法创建电影目录：{folder_name}")

        video_items = [item for item in items if self._ext(item.name) in VIDEO_EXTS]
        primary = video_items[0] if len(video_items) == 1 else None
        for item in items:
            ext = self._ext(item.name)
            if not item.is_dir and primary and item.fid == primary.fid:
                if not (self.keep_scene_names and is_scene_name(item.name)):
                    await self.quark.rename_file(item.fid, f"{folder_name}.{ext or 'mkv'}")
            elif not item.is_dir and primary and ext in SUBTITLE_EXTS and not is_scene_name(item.name):
                await self.quark.rename_file(item.fid, f"{folder_name}.{ext}")
        await self.quark.move_files([item.fid for item in items], folder_id)
        return LibraryResult(
            True,
            "已按电影规则整理",
            path=self._path(genre, folder_name),
            genre=genre,
            moved_fids=[item.fid for item in items],
        )

    async def _organize_tv(
        self, items: list[QuarkFileItem], info: MediaInfo, genre: str, parent_id: str
    ) -> LibraryResult:
        show_name = info.folder_name
        show_id = await self.quark.get_or_create_folder(show_name, parent_id)
        if not show_id:
            return LibraryResult(False, f"无法创建剧集目录：{show_name}")
        season_name = f"Season {info.season:02d}"

        if len(items) == 1 and items[0].is_dir:
            item = items[0]
            if item.name != season_name:
                await self.quark.rename_file(item.fid, season_name)
            await self.quark.move_files([item.fid], show_id)
            return LibraryResult(
                True,
                "已按剧集规则整理",
                path=self._path(genre, show_name, season_name),
                genre=genre,
                moved_fids=[item.fid],
            )

        season_id = await self.quark.get_or_create_folder(season_name, show_id)
        if not season_id:
            return LibraryResult(False, f"无法创建季度目录：{season_name}")
        for item in items:
            ext = self._ext(item.name)
            if item.is_dir or ext not in VIDEO_EXTS:
                continue
            if not (self.keep_scene_names and is_scene_name(item.name)):
                episode = info.episode or self._episode_from_name(item.name)
                if episode:
                    await self.quark.rename_file(
                        item.fid,
                        f"{info.title} - S{info.season:02d}E{episode:02d}.{ext or 'mkv'}",
                    )
        await self.quark.move_files([item.fid for item in items], season_id)
        return LibraryResult(
            True,
            "已按剧集规则整理",
            path=self._path(genre, show_name, season_name),
            genre=genre,
            moved_fids=[item.fid for item in items],
        )

    def _path(self, genre: str, *parts: str) -> str:
        prefix = [self.root_name]
        if self.genre_folders:
            media_root = "电视剧" if len(parts) >= 2 else "电影"
            prefix.append(media_root)
            prefix.append(genre)
        return "/".join(prefix + list(parts))

    @staticmethod
    def _ext(name: str) -> str:
        return name.rsplit(".", 1)[-1].lower() if "." in name else ""

    @staticmethod
    def _episode_from_name(name: str) -> int:
        match = SEASON_EPISODE_RE.search(name)
        if match and match.group(2):
            return int(match.group(2))
        match = CHINESE_EPISODE_RE.search(name)
        return int(match.group(1)) if match else 0
