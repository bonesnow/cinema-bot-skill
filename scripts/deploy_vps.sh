#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ 未找到 Docker。请先安装 Docker Engine 和 docker compose。" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "❌ 当前 Docker 不支持 compose 子命令。" >&2
  exit 1
fi

mkdir -p data
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi
if [[ ! -f data/catalog.json ]]; then
  cp catalog.example.json data/catalog.json
fi

set_env() {
  local key="$1" value="$2"
  python3 - "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(".env")
key, value = sys.argv[1], sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
out, found = [], False
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

current_quark_auth="$(grep -E '^QUARK_AUTH_FILE=' .env | tail -1 | cut -d= -f2- || true)"
case "$current_quark_auth" in ""|data/*) set_env QUARK_AUTH_FILE /data/quark_auth.json ;; esac

current_metadata="$(grep -E '^METADATA_CACHE_PATH=' .env | tail -1 | cut -d= -f2- || true)"
case "$current_metadata" in ""|data/*) set_env METADATA_CACHE_PATH /data/metadata_cache.json ;; esac

current_catalog="$(grep -E '^LOCAL_CATALOG_PATH=' .env | tail -1 | cut -d= -f2- || true)"
case "$current_catalog" in data/catalog.json) set_env LOCAL_CATALOG_PATH /data/catalog.json ;; esac

set -a
# shellcheck disable=SC1091
. ./.env
set +a

compose=(docker compose -f docker-compose.yml)
services=(cinema-bot)

if [[ -n "${PUBLIC_HOST:-}" && "${PUBLIC_HOST:-}" != __FILL_* ]]; then
  compose+=(-f docker-compose.vps.yml)
  services+=(caddy)
  if [[ -n "${DUCKDNS_SUBDOMAIN:-}" && -n "${DUCKDNS_TOKEN:-}" ]]; then
    compose+=(--profile duckdns)
    services+=(duckdns)
  fi
  ./scripts/vps_check.sh .env
else
  echo "ℹ️ 未填写 PUBLIC_HOST，仅启动 cinema-bot，并绑定到 127.0.0.1:8000。"
  echo "   如果要接飞书，请配置公网 HTTPS 域名后重新运行。"
fi

echo ""
echo "开始构建并启动：${services[*]}"
"${compose[@]}" up -d --build "${services[@]}"

echo ""
"${compose[@]}" ps
echo ""
"${compose[@]}" run --rm cinema-bot python -m app.config_check || true

echo ""
echo "✅ 部署命令已执行完成"
if [[ -n "${PUBLIC_HOST:-}" && "${PUBLIC_HOST:-}" != __FILL_* ]]; then
  echo "健康检查：https://${PUBLIC_HOST}/healthz"
  echo "飞书回调：https://${PUBLIC_HOST}/webhooks/feishu"
else
  echo "本机健康检查：http://127.0.0.1:8000/healthz"
fi
