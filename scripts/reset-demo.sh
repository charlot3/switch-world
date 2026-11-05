#!/usr/bin/env bash
#
# reset-demo — reset the world state (phone DMs included) for a fresh demo.
#
#   scripts/reset-demo.sh flip
#   scripts/reset-demo.sh geekroom
#   scripts/reset-demo.sh all --artifacts
#
# This resets the SQLite world: beliefs, relationships, events, phone DMs and the scene
# card preview. It does NOT erase Mattermost/Switch room history; create a new room or
# recreate the Switch stack if the chat transcript itself must be fresh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-flip}"
shift || true
ARTIFACTS=0
for arg in "$@"; do
  case "$arg" in
    --artifacts) ARTIFACTS=1 ;;
    -h|--help)
      echo "usage: scripts/reset-demo.sh [flip|geekroom|all] [--artifacts]"
      exit 0
      ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

reset_one() {
  local label="$1" url="$2"
  echo "== $label: POST $url/api/dev/reset"
  if ! curl -sS -X POST "$url/api/dev/reset" -H 'Content-Type: application/json' -d '{}' >/tmp/reset-demo-$label.json; then
    echo "  $label world engine is not reachable at $url" >&2
    return 1
  fi
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  ", "reset", d.get("ok"), "clock", (d.get("state") or {}).get("clock"))' /tmp/reset-demo-$label.json
}

if [ "$TARGET" = "flip" ] || [ "$TARGET" = "all" ]; then
  reset_one flip "http://127.0.0.1:8890"
  if [ "$ARTIFACTS" = "1" ]; then
    rm -rf "$ROOT/data/exports"
    rm -f "$ROOT/data/logs/bifrost.jsonl" "$ROOT/data/bifrost_budget.json"
    echo "  cleared flip exports / Bifrost logs"
  fi
fi

if [ "$TARGET" = "geekroom" ] || [ "$TARGET" = "all" ]; then
  reset_one geekroom "http://127.0.0.1:8891"
  if [ "$ARTIFACTS" = "1" ]; then
    rm -rf /tmp/geekroom/exports
    rm -f /tmp/geekroom/logs/bifrost.jsonl /tmp/geekroom/bifrost_budget.json
    echo "  cleared Geek Room exports / Bifrost logs"
  fi
fi

echo "World reset. Switch/Mattermost room history is unchanged."
