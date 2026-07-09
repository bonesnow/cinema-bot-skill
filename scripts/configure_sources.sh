#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi

urls=("$@")
if [[ "${#urls[@]}" -eq 0 ]]; then
  echo "请输入资源站网址，一行一个。输入空行结束。"
  while true; do
    read -r -p "资源站网址: " value
    [[ -z "$value" ]] && break
    urls+=("$value")
  done
fi

if [[ "${#urls[@]}" -eq 0 ]]; then
  echo "❌ 没有输入资源站网址" >&2
  exit 1
fi

python3 - "${urls[@]}" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import json
import sys

def normalize_url(value: str) -> str:
    value = value.strip()
    if value and "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")

sites = []
for raw in sys.argv[1:]:
    url = normalize_url(raw)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit(f"无效网址：{raw}")
    sites.append(
        {
            "name": parsed.hostname.lower(),
            "enabled": True,
            "authorized": True,
            "url": url,
        }
    )

payload = {
    "simple_sites": sites,
    "websites": [],
}
Path("data").mkdir(exist_ok=True)
Path("data/websites.yaml").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

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

set_env WEBSITE_CONFIG_PATH data/websites.yaml
chmod 600 .env

echo "✅ 已生成 data/websites.yaml"
echo "✅ 已写入 .env：WEBSITE_CONFIG_PATH=data/websites.yaml"
echo "下一步："
echo "  ./scripts/local_qa.sh"
echo "或："
echo "  docker compose run --rm cinema-bot python -m app.website_check"
