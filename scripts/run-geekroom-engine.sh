#!/usr/bin/env bash
#
# run-geekroom-engine — a separate world-engine instance for the Geek Room demo.
#
# It uses its own DB/data directory so the Flip demo on :8890 is untouched. The
# default is an offline Tavily fixture and the local Bifrost gateway on :8080.
#
# Usage:
#   scripts/run-geekroom-engine.sh
#   GEEKROOM_PORT=8892 GEEKROOM_DB=/tmp/other.sqlite scripts/run-geekroom-engine.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

export WORLD_ENGINE_PORT="${GEEKROOM_PORT:-8891}"
export WORLD_DB="${GEEKROOM_DB:-/tmp/geekroom/world.sqlite}"
export WORLD_DATA_DIR="${GEEKROOM_DATA:-/tmp/geekroom}"
export TAVILY_OFFLINE="${TAVILY_OFFLINE:-1}"
export BIFROST_URL="${BIFROST_URL:-http://127.0.0.1:8080/v1}"

mkdir -p "$WORLD_DATA_DIR"
cd "$ROOT"
echo "Geek Room world engine: http://127.0.0.1:${WORLD_ENGINE_PORT}"
echo "DB: ${WORLD_DB} · Tavily offline: ${TAVILY_OFFLINE} · Bifrost: ${BIFROST_URL}"
exec uv run world-engine
