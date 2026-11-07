#!/usr/bin/env bash
# Deploy the switch-world guest demo to an Oracle Cloud VM.
#
# Required environment:
#   DEMO_HOST            user@ip (e.g. ubuntu@203.0.113.10)
#   DEMO_SSH_KEY         path to the private SSH key (chmod 600)
#   DEMO_DOMAIN          public hostname, e.g. switch-demo.duckdns.org
#   DEMO_GUEST_PASSWORD  plaintext guest password (never written to disk)
#
# Optional:
#   DEMO_GUEST_USER      basic-auth username (default: guest)
#   DEMO_REMOTE_DIR      remote checkout (default: /home/ubuntu/switch-world-demo)
#   DUCKDNS_TOKEN        if set, refresh the DuckDNS A record
#   DUCKDNS_DOMAIN       DuckDNS subdomain without .duckdns.org
#                        (default: derived from DEMO_DOMAIN)
#
# This script does NOT commit secrets. The bcrypt hash is rendered into
# /etc/caddy/conf.d/switch-world.caddy (mode 640) on the remote host. The
# plaintext password only ever travels base64-encoded on ssh stdin/stdout for
# `caddy hash-password`.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
SNIPPET="$SCRIPT_DIR/Caddyfile.snippet"
REMOTE_DIR="${DEMO_REMOTE_DIR:-/home/ubuntu/switch-world-demo}"
DEMO_GUEST_USER="${DEMO_GUEST_USER:-guest}"

DRY_RUN=0

usage() {
  cat <<'EOF'
Deploy the switch-world guest demo to an Oracle Cloud VM.

Required environment:
  DEMO_HOST            user@ip (e.g. ubuntu@203.0.113.10)
  DEMO_SSH_KEY         path to the private SSH key (chmod 600)
  DEMO_DOMAIN          public hostname, e.g. switch-demo.duckdns.org
  DEMO_GUEST_PASSWORD  plaintext guest password (never written to disk)

Optional:
  DEMO_GUEST_USER      basic-auth username (default: guest)
  DEMO_REMOTE_DIR      remote checkout (default: /home/ubuntu/switch-world-demo)
  DUCKDNS_TOKEN        if set, refresh the DuckDNS A record
  DUCKDNS_DOMAIN       DuckDNS subdomain without .duckdns.org
                       (default: derived from DEMO_DOMAIN)

Flags:
  -n, --dry-run        print the plan; no ssh/scp/curl or file writes
  -h, --help           show this help

The plaintext password is never written to disk or the repository. The bcrypt
hash is installed remotely in /etc/caddy/conf.d/switch-world.caddy (mode 640).
EOF
}

