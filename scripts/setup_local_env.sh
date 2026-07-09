#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "❌ 未找到 Python。请先安装 Python 3.12 或更新系统 Python。" >&2
    exit 1
  fi
fi

python_version="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
case "$python_version" in
  3.1[2-9]|3.[2-9][0-9]) ;;
  *)
    echo "❌ 当前 Python 是 $python_version，本项目需要 Python 3.12 或更高版本。" >&2
    echo "   可设置 PYTHON_BIN=/path/to/python3.12 后重试。" >&2
    exit 1
    ;;
esac

mkdir -p data
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
if [[ ! -f data/catalog.json ]]; then
  cp catalog.example.json data/catalog.json
fi

set_env() {
  local key="$1" value="$2"
  "$PYTHON_BIN" - "$key" "$value" <<'PY'
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

set_env DRY_RUN true
set_env AUTO_SAVE true
set_env QUARK_AUTH_FILE data/quark_auth.json
set_env LOCAL_CATALOG_PATH data/catalog.json
set_env METADATA_CACHE_PATH data/metadata_cache.json
set_env ORGANIZE_AFTER_SAVE true

chmod 600 .env

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt >/dev/null

echo "✅ 本地环境已准备好"
echo "配置文件：$ROOT_DIR/.env"
echo "本地目录：$ROOT_DIR/data/catalog.json"
