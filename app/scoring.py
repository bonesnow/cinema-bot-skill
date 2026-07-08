from __future__ import annotations

from .models import ResourceResult

QUALITY_SCORES = {
    "2160p": 100,
    "4k": 100,
    "uhd": 100,
    "1080p": 55,
    "1080i": 45,
    "720p": 20,
    "480p": 5,
}
SOURCE_SCORES = {
    "remux": 100,
    "bluray": 90,
    "bdrip": 80,
    "web-dl": 70,
    "webdl": 70,
    "webrip": 65,
    "hdtv": 40,
    "cam": -100,
}
HDR_SCORES = {
    "dolby vision": 30,
    "dolby.vision": 30,
    " dv ": 30,
    "hdr10+": 25,
    "hdr10": 20,
    "hdr": 15,
}
AUDIO_SCORES = {
    "atmos": 15,
    "truehd": 12,
    "dts-hd": 10,
    "dts": 8,
    "eac3": 7,
    "ddp": 7,
    "ac3": 3,
    "aac": 2,
}
CODEC_SCORES = {"h265": 10, "hevc": 10, "x265": 10, "h264": 5, "x264": 5}
SUBTITLE_KEYWORDS = ("字幕", "subtitle", "chs", "cht", "中英", "中字", "双语")


def _first_match_score(text: str, table: dict[str, int]) -> int:
    return next((value for key, value in table.items() if key in text), 0)


def score_resource(resource: ResourceResult) -> int:
    text = f" {resource.searchable_text()} "
    score = sum(
        _first_match_score(text, table)
        for table in (QUALITY_SCORES, SOURCE_SCORES, HDR_SCORES, AUDIO_SCORES, CODEC_SCORES)
    )
    if any(keyword in text for keyword in SUBTITLE_KEYWORDS):
        score += 5
    if "pan.quark.cn/s/" in resource.share_url:
        score += 15
    return score