while (($#)); do
  case "$1" in
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> [%s] %s\n' "$1" "$2"; }
note() { printf '    %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preconditions

missing=0
for name in DEMO_HOST DEMO_SSH_KEY DEMO_DOMAIN DEMO_GUEST_PASSWORD; do
  if [[ -z "${!name:-}" ]]; then
    printf 'ERROR: %s is required\n' "$name" >&2
    missing=1
  fi
done
((missing == 0)) || exit 1

[[ "$DEMO_HOST" == *@* ]] || die "DEMO_HOST must be user@ip (got: $DEMO_HOST)"
[[ -f "$DEMO_SSH_KEY" ]] || die "DEMO_SSH_KEY does not exist: $DEMO_SSH_KEY"
[[ -r "$DEMO_SSH_KEY" ]] || die "DEMO_SSH_KEY is not readable: $DEMO_SSH_KEY"
[[ -f "$SNIPPET" ]] || die "missing $SNIPPET"

command -v ssh >/dev/null 2>&1 || die "ssh is not installed"
command -v scp >/dev/null 2>&1 || die "scp is not installed"
command -v python3 >/dev/null 2>&1 || die "python3 is required to render the Caddyfile"
command -v base64 >/dev/null 2>&1 || die "base64 is required"

SSH_OPTS=(
  -i "$DEMO_SSH_KEY"
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o StrictHostKeyChecking=accept-new
)

remote() {
  ssh "${SSH_OPTS[@]}" "$DEMO_HOST" "$1"
}

if ((DRY_RUN)); then
  step "dry-run" "no ssh, scp, curl or file writes will be performed"
  note "repo root:        $REPO_ROOT"
  note "remote dir:       $REMOTE_DIR"
  note "domain:           $DEMO_DOMAIN"
  note "guest user:       $DEMO_GUEST_USER"
  note ""
  note "1. ssh reachability check against $DEMO_HOST"
  note "2. verify docker + caddy exist on the remote host"
  note "3. rsync (or tar over ssh) the app tree to $REMOTE_DIR"
  note "4. mkdir/chown $REMOTE_DIR/deploy/demo/data for uid 10001"
  note "5. docker compose -f deploy/demo/docker-compose.yml up -d --build"
  note "6. poll http://127.0.0.1:8893/health until it returns 200"
  note "7. caddy hash-password on the remote host (bcrypt)"
  note "8. render Caddyfile.snippet and install /etc/caddy/conf.d/switch-world.caddy (mode 640)"
  note "9. caddy validate + systemctl reload caddy"
  if [[ -n "${DUCKDNS_TOKEN:-}" ]]; then
    note "10. update DuckDNS A record"
  else
    note "10. DuckDNS update skipped (DUCKDNS_TOKEN unset)"
  fi
  note ""
  note "Nothing was changed."
  exit 0
fi

# ---------------------------------------------------------------- 1. reachability

step "1/9" "checking ssh to $DEMO_HOST"
remote "true" || die "cannot ssh to $DEMO_HOST with $DEMO_SSH_KEY"
note "ok"

# ---------------------------------------------------------------- 2. remote tools

step "2/9" "checking remote docker and caddy"
remote "command -v docker >/dev/null 2>&1" || die "docker is not installed on $DEMO_HOST"
remote "docker compose version >/dev/null 2>&1" || die "docker compose v2 is not available on $DEMO_HOST"
remote "command -v caddy >/dev/null 2>&1" || die "caddy is not installed on $DEMO_HOST (install Caddy before deploying)"
remote "sudo -n true 2>/dev/null" || die "passwordless sudo is not available; Caddy config needs root"
note "ok"

# ---------------------------------------------------------------- 3. copy source

step "3/9" "syncing repository to $REMOTE_DIR"
REMOTE_TARGET="$DEMO_HOST:$REMOTE_DIR"
if command -v rsync >/dev/null 2>&1; then
  note "using rsync"
  rsync -az --human-readable \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='.pytest_cache' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.sqlite*' \
    --exclude='data' \
    --exclude='deploy/bifrost' \
    --exclude='deploy/demo/data' \
    --exclude='recordings' \
    --exclude='scratch' \
    --exclude='node_modules' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='agents/*/opencode.json' \
    --exclude='agents/*/.mcp.json' \
    --exclude='agents/*/.switch' \
    --exclude='.switch' \
    --exclude='director/.switch' \
    --exclude='.claude' \
    -e "ssh ${SSH_OPTS[*]}" \
    "$REPO_ROOT/" "$REMOTE_TARGET/"
else
  note "rsync unavailable; using tar over ssh"
  tar -C "$REPO_ROOT" -czf - \
    --exclude='./.git' \
    --exclude='./.venv' \
    --exclude='./.pytest_cache' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.sqlite*' \
    --exclude='./data' \
    --exclude='./deploy/bifrost' \
    --exclude='./deploy/demo/data' \
    --exclude='./recordings' \
    --exclude='./scratch' \
    --exclude='./node_modules' \
    --exclude='./.env' \
    --exclude='./.env.*' \
    --exclude='./agents/*/opencode.json' \
    --exclude='./agents/*/.mcp.json' \
    --exclude='./agents/*/.switch' \
    --exclude='./.switch' \
    --exclude='./director/.switch' \
    --exclude='./.claude' \
    . \
    | ssh "${SSH_OPTS[@]}" "$DEMO_HOST" "mkdir -p '$REMOTE_DIR' && tar -C '$REMOTE_DIR' -xzf -"
fi
note "ok"

# ---------------------------------------------------------------- 4. data dir

step "4/9" "preparing persistent data directory"
remote "mkdir -p '$REMOTE_DIR/deploy/demo/data' && { sudo -n chown -R 10001:10001 '$REMOTE_DIR/deploy/demo/data' || echo 'WARNING: could not chown $REMOTE_DIR/deploy/demo/data to 10001:10001; the container may fail to write SQLite' >&2; }"
note "ok"

# ---------------------------------------------------------------- 5. build + up

step "5/9" "building and starting the container"
remote "cd '$REMOTE_DIR' && docker compose -f deploy/demo/docker-compose.yml up -d --build"
note "ok"

# ---------------------------------------------------------------- 6. health

step "6/9" "waiting for the world engine health check"
HEALTH_CMD="
set -e
cd '$REMOTE_DIR'
for i in \$(seq 1 30); do
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS http://127.0.0.1:8893/health >/dev/null 2>&1; then echo healthy; exit 0; fi
  else
    if docker compose -f deploy/demo/docker-compose.yml exec -T world python -c 'import sys, urllib.request; sys.exit(0 if urllib.request.urlopen(\"http://127.0.0.1:8893/health\", timeout=3).status == 200 else 1)' >/dev/null 2>&1; then
      echo healthy; exit 0
    fi
  fi
  sleep 2
done
echo 'ERROR: health check did not pass within 60s' >&2
docker compose -f deploy/demo/docker-compose.yml logs --tail=60 >&2 || true
exit 1
"
remote "$HEALTH_CMD" || die "world engine did not become healthy (see logs above)"
note "ok"

# ---------------------------------------------------------------- 7. hash

step "7/9" "generating bcrypt hash with caddy hash-password (remote)"
PW_B64="$(printf '%s' "$DEMO_GUEST_PASSWORD" | base64 | tr -d '\n')"
HASH_CMD="command -v caddy >/dev/null 2>&1 || { echo 'ERROR: caddy is not installed' >&2; exit 3; }; pw=\$(printf '%s' '$PW_B64' | base64 -d); caddy hash-password --plaintext \"\$pw\""
HASH="$(remote "$HASH_CMD")"
HASH="${HASH//$'\r'/}"
HASH="${HASH%$'\n'}"
[[ -n "$HASH" ]] || die "caddy hash-password returned an empty hash"
[[ "$HASH" == '$2'* ]] || die "unexpected hash output from caddy hash-password (got: ${HASH:0:16}...)"
note "ok (bcrypt hash generated, plaintext discarded)"

# ---------------------------------------------------------------- 8. install site

step "8/9" "rendering and installing Caddy site block"

if ! remote "grep -qE '^[[:space:]]*import[[:space:]].*conf\.d' /etc/caddy/Caddyfile"; then
  cat >&2 <<'EOF'
ERROR: /etc/caddy/Caddyfile does not import /etc/caddy/conf.d/*.caddy

Add this line to the main Caddyfile (keep any existing site blocks):

    import /etc/caddy/conf.d/*.caddy

Then re-run this script. It will not modify or replace the main Caddyfile
automatically because that could take other sites offline.
EOF
  exit 1
fi

RENDERED="$(mktemp "${TMPDIR:-/tmp}/switch-world-demo-caddy.XXXXXX")"
trap 'rm -f "$RENDERED"' EXIT

DEMO_DOMAIN="$DEMO_DOMAIN" \
DEMO_GUEST_USER="$DEMO_GUEST_USER" \
DEMO_GUEST_HASH="$HASH" \
python3 - "$SNIPPET" > "$RENDERED" <<'PY'
import os
import sys

text = open(sys.argv[1], encoding="utf-8").read()
for key in ("DEMO_DOMAIN", "DEMO_GUEST_USER", "DEMO_GUEST_HASH"):
    text = text.replace("{$" + key + "}", os.environ[key])
if "{$DEMO_" in text:
    sys.exit("unrendered placeholder remains in Caddyfile.snippet")
sys.stdout.write(text)
PY

chmod 600 "$RENDERED"
scp "${SSH_OPTS[@]}" "$RENDERED" "$DEMO_HOST:/tmp/switch-world-demo.caddy" >/dev/null

remote "sudo -n mkdir -p /etc/caddy/conf.d && sudo -n install -m 640 -o root -g caddy /tmp/switch-world-demo.caddy /etc/caddy/conf.d/switch-world.caddy && rm -f /tmp/switch-world-demo.caddy"
note "ok: /etc/caddy/conf.d/switch-world.caddy (mode 640)"

# ---------------------------------------------------------------- 9. validate

step "9/9" "validating and reloading Caddy"
if ! remote "sudo -n caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"; then
  cat >&2 <<'EOF'
ERROR: Caddy rejected the configuration. The previous Caddy process is still
serving its last-good config. Inspect /etc/caddy/conf.d/switch-world.caddy and
follow the rollback steps in deploy/demo/README.md.
EOF
  exit 1
fi

if ! remote "sudo -n systemctl reload caddy"; then
  note "systemctl reload failed; trying caddy reload"
  remote "sudo -n caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"
fi
note "ok"

# ---------------------------------------------------------------- optional DNS

if [[ -n "${DUCKDNS_TOKEN:-}" ]]; then
  step "dns" "updating DuckDNS"
  if [[ -z "${DUCKDNS_DOMAIN:-}" ]]; then
    if [[ "$DEMO_DOMAIN" == *.duckdns.org ]]; then
      DUCKDNS_DOMAIN="${DEMO_DOMAIN%.duckdns.org}"
    else
      die "DUCKDNS_TOKEN is set but DUCKDNS_DOMAIN is unset and DEMO_DOMAIN is not a *.duckdns.org name"
    fi
  fi
  response="$(curl -fsS "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")"
  [[ "$response" == OK* ]] || die "DuckDNS update failed: $response"
  note "DuckDNS updated for $DUCKDNS_DOMAIN.duckdns.org"
fi

# ---------------------------------------------------------------- summary

printf '\nDeployed.\n'
printf '  URL:          https://%s\n' "$DEMO_DOMAIN"
printf '  Guest user:   %s\n' "$DEMO_GUEST_USER"
printf '  Password:     (the DEMO_GUEST_PASSWORD you supplied; not printed or stored)\n'
printf '\nVerify:\n'
printf '  curl -u %s https://%s/health\n' "$DEMO_GUEST_USER" "$DEMO_DOMAIN"
printf '  ssh %s "cd %s && docker compose -f deploy/demo/docker-compose.yml logs -f --tail=50"\n' "$DEMO_HOST" "$REMOTE_DIR"
