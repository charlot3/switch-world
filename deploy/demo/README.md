# switch-world guest demo (Oracle Cloud + Caddy + DuckDNS)

A self-contained, guest-accessible snapshot of the switch-world dashboard and
world engine. It serves the existing FastAPI app and `web/` UI, seeded once with
the **w5-good** scenario, behind Caddy basic auth on a DuckDNS hostname.

> **Three modes.**
>
> 1. **Snapshot** — no model calls, `WORLD_DEV=0`, read-only-ish browsing.
> 2. **Cloud replies (default in docker-compose)** — the same container, but
>    `WORLD_AGENT_MODE=cloud`: group chat, whisper and DM answer through the
>    DeepSeek API with the operator's key. No Switch Console is needed, so the
>    whole demo runs on the VM. This is the mode the public submission uses.
> 3. **Reverse tunnel** — the operator's local stack behind the same Caddy
>    site. Kept as a fallback only; prefer cloud replies.
>
> All modes run `WORLD_DEV=0`, so authored-beat/dev endpoints (scenario/take
> load, clock advance, reset, model-backed beats) answer `404`. The social
> endpoints the dashboard uses — `/api/group/say`, `/api/group/whisper`,
> `/api/dm`, `/api/friends/*` — stay open.

## Cloud replies (recommended)

No Switch Console runs on the VM, so `WORLD_AGENT_MODE=cloud` keeps the same
planning/addressing/recording path and answers each planned speaker with one
DeepSeek call. Whisper and DM use the same key through `CloudBifrost`.

Create `/home/ubuntu/switch-world-demo/.env` (mode 600, never committed):

```bash
DEEPSEEK_API_KEY=<the same key the local cast uses>
WORLD_AGENT_MODE=cloud
WORLD_CLOUD_MODEL=deepseek-flash
WORLD_CLOUD_REASONING=low
```

Build and start:

```bash
cd /home/ubuntu/switch-world-demo
docker compose --env-file .env -f deploy/demo/docker-compose.yml up -d --build
```

Test before pointing Caddy at it:

```bash
curl -s http://127.0.0.1:8893/health
curl -s -X POST http://127.0.0.1:8893/api/group/say \
  -H 'Content-Type: application/json' \
  -d '{"message":"Evening, all. What is good tonight?","timeout":90}'
```

The reply should contain two or three `replies[]` lines and no `@user` or
`@director` text. The same test through the public hostname is the acceptance
check for every deploy.

## Live mode (reverse tunnel, fallback)

Use this only when the cloud key is unavailable and the local Switch agents must
be the responders. The Mac then serves the dashboard and Mattermost:

```bash
# On the Mac, keep this session open (loopback-only remote ports):
ssh -N \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -i ~/.ssh/<oracle-key> \
  -R 127.0.0.1:18065:127.0.0.1:8065 \
  -R 127.0.0.1:18890:127.0.0.1:8890 \
  ubuntu@<oracle-ip>
```

`18890` is the live world engine (dashboard + `/api/*`), `18065` is the local
Mattermost. The Caddy site then looks like this:

```caddyfile
switch-demo-rin.duckdns.org {
	encode zstd gzip

	# Mattermost keeps its own login; no basic auth here so the Switch
	# bridge can authenticate with a bearer token.
	handle /mattermost/* {
		reverse_proxy 127.0.0.1:8065
	}

	# Live dashboard. Dev mutators stay closed to visitors.
	handle /api/dev/* {
		basic_auth { guest <bcrypt-hash> }
		respond 403
	}

	handle {
		basic_auth { guest <bcrypt-hash> }
		reverse_proxy 127.0.0.1:18890
	}
}
```

Notes:

- The dashboard reads and writes the **local** SQLite world, so a guest line
  really advances the recorded scene. Keep `WORLD_DEV` gating in mind: the
  Caddy rule above blocks `/api/dev/*` from the public surface.
- `web/app.js` rewrites the "Open #world" links to
  `<origin>/mattermost/switch/channels/world` on non-local hosts, so the
  public page links into the bridged Mattermost instead of `localhost:8065`.
- The tunnel is the availability boundary: if the SSH session drops, the site
  answers `502`. Restart it before sharing the link.
- Guest-facing credentials: Caddy basic auth for the dashboard, and the
  Mattermost guest account for `/mattermost`. Use the same password for both
  when the operator wants one login story.

## Layout

