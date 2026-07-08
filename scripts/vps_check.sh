#!/usr/bin/env sh
set -eu

ENV_FILE="${1:-.env}"
case "$ENV_FILE" in
  */*) ;;
  *) ENV_FILE="./$ENV_FILE" ;;
esac

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ 未找到 $ENV_FILE，请先执行：cp .env.example .env"
  exit 1
fi

# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

failed=0
check_value() {
  name="$1"
  eval "value=\${$name:-}"
  case "$value" in
    ""|__FILL_* )
      echo "❌ 缺少：$name"
      failed=1
      ;;
    *)
      echo "✅ 已填写：$name"
      ;;
  esac
}

check_value PUBLIC_HOST

# DuckDNS is optional. Validate only when either value is supplied.
duck_sub="${DUCKDNS_SUBDOMAIN:-}"
duck_token="${DUCKDNS_TOKEN:-}"
case "$duck_sub" in __FILL_*) duck_sub="" ;; esac
case "$duck_token" in __FILL_*) duck_token="" ;; esac

if [ -n "$duck_sub" ] || [ -n "$duck_token" ]; then
  if [ -z "$duck_sub" ] || [ -z "$duck_token" ]; then
    echo "❌ DuckDNS 启用时必须同时填写 DUCKDNS_SUBDOMAIN 和 DUCKDNS_TOKEN"
    failed=1
  else
    echo "✅ DuckDNS 可选配置完整"
    expected="${duck_sub}.duckdns.org"
    if [ "${PUBLIC_HOST:-}" != "$expected" ]; then
      echo "⚠️ 当前 PUBLIC_HOST 不是 DuckDNS 主机名：$expected"
    fi
  fi
else
  echo "ℹ️ 未启用 DuckDNS，将直接使用 PUBLIC_HOST"
fi

if [ "$failed" -ne 0 ]; then
  exit 1
fi

echo ""
echo "飞书回调地址：https://${PUBLIC_HOST}/webhook/feishu"
echo "兼容回调地址：https://${PUBLIC_HOST}/webhooks/feishu"
echo "健康检查地址：https://${PUBLIC_HOST}/healthz"
