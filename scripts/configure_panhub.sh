#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

set_key() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
found = False
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

read -r -p "PanHub 地址: " PANHUB_URL
if [[ -z "$PANHUB_URL" ]]; then
  echo "错误：PanHub 地址不能为空" >&2
  exit 1
fi

set_key PANHUB_BASE_URL "$PANHUB_URL"
set_key PANHUB_CONCURRENCY "4"
set_key PANHUB_TIMEOUT "30"
set_key WEBSITE_CONFIG_PATH ""
set_key PROVIDER_API_URLS ""
set_key LOCAL_CATALOG_PATH ""

read -r -p "PanHub 是否返回 HTTP 401？[y/N]: " NEED_COOKIE
if [[ "${NEED_COOKIE,,}" == "y" || "${NEED_COOKIE,,}" == "yes" ]]; then
  read -r -s -p "请输入完整 PanHub Cookie（输入不显示）: " PANHUB_COOKIE
  echo
  set_key PANHUB_COOKIE "$PANHUB_COOKIE"
else
  set_key PANHUB_COOKIE ""
fi

chmod 600 "$ENV_FILE"
echo "✅ PanHub 已写入 $ENV_FILE"
echo "下一步运行："
echo "  docker compose build --no-cache cinema-bot"
echo "  docker compose run --rm cinema-bot python -m app.config_check"
