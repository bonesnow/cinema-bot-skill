---
name: cinema-bot
summary: Receive movie or TV requests, check the user's Quark drive first, then query explicitly configured authorized websites, APIs, or local catalogs and save only the highest-quality missing result.
description: Use when the user wants to find a movie or TV show, sends an authorized Quark share link, asks to save it, asks to QR-login or log out of Quark, or asks for cinema-bot status. Website sources must be explicitly configured, domain allowlisted, and authorized by the user. Never search magnets, torrents, piracy indexes, or bypass access controls.
---

# Cinema Bot Skill

## Configuration gate

Run before normal operation:

```bash
python -m app.website_check
python -m app.config_check
```

Values beginning with `__FILL_` are placeholders and must not be treated as valid configuration.

## Commands

```bash
python -m app.cli "我要看 星际穿越"
python -m app.cli "搜索 流浪地球2 4K"
python -m app.cli "https://pan.quark.cn/s/xxxx 提取码 1234"
python -m app.cli "夸克登录"
python -m app.cli "退出夸克"
python -m app.cli "状态"
```

## Workflow

1. Authenticate the bot channel and enforce the user allowlist.
2. Parse the request and remove quality hints from the drive lookup title.
3. For Quark login, generate a short-lived QR image, poll confirmation, and persist cookies.
4. Search the user's own Quark drive first.
5. If a matching title exists, report the highest-quality existing version and stop.
6. If missing, query enabled PanHub, JPMOM, HouTuPan, custom website, API, and/or local-catalog providers.
7. Built-in JPMOM and HouTuPan adapters use same-site heuristic parsing with HTTP-first and Playwright fallback; custom website sources still require `authorized: true` and a domain allowlist.
8. Reject non-Quark links, magnets, torrents, private-network targets by default, and unexpected redirect domains.
9. Deduplicate and rank by resolution, source, HDR, audio, codec, subtitles, relevance, and size.
10. Save only the highest-ranked result when `AUTO_SAVE=true` and `DRY_RUN=false`.
11. Never expose cookies, application secrets, access tokens, QR tokens, or website login credentials.

## Website modes

- Built-in JPMOM/HouTuPan: no CSS configuration; HTTP-first with Playwright fallback.
- `html`: configuration-driven HTTP and HTML parsing.
- `browser`: configuration-driven Playwright Chromium parsing.

Do not bypass CAPTCHAs, sliders, paywalls, authentication requirements, robots controls, or other access restrictions.


## Media library commands

- `整理 <片名>`: organize an existing Quark item.
- `整理网盘`: organize top-level items from the configured transfer folder.
- `刮削 <片名>`: inspect normalized metadata and classification.
- Successful transfers are automatically organized when `ORGANIZE_AFTER_SAVE=true`.
