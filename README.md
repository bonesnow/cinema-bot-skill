# Cinema Bot

飞书点片机器人：先查自己的夸克网盘，没有命中时再查询你配置的授权资源源，选择画质评分最高的夸克链接，转存后自动刮削并整理为媒体库目录。

> 本仓库不包含真实资源站配置、Cookie、夸克登录态、飞书密钥或个人 VPS 信息。所有私有配置只放在本机 `.env` 和 `data/` 目录，默认被 Git 忽略。

## 功能

- 飞书机器人接收 `我要看 片名`、`状态`、`夸克登录` 等指令。
- 夸克扫码登录，登录态保存到 `/data/quark_auth.json`。
- 先搜索自己的夸克网盘，已有资源时直接回复。
- 未命中时查询授权资源源：自建 JSON API、本地目录或你本地配置的网站。
- 可直接在聊天里发送 `配置资源站 https://example.com` 添加网站。
- 按 4K、REMUX、HDR、音轨、字幕等信息给候选资源评分。
- 转存成功后自动定位保存文件、刮削元数据并整理到媒体库目录。
- 支持 Docker Compose、VPS 反向代理和健康检查。

## 媒体库结构

默认根目录为 `夸克影视`：

```text
夸克影视/
├── 电影/
│   ├── 华语电影/
│   ├── 外语电影/
│   └── 动画电影/
└── 电视剧/
    ├── 国产剧/
    ├── 欧美剧/
    ├── 日韩剧/
    ├── 动漫/
    ├── 纪录片/
    ├── 综艺/
    ├── 儿童/
    └── 未分类/
```

保存完成后的主流程是：

```text
飞书点片
  -> 搜索夸克网盘
  -> 搜索授权资源源
  -> 选择最高分候选
  -> 转存
  -> 自动刮削
  -> 自动归类整理
  -> 回复最终媒体库路径
```

手动 `刮削`、`整理`、`整理网盘` 只用于维护或补救，不是日常主流程。

## 部署方式怎么选

优先按你的条件选一条路：

| 你的条件 | 推荐入口 | 适合什么 |
|---|---|---|
| 没有 VPS，也没有域名 | `./scripts/local_qa.sh` | 直接在电脑终端问答，不接飞书 |
| 没有 VPS，但想在本机跑服务 | `./scripts/deploy_local.sh` | 本机调试 API；需要公网 HTTPS 才能接飞书 |
| 有 VPS | `./scripts/deploy_vps.sh` | Docker 一键部署；有域名时自动带 Caddy |

最简单的本地问答：

```bash
git clone https://github.com/bonesnow/cinema-bot-skill.git
cd cinema-bot-skill
./scripts/local_qa.sh
```

脚本会自动：

- 创建 `.env`
- 创建 `data/catalog.json`
- 创建 Python 虚拟环境
- 安装依赖
- 进入本地问答模式

没有 VPS、没有域名时，就使用这个模式。它不需要飞书回调，也不需要公网 HTTPS。

添加资源站也只需要在问答里发送：

```text
配置资源站 https://你的资源站.example
```

常用管理命令：

```text
资源站列表
删除资源站 https://你的资源站.example
清空资源站
```

也可以用脚本一次性写入多个网址：

```bash
./scripts/configure_sources.sh https://你的资源站.example
```

脚本会生成 `data/websites.yaml`，并把 `.env` 里的 `WEBSITE_CONFIG_PATH` 配好。只有在自动识别失败时，才需要看高级 CSS 配置。

本地服务模式：

```bash
./scripts/deploy_local.sh
```

启动后访问：

```text
http://127.0.0.1:8000/healthz
```

VPS 模式：

```bash
./scripts/deploy_vps.sh
```

如果 `.env` 中填写了 `PUBLIC_HOST`，脚本会使用 Docker Compose + Caddy 启动 HTTPS 反向代理；否则只启动绑定到 `127.0.0.1:8000` 的应用服务。

## 手动配置

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，至少填写：

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ALLOWED_OPEN_IDS=
```

再配置至少一种资源源：

```env
# 自建或有权使用的 JSON API
PROVIDER_API_URLS=
PROVIDER_API_TOKEN=

# 或本地合法目录
LOCAL_CATALOG_PATH=/data/catalog.json
```

如果使用本地目录：

```bash
mkdir -p data
cp catalog.example.json data/catalog.json
```

手动启动：

```bash
docker compose up -d --build cinema-bot
docker compose run --rm cinema-bot python -m app.config_check
```

本地健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

生产环境建议只把 `127.0.0.1:8000` 暴露给 Nginx 或 Caddy，由 HTTPS 反向代理对外提供飞书回调。

## 飞书联调

飞书事件回调地址：

```text
https://你的域名/webhooks/feishu
```

机器人权限至少需要：

- 接收群聊或单聊文本消息；
- 发送文本消息；
- 发送图片，用于夸克扫码登录二维码。

飞书里依次发送：

```text
状态
配置资源站 https://你的资源站.example
资源站列表
夸克登录
我要看 星际穿越
```

首次联调保持：

```env
DRY_RUN=true
AUTO_SAVE=true
```

确认搜索、评分、回复都正常后，再改为真实转存：

```env
DRY_RUN=false
```

然后重启：

```bash
docker compose restart cinema-bot
```

## 资源源

公开仓库不会保存真实资源站配置。你可以在自己的 VPS 上选择一种或多种方式：

- `配置资源站 https://资源站`：推荐，直接在飞书、本地问答或其他聊天入口发送。
- `PROVIDER_API_URLS`：你维护或有权使用的 JSON 搜索 API。
- `LOCAL_CATALOG_PATH`：本地 JSON 目录，适合小规模自用。
- `./scripts/configure_sources.sh https://资源站`：只输入网址，使用通用启发式适配器。
- `WEBSITE_CONFIG_PATH=/data/websites.yaml`：你本地填写的网站配置，必须显式设置 `authorized: true`。
- 可选站点适配器：仅在你有权访问、且站点允许自动化检索时，在 `.env` 中自行填写地址和 Cookie。

不要提交：

- `.env`
- `data/websites.yaml`
- `data/quark_auth.json`
- `data/site-auth/`
- 任何 Cookie、Token、App Secret、资源站账号或个人部署状态

## 常用命令

```bash
# 没有 VPS/域名：本地问答
./scripts/local_qa.sh

# 本机运行服务
./scripts/deploy_local.sh

# VPS 一键部署
./scripts/deploy_vps.sh

# 配置检查，不会打印密钥
docker compose run --rm cinema-bot python -m app.config_check

# 测试资源搜索，不会转存
docker compose run --rm cinema-bot python -m app.site_test "星际穿越"

# 测试网站配置
docker compose run --rm cinema-bot python -m app.website_check

# 运行测试
python -m pytest
```

## 文档

- [整体架构](docs/01_整体架构规划.md)
- [飞书接入](docs/02_飞书接入步骤.md)
- [资源 API 规范](docs/03_资源API接口规范.md)
- [自定义网站接入](docs/03_资源网站接入步骤.md)
- [反向代理](docs/05_反向代理示例.md)
- [VPS 部署](docs/07_VPS无域名部署.md)
- [部署方式](docs/12_部署方式.md)
- [媒体库整理和分类刮削](docs/11_媒体库整理和分类刮削.md)
- [安全说明](SECURITY.md)

## 许可

见 [LICENSE](LICENSE)。
