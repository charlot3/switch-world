#!/usr/bin/env bash
#
# update-mattermost-avatars — push the generated square crops to the four bot accounts.
#
# Reads the Mattermost admin credentials from .env, logs in, resolves each bot by
# username, and uploads web/assets/portraits/<name>-avatar.png. The token and the
# password never leave the shell; only a per-character status line is printed.
#
# Usage:
#   scripts/update-mattermost-avatars.sh [env-file]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
[ -f "$ENV_FILE" ] || { echo "missing env file: $ENV_FILE" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

BASE="${MATTERMOST_URL:-http://localhost:8065}"
ADMIN_USER="${MATTERMOST_ADMIN_USER:-admin}"
: "${MATTERMOST_ADMIN_PASSWORD:?missing MATTERMOST_ADMIN_PASSWORD}"

LOGIN_JSON="$(
  python3 -c 'import json, os; print(json.dumps({
      "login_id": os.environ.get("MATTERMOST_ADMIN_USER", "admin"),
      "password": os.environ["MATTERMOST_ADMIN_PASSWORD"],
  }))'
)"
LOGIN_HEADERS="$(mktemp)"
trap 'rm -f "$LOGIN_HEADERS"' EXIT
LOGIN_RESPONSE="$(curl -sS -D "$LOGIN_HEADERS" -X POST "$BASE/api/v4/users/login" \
  -H 'Content-Type: application/json' -d "$LOGIN_JSON")"
TOKEN="$(awk 'BEGIN { IGNORECASE = 1 } /^Token:/ { print $2 }' "$LOGIN_HEADERS" | tr -d '\r')"
if [ -z "$TOKEN" ]; then
  python3 -c 'import json, sys; d=json.load(sys.stdin); print("Mattermost login failed:", d.get("message", "no message"), "| id:", d.get("id", "?"))' \
    <<<"$LOGIN_RESPONSE" >&2
  exit 1
fi

for name in alice emily sophia mia; do
  avatar="$ROOT/web/assets/portraits/$name-avatar.png"
  [ -f "$avatar" ] || { echo "$name: missing $avatar" >&2; continue; }
  user_id="$(
    curl -sS -H "Authorization: Bearer $TOKEN" \
      "$BASE/api/v4/users/username/$name" \
      | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))'
  )"
  if [ -z "$user_id" ]; then
    echo "$name: no Mattermost user"
    continue
  fi
  curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
    -F "image=@$avatar" "$BASE/api/v4/users/$user_id/image" >/dev/null
  echo "$name: avatar updated"
done
