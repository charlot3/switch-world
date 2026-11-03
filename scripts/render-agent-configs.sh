#!/usr/bin/env bash
#
# render-agent-configs — write each character's OpenCode config with its literal token.
#
# Usage:
#   scripts/render-agent-configs.sh [env-file]
#
# Why literal tokens: Switch passes the session only a fixed set of environment variables,
# not the whole shell. A ${WORLD_TOKEN} reference in opencode.json would be empty and every
# world MCP call would return 401. The generated file is gitignored.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"

[ -f "$ENV_FILE" ] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

WORLD_URL="${WORLD_MCP_URL:-http://127.0.0.1:8890/mcp}"
# The roleplay model. Keep it identical across the cast; a mixed cast drifts.
MODEL="${WORLD_AGENT_MODEL:-opencode-go/deepseek-v4.1-flash}"

for name in alice emily sophia mia; do
  var="WORLD_TOKEN_$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')"
  token="${!var:-}"
  if [ -z "$token" ]; then
    echo "missing $var in $ENV_FILE" >&2
    exit 1
  fi

  dir="$ROOT/agents/$name"
  mkdir -p "$dir"

  cat > "$dir/opencode.json" <<JSON
{
  "\$schema": "https://opencode.ai/config.json",
  "model": "$MODEL",
  "instructions": ["IDENTITY.md"],
  "mcp": {
    "world": {
      "type": "remote",
      "url": "$WORLD_URL",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer $token"
      }
    }
  }
}
JSON

  chmod 600 "$dir/opencode.json"
  echo "wrote $dir/opencode.json"
done
