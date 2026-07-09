#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/scripts/setup_local_env.sh"
cd "$ROOT_DIR"

echo ""
echo "✅ 进入本地问答模式。不需要 VPS、域名、飞书回调。"
echo "提示：先编辑 data/catalog.json，填入你有权使用的夸克分享。"
echo ""
exec .venv/bin/python -m app.cli
