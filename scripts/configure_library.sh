#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

set_env() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); key=sys.argv[2]; value=sys.argv[3]
lines=path.read_text(encoding='utf-8').splitlines()
out=[]; found=False
for line in lines:
    if line.startswith(key+'='):
        out.append(f'{key}={value}'); found=True
    else:
        out.append(line)
if not found:
    out.append(f'{key}={value}')
path.write_text('\n'.join(out)+'\n', encoding='utf-8')
PY
}

read -r -p "转存后自动整理？[Y/n]: " auto
case "${auto:-Y}" in n|N) set_env ORGANIZE_AFTER_SAVE false ;; *) set_env ORGANIZE_AFTER_SAVE true ;; esac

read -r -p "媒体库目录名 [夸克影视]: " root_name
set_env LIBRARY_ROOT_NAME "${root_name:-夸克影视}"

read -r -p "已有媒体库目录 FID（没有就直接回车）: " root_fid
set_env LIBRARY_ROOT_FID "${root_fid:-}"

read -r -p "按 电影/电视剧 和二级分类创建目录？[Y/n]: " genre
case "${genre:-Y}" in n|N) set_env LIBRARY_GENRE_FOLDERS false ;; *) set_env LIBRARY_GENRE_FOLDERS true ;; esac

read -r -p "保留规范片源文件名（2160p/REMUX/HDR 等）？[Y/n]: " keep
case "${keep:-Y}" in n|N) set_env LIBRARY_KEEP_SCENE_NAMES false ;; *) set_env LIBRARY_KEEP_SCENE_NAMES true ;; esac

read -r -s -p "OMDb API Key（可选，输入不显示；没有就直接回车）: " omdb
echo
set_env OMDB_API_KEY "${omdb:-}"
set_env METADATA_CACHE_PATH /data/metadata_cache.json
chmod 600 "$ENV_FILE"

echo "✅ 媒体库整理配置已写入 $ENV_FILE"
echo "下一步：docker compose run --rm cinema-bot python -m app.config_check"
