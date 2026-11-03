#!/usr/bin/env bash
#
# render-claude-configs — the Claude Code fallback for a character directory.
#
# Usage:
#   scripts/render-claude-configs.sh [env-file]
#
# Writes agents/<name>/CLAUDE.md (persona + operating rules) and .mcp.json with the
# character's literal world token. .mcp.json is gitignored; CLAUDE.md is committed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
[ -f "$ENV_FILE" ] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

WORLD_URL="${WORLD_MCP_URL:-http://127.0.0.1:8890/mcp}"

for name in alice emily sophia mia; do
  dir="$ROOT/agents/$name"
  [ -d "$dir" ] || { echo "missing directory: $dir" >&2; exit 1; }
  var="WORLD_TOKEN_$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')"
  token="${!var:-}"
  [ -n "$token" ] || { echo "missing $var in $ENV_FILE" >&2; exit 1; }

  cat "$dir/AGENTS.md" "$dir/IDENTITY.md" > "$dir/CLAUDE.md"

  cat > "$dir/.mcp.json" <<JSON
{
  "mcpServers": {
    "world": {
      "type": "http",
      "url": "$WORLD_URL",
      "headers": {
        "Authorization": "Bearer $token"
      }
    }
  }
}
JSON
  chmod 600 "$dir/.mcp.json"
  echo "wrote $dir/CLAUDE.md and $dir/.mcp.json"
done
