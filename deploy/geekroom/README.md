# Four Hearts — Geek Room demo

The Geek Room submission runs the same world as `switch-world`, under a
different project name, with **every character call through Bifrost** and the
**Tavily** layer visible in the world feed.

- `bifrost` — self-hosted `maximhq/bifrost:v2.5.0`, one `openai` provider pointed
  at `https://api.deepseek.com/v1`, model `openai/deepseek-flash`.
- `world` — the v2 image, `WORLD_AGENT_MODE=bifrost`, loopback `:8894`.
- Caddy terminates TLS and proxies the root to `127.0.0.1:8894` once a site
  block for `FOUR_HEARTS_DOMAIN` is installed (see **Public URL**).

No Tavily key is required for the packaged demo: `TAVILY_OFFLINE=1` records a
clearly labelled fixture event. A live key is a drop-in (`TAVILY_API_KEY`,
unset `TAVILY_OFFLINE`).

## Env

`/home/ubuntu/four-hearts/.env` (mode 600, never committed):

```bash
DEEPSEEK_API_KEY=...
BIFROST_ENCRYPTION_KEY=<32 chars>
BIFROST_API_KEY=four-hearts-local
TAVILY_OFFLINE=1
# TAVILY_API_KEY=tvly-...   # and remove TAVILY_OFFLINE for live search
```

## Start

```bash
cd /home/ubuntu/four-hearts
mkdir -p deploy/geekroom/data
sudo chown -R 10001:10001 deploy/geekroom/data
docker compose --env-file .env -f deploy/geekroom/docker-compose.yml up -d --build
```

## Seed the Geek Room evidence

```bash
# One Tavily world event (offline fixture is labelled as such)
docker compose --env-file .env -f deploy/geekroom/docker-compose.yml \
  exec -T world python scripts/world-tick.py --once

# One café beat through Bifrost, so the request log has real rows
docker compose --env-file .env -f deploy/geekroom/docker-compose.yml \
  exec -T world director --bifrost
```

## Test after every deploy

```bash
curl -s http://127.0.0.1:8894/health
curl -s http://127.0.0.1:8894/api/state | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['revision'], len(d['events']))"
curl -s http://127.0.0.1:8894/api/bifrost/usage
curl -s http://127.0.0.1:8080/v1/models | head -c 300
docker exec four-hearts-world sh -c 'tail -3 /data/logs/bifrost.jsonl'
curl -s -X POST http://127.0.0.1:8894/api/group/say \
  -H 'Content-Type: application/json' \
  -d '{"message":"Evening, all. What is good tonight?","timeout":90}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([(r['character'], r['text'][:60]) for r in d.get('replies',[])])"
```

The last call must return two or three in-character lines and grow the Bifrost
log. The dashboard at `/` must show the world event in the feed and the Bifrost
usage in Settings.

## Public URL

No public hostname is defined in this repository, and the compose file publishes
loopback only. Until a DNS name points at the VM and Caddy is reloaded, the demo
is reachable only at `http://127.0.0.1:8894` on the host. Set the domain
explicitly before claiming a public URL:

```bash
export FOUR_HEARTS_DOMAIN=...   # e.g. the existing DuckDNS name
sed "s/__FOUR_HEARTS_DOMAIN__/${FOUR_HEARTS_DOMAIN}/" \
  deploy/geekroom/Caddyfile.snippet \
  | sudo tee /etc/caddy/conf.d/four-hearts.caddy
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The snippet reverses `/` to `127.0.0.1:8894`; keep `/mattermost/*` as-is in the
main Caddyfile. Validate and reload before declaring the deploy done.

## Rollback

The previous Flip demo is a separate compose project (`switch-world-demo`,
`:8893`). Stop this project, point Caddy back to `:8893`, reload, and start the
old project if it was stopped. Images are tagged, so no rebuild is needed.
