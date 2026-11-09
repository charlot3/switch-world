#!/usr/bin/env bash
#
# run-bifrost — start the local Bifrost gateway with the OpenCode Go provider.
#
# Bifrost is the Geek Room edition's model gateway. It listens on :8080 and exposes
# the OpenAI-compatible /v1/chat/completions endpoint that switch_world/adapters/models/bifrost_compat.py calls.
#
# Usage:
#   scripts/run-bifrost.sh [env-file]
#
# The default provider is the OpenCode Go adapter (`openai/deepseek-v4.1-flash`)
# in world/models.json, served by scripts/opencode-gateway.py. Set
# BIFROST_MODEL_<CHARACTER> / BIFROST_FALLBACKS_<CHARACTER> to point individual
# characters at different provider models; add those providers to config.json.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${BIFROST_ENCRYPTION_KEY:=0123456789abcdef0123456789abcdef}"
: "${OLLAMA_URL:=http://host.docker.internal:11435}"
: "${BIFROST_PORT:=8080}"
: "${OPENCODE_PROXY_TOKEN:=opencode-shim}"
export OPENCODE_PROXY_TOKEN

# Bifrost's primary provider is the OpenCode Go adapter on :8090. It uses the
# OpenCode model already signed in on this machine, so the demo has no paid API bill.
bash "$ROOT/scripts/run-opencode-gateway.sh" "$ENV_FILE"

# Docker Desktop can reach the host, but Ollama commonly listens only on 127.0.0.1.
# Give Bifrost a host-reachable port without changing the user's Ollama configuration.
if ! curl -sf http://127.0.0.1:11435/api/tags >/dev/null 2>&1 \
   && curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  nohup python3 "$ROOT/scripts/ollama-proxy.py" \
    >/tmp/switch-world-ollama-proxy.log 2>&1 &
  echo $! >/tmp/switch-world-ollama-proxy.pid
  sleep 1
fi

docker rm -f switch-world-bifrost >/dev/null 2>&1 || true
docker run -d --rm --name switch-world-bifrost \
  -p "${BIFROST_PORT}:8080" \
  -v "$ROOT/deploy/bifrost/data:/app/data" \
  -e BIFROST_ENCRYPTION_KEY="$BIFROST_ENCRYPTION_KEY" \
  -e OLLAMA_URL="$OLLAMA_URL" \
  -e OPENCODE_PROXY_TOKEN="$OPENCODE_PROXY_TOKEN" \
  maximhq/bifrost

echo "Bifrost starting on http://127.0.0.1:${BIFROST_PORT}"
echo "Ollama provider: ${OLLAMA_URL}"
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${BIFROST_PORT}/v1/models" >/dev/null 2>&1; then
    echo "Bifrost is ready."
    exit 0
  fi
  sleep 1
done
echo "Bifrost did not answer yet; check: docker logs switch-world-bifrost" >&2
exit 1
