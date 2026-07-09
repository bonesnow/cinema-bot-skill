#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-$HOME/.hermes/skills/cinema-bot}"
mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
cp -R "$(cd "$(dirname "$0")" && pwd)" "$TARGET"
rm -f "$TARGET/.env"

echo "Installed to: $TARGET"
echo "1. cd '$TARGET'"
echo "2. 没有 VPS/域名：./scripts/local_qa.sh"
echo "3. 本机服务：./scripts/deploy_local.sh"
echo "4. VPS 部署：./scripts/deploy_vps.sh"
echo "5. 详细文档：README.md 和 docs/12_部署方式.md"
