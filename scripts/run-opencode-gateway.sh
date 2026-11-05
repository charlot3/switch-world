#!/usr/bin/env bash
#
# run-opencode-gateway — an OpenAI-compatible adapter for OpenCode Go's DeepSeek model.
#
# Bifrost calls this on :8090; the adapter calls `opencode run` and returns the text
# event as an OpenAI chat completion. It is free/open-source tooling and uses the
# OpenCode Go provider already signed in on this machine.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${OPENCODE_PROXY_TOKEN:=opencode-shim}"
: "${OPENCODE_MODEL:=opencode-go/deepseek-v4.1-flash}"
: "${OPENCODE_GATEWAY_PORT:=8090}"
: "${OPENCODE_TIMEOUT:=240}"
export OPENCODE_PROXY_TOKEN OPENCODE_MODEL OPENCODE_GATEWAY_PORT OPENCODE_TIMEOUT

if curl -sf "http://127.0.0.1:${OPENCODE_GATEWAY_PORT}/health" >/dev/null 2>&1; then
  echo "OpenCode gateway already running on :${OPENCODE_GATEWAY_PORT}"
  exit 0
fi

nohup python3 "$ROOT/scripts/opencode-gateway.py" \
  >/tmp/switch-world-opencode-gateway.log 2>&1 &
echo $! >/tmp/switch-world-opencode-gateway.pid
echo "OpenCode gateway starting on :${OPENCODE_GATEWAY_PORT} -> ${OPENCODE_MODEL}"
for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${OPENCODE_GATEWAY_PORT}/health" >/dev/null 2>&1; then
    echo "OpenCode gateway is ready."
    exit 0
  fi
  sleep 0.5
done
echo "OpenCode gateway did not answer; check /tmp/switch-world-opencode-gateway.log" >&2
exit 1
