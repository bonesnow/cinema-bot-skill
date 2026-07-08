# Changelog

## 6.0.0 - 2026-07-08

- 补回原始 cinema-manager 的媒体库整理链路。
- 夸克转存后轮询任务并提取 `save_as_top_fids`。
- 新增夸克目录列举、创建目录、重命名和移动操作。
- 自动识别电影、电视剧、年份、季度和集数。
- 电影按 `片名 (年份)`，剧集按 `剧名/Season XX` 整理。
- 规范片源文件名可保留，杂乱名称自动标准化。
- 新增 OMDb 分类刮削和本地元数据缓存。
- 新增飞书指令：`整理 片名`、`整理网盘`、`刮削 片名`。
- 新增 `configure_library.sh` 和媒体库说明文档。
- 公开发布版本移除个人部署模板、真实资源站配置和具体站点接入文档。
- 测试增至 31 项。


## 5.4.0

- 新增 JPMOM 内置适配器，使用 `/?s=关键词` 搜索并自动识别文章详情页。
- 新增 HouTuPan 内置适配器，自动尝试多种常见搜索路径。
- 两个适配器均采用 HTTP 优先、Playwright 浏览器回退。
- 无需填写 CSS 选择器，只返回直接夸克分享链接。
- 自动提取标题、画质关键词、文件大小和提取码。
- 新增 `python -m app.site_test "片名"` 独立联调命令。
- 单个站点失败不会影响 PanHub 或其他 Provider。
- 测试总数增加到 27 项。

# 5.2.0

## 5.2.1

- 支持无需自有域名的临时公网主机名部署。
- DuckDNS 容器改为可选 profile。

- 飞书回调同时兼容 `/webhook/feishu` 和 `/webhooks/feishu`。
- 适配已经在飞书后台填写单数路径的部署。


- 新增 `scripts/configure_feishu.sh`，在 VPS 上无回显输入 App Secret 和 Verification Token。
- 自动将 `.env` 权限设为 `600`。
- 新增飞书凭证安全配置说明。
- 不在项目包中保存已暴露的 App Secret。

# Changelog

## v5 — Website adapter integration

- Add configuration-driven resource website providers.
- Add lightweight HTML parsing with CSS selectors.
- Add optional Playwright Chromium mode for JavaScript-rendered pages.
- Add search-page and detail-page Quark-link extraction.
- Add strict allowed-domain validation and private-network blocking by default.
- Require explicit `authorized: true` for every enabled website.
- Add optional per-site Cookie environment variables and browser storage state.
- Add `websites.example.yaml` with every user-supplied field highlighted.
- Add `python -m app.website_check` and `python -m app.website_test`.
- Integrate website results with existing deduplication, quality ranking, and Quark saving.
- Expand tests from 12 to 17 passing tests.

## v4 — Planned framework and highlighted configuration

- Add complete architecture and staged deployment documentation.
- Add safe configuration checks and highlighted placeholders.

## v3 — Quark QR-code login

- Add QR login, status polling, persisted cookies, and bot-delivered QR images.

## v2 — Drive-first workflow

- Search the user's Quark drive first and stop on an existing match.
- Rank and save only the highest-quality missing result.

## 5.1.0

- 新增仅有 VPS、没有自有域名的部署模式。
- 新增 DuckDNS 自动 IP 更新容器。
- 新增 Caddy 自动 HTTPS 反向代理。
- 新增 `docker-compose.vps.yml`、`Caddyfile` 和 VPS 配置检查脚本。
- 新增 `docs/07_VPS无域名部署.md`。
- 飞书固定回调地址格式：`https://<subdomain>.duckdns.org/webhooks/feishu`。

## 5.3.0

- 新增 PanHub 专用 JSON Provider。
- 支持 PanHub 专用 JSON Provider，本地填写实例地址后使用。
- PanHub 请求仅启用 `pansearch`，并限制为夸克链接。
- 支持 PanHub 可选密码门 Cookie。
- 自动读取 PanHub 返回的提取码并用于夸克转存。
- `websites.yaml` 在已配置 PanHub 时改为可选。
- DuckDNS 容器改为可选 profile，无 DuckDNS 时不再默认启动。
- 测试总数增加到 21 项。