```
deploy/demo/
├── Dockerfile                 # multi-stage: build one wheel, install it; non-root uid 10001, port 8893
├── Dockerfile.dockerignore    # small build context (BuildKit)
├── docker-compose.yml         # build from repo root, ./data:/data, 127.0.0.1:8893
├── entrypoint.py              # legacy standalone launcher (the image uses `world-engine --seed w5-good`)
├── Caddyfile.snippet           # site block with {$DEMO_*} placeholders
├── deploy.sh                  # idempotent deploy, --dry-run supported
└── README.md
```

The image builds the package wheel (which force-includes `world/`, `web/` and
each character's `IDENTITY.md`), installs that one artifact, and starts
`world-engine --seed w5-good`. The console script seeds the scenario only when
the database is fresh, then serves on `0.0.0.0:8893` with `WORLD_DEV=0`.

The container stores its SQLite database at `/data/world.sqlite`, bind-mounted
to `deploy/demo/data` on the host. The first boot loads `w5-good`; every later
restart reuses the database. It never resets on boot.

## Prerequisites (operator supplies)

On the Oracle Cloud VM (Ubuntu assumed):

- Docker Engine + Compose v2 (`docker compose version` works).
- Caddy **2.8 or newer** (`basic_auth` directive; older installs use `basicauth`).
- Ports **80 and 443** open in both the Oracle Cloud security list and the host
  firewall (`sudo ufw allow 80,443/tcp` or equivalent).
- Passwordless sudo for the deploy user, or run the steps manually as root.
- A DuckDNS subdomain and its token (see below).
- An SSH key that can log in as `ubuntu@<public-ip>`.

On the machine running `deploy.sh`:

- `ssh`, `scp`, `base64`, `python3`; `rsync` is used when available.
- The private SSH key file (keep it `chmod 600`).

### Credentials you must provide

| Variable | Meaning |
| --- | --- |
| `DEMO_HOST` | `ubuntu@<public-ip>` |
| `DEMO_SSH_KEY` | path to the private key |
| `DEMO_DOMAIN` | e.g. `switch-demo.duckdns.org` |
| `DEMO_GUEST_PASSWORD` | plaintext guest password; never committed or written to disk |
| `DEMO_GUEST_USER` *(optional)* | basic-auth username, default `guest` |
| `DEMO_REMOTE_DIR` *(optional)* | remote checkout, default `/home/ubuntu/switch-world-demo` |
| `DUCKDNS_TOKEN` *(optional)* | refreshes the DuckDNS A record when set |
| `DUCKDNS_DOMAIN` *(optional)* | defaults to `DEMO_DOMAIN` minus `.duckdns.org` |

Never commit `.env`, the password, or generated hashes. Put the exports in
your shell or a local untracked file, not in this repository.

## DuckDNS

1. Sign in at <https://www.duckdns.org>, create a subdomain (e.g.
   `switch-demo`), and copy the token.
2. Point it at the VM public IP. Either let `deploy.sh` do it when
   `DUCKDNS_TOKEN` is set, or run:
   ```bash
   curl "https://www.duckdns.org/update?domains=switch-demo&token=<token>&ip=<public-ip>"
   ```
3. Wait for DNS (`dig +short switch-demo.duckdns.org`) to return the VM IP
   before Caddy requests a certificate.

Caddy obtains the TLS certificate automatically once ports 80/443 are reachable
and DNS resolves.

## Caddy: do not overwrite the main Caddyfile

`deploy.sh` installs only `/etc/caddy/conf.d/switch-world.caddy` and refuses to
run if the main Caddyfile does not import `conf.d`. If Caddy already serves
other sites, add exactly one line to `/etc/caddy/Caddyfile`:

```caddyfile
import /etc/caddy/conf.d/*.caddy
```

Then validate and reload:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

The script renders `Caddyfile.snippet` from `DEMO_DOMAIN`,
`DEMO_GUEST_USER` and the bcrypt hash. It never writes the plaintext password
anywhere; the hash file is installed as `root:caddy` mode `640`.

## Deploy

```bash
cd /path/to/switch-world

export DEMO_HOST='ubuntu@203.0.113.10'
export DEMO_SSH_KEY="$HOME/.ssh/oracle-demo"
export DEMO_DOMAIN='switch-demo.duckdns.org'
export DEMO_GUEST_PASSWORD='<choose-a-strong-password>'
export DEMO_GUEST_USER='guest'                 # optional
export DUCKDNS_TOKEN='<token>'                 # optional
export DUCKDNS_DOMAIN='switch-demo'            # optional

chmod 600 "$DEMO_SSH_KEY"

# 1. See exactly what will happen; touches nothing.
./deploy/demo/deploy.sh --dry-run

# 2. Deploy.
./deploy/demo/deploy.sh
```

