#!/usr/bin/env bash
#
# fetch-switch — pull the pinned standalone Switch compose artifact.
#
# Usage:
#   scripts/fetch-switch.sh <tag>
#
# Requires oras (https://oras.land/). Prints the artifact contents so you can find the
# compose file and .env.example. The docs require an explicit SWITCH_VERSION; the compose
# file has no fallback.

set -euo pipefail

TAG="${1:?usage: scripts/fetch-switch.sh <tag>   (list tags: oras repo tags ghcr.io/sandbox-quantum/standalone-compose)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/deploy/switch/$TAG"

command -v oras >/dev/null 2>&1 || {
  echo "oras is required: https://oras.land/docs/installation" >&2
  exit 1
}

mkdir -p "$DEST"
echo "pulling ghcr.io/sandbox-quantum/standalone-compose:$TAG -> $DEST"
oras pull "ghcr.io/sandbox-quantum/standalone-compose:$TAG" -o "$DEST"
echo
echo "contents:"
ls -la "$DEST"
echo
echo "next: copy this repo's .env.example (merge any extra variables from the artifact),"
echo "      set SWITCH_VERSION=$TAG, fill the secrets, and run:"
echo "      docker compose --env-file .env -f $DEST/docker-compose.yml \\"
echo "        --profile collab --profile gateway up -d"
