#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-$HOME/.hermes/skills/cinema-bot}"
mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
cp -R "$(cd "$(dirname "$0")" && pwd)" "$TARGET"
rm -f "$TARGET/.env"

echo "Installed to: $TARGET"
echo "1. cd '$TARGET'"
echo "2. cp .env.example .env"
echo "3. cp websites.example.yaml data/websites.yaml"
echo "4. Open .env and data/websites.yaml, then search for: __FILL_"
echo "5. Read: 00_先看这里.md"
echo "6. Run: docker compose run --rm cinema-bot python -m app.website_check"
echo "7. Run: docker compose run --rm cinema-bot python -m app.config_check"