The script:

1. Checks SSH reachability and remote `docker`, `docker compose`, `caddy`, sudo.
2. Syncs the app tree (excluding `.git`, `.venv`, local `data/`, `.env`) to
   `$DEMO_REMOTE_DIR`.
3. Creates `deploy/demo/data` and chowns it to uid `10001`.
4. Runs `docker compose -f deploy/demo/docker-compose.yml up -d --build`.
5. Polls `http://127.0.0.1:8893/health` for up to 60 seconds.
6. Generates the bcrypt hash remotely with `caddy hash-password`.
7. Renders and installs `/etc/caddy/conf.d/switch-world.caddy` (mode 640).
8. Validates the full Caddy config and reloads Caddy.
9. Optionally updates DuckDNS.

Generate a password and, if you want to preview a hash locally:

```bash
openssl rand -base64 24
caddy hash-password --plaintext 'your-password'   # requires Caddy locally
```

## Verify

```bash
# From anywhere: basic auth should be required, then /health returns JSON.
curl -i "https://$DEMO_DOMAIN/health"
curl -u "$DEMO_GUEST_USER:<password>" "https://$DEMO_DOMAIN/health"

# From the VM: container health and logs.
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
  "cd $DEMO_REMOTE_DIR && docker compose -f deploy/demo/docker-compose.yml ps"
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
  "cd $DEMO_REMOTE_DIR && docker compose -f deploy/demo/docker-compose.yml logs -f --tail=100"

# Loopback only (never publicly exposed):
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" "curl -s http://127.0.0.1:8893/health"
```

Browse `https://$DEMO_DOMAIN/` with the guest credentials. Useful read-only
endpoints: `/api/state`, `/api/canon`, `/api/matrix`, `/api/scenarios`,
`/api/scenarios/current`, `/api/takes`, `/api/takes/current`, `/api/clock`,
`/api/friends`, `/api/safety`, `/api/who-knows/<key>`, `/api/scene-card`,
`/api/scene-card.md`, `/api/studio/summary`.

## Logs and troubleshooting

| Symptom | Check |
| --- | --- |
| 502 from Caddy | `docker compose ... ps`; container must be healthy and on `127.0.0.1:8893` |
| Container exits at boot | logs show the non-root user cannot write `/data`; run `sudo chown -R 10001:10001 $DEMO_REMOTE_DIR/deploy/demo/data` |
| Caddy TLS fails | DNS not pointing at the VM, or ports 80/443 blocked in the Oracle security list |
| Caddy validate fails | inspect `/etc/caddy/conf.d/switch-world.caddy`; hash must start with `$2` |
| Dashboard buttons error | expected for mutating actions with `WORLD_DEV=0`; browsing stays functional |

To rerun a build after syncing code:

```bash
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
  "cd $DEMO_REMOTE_DIR && docker compose -f deploy/demo/docker-compose.yml up -d --build"
```

To intentionally reset the demo world (destroys guest-visible state):

```bash
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
  "cd $DEMO_REMOTE_DIR && docker compose -f deploy/demo/docker-compose.yml down"
ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
  "rm -rf $DEMO_REMOTE_DIR/deploy/demo/data"
# next `up` reseeds w5-good
```

## Rollback (manual; the script never does this for you)

1. Remove only the demo site block:
   ```bash
   ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
     "sudo -n rm -f /etc/caddy/conf.d/switch-world.caddy"
   ```
2. Validate and reload Caddy so the other sites keep working:
   ```bash
   ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
     "sudo -n caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo -n systemctl reload caddy"
   ```
3. Stop and remove the container:
   ```bash
   ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" \
     "cd $DEMO_REMOTE_DIR && docker compose -f deploy/demo/docker-compose.yml down"
   ```
4. Optionally delete the checkout and its data:
   ```bash
   ssh -i "$DEMO_SSH_KEY" "$DEMO_HOST" "rm -rf $DEMO_REMOTE_DIR"
   ```
5. Optionally point DuckDNS elsewhere or leave it; the hostname simply stops
   answering on this VM.

If Caddy is shared with other sites, step 1 is the only change that matters:
removing the single `conf.d` file and reloading restores the previous config.

## Local checks (no deployment)

```bash
cd /path/to/switch-world
docker compose -f deploy/demo/docker-compose.yml config >/dev/null && echo compose-ok
python3 -m py_compile deploy/demo/entrypoint.py && echo entrypoint-ok
bash -n deploy/demo/deploy.sh && echo deploy-sh-ok
```
