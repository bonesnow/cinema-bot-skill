#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/scripts/setup_local_env.sh"
cd "$ROOT_DIR"

PORT="${PORT:-8000}"
echo ""
echo "✅ 本地服务即将启动"
echo "健康检查：http://127.0.0.1:${PORT}/healthz"
echo "飞书回调需要公网 HTTPS。没有域名时，请用 scripts/local_qa.sh。"
echo ""
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --proxy-headers
