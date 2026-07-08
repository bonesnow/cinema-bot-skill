#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

read -r -p "请输入飞书 App ID: " APP_ID
if [[ -z "$APP_ID" ]]; then
  echo "错误：App ID 不能为空" >&2
  exit 1
fi

read -r -s -p "请输入重新生成的飞书 App Secret（输入过程不显示）: " APP_SECRET
echo
if [[ -z "$APP_SECRET" ]]; then
  echo "错误：App Secret 不能为空" >&2
  exit 1
fi

read -r -s -p "请输入飞书 Verification Token（输入过程不显示）: " VERIFY_TOKEN
echo
if [[ -z "$VERIFY_TOKEN" ]]; then
  echo "错误：Verification Token 不能为空" >&2
  exit 1
fi

python3 - "$ENV_FILE" "$APP_ID" "$APP_SECRET" "$VERIFY_TOKEN" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
updates = {
    "FEISHU_APP_ID": sys.argv[2],
    "FEISHU_APP_SECRET": sys.argv[3],
    "FEISHU_VERIFICATION_TOKEN": sys.argv[4],
}

lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

chmod 600 "$ENV_FILE"

echo "✅ 飞书凭证已安全写入 $ENV_FILE"
echo "✅ 文件权限已设置为 600"
echo "下一步：填写公网地址和资源源配置，然后运行："
echo "  docker compose run --rm cinema-bot python -m app.config_check"
