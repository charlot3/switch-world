# Bifrost local gateway

`data/config.json` is mounted at `/app/data/config.json` in the `maximhq/bifrost`
container. The default provider is **Ollama**, so the Geek Room demo runs without an
external API key.

```sh
scripts/run-bifrost.sh
# UI:   http://127.0.0.1:8080
# API:  http://127.0.0.1:8080/v1
```

The script also starts `scripts/ollama-proxy.py` when Ollama is bound to loopback only,
because Docker Desktop needs a host-reachable port (`host.docker.internal:11435`).

## Per-character routing

`world/models.json` is the source of truth the Python client uses:

- `model` — a provider-prefixed Bifrost model, e.g. `ollama/qwen3.8:27b-q4_K_M`
- `fallbacks` — provider/model strings passed to Bifrost's `fallbacks` field
- `temperature`, `max_tokens`
- `daily_tokens` — a local guard, mirrored by Bifrost governance when enabled
- `virtual_key_env` — optional `x-bf-vk` header

Override any of them without editing the file:

```sh
export BIFROST_MODEL_ALICE=anthropic/claude-sonnet-4-5
export BIFROST_FALLBACKS_ALICE=openai/gpt-4o-mini,ollama/qwen3.8:27b-q4_K_M
export BIFROST_VK_ALICE=...
```

To use OpenAI or Anthropic instead of Ollama, add the provider to `config.json` and set
the key in the container environment:

```json
"providers": {
  "anthropic": {
    "keys": [{
      "name": "anthropic-primary",
      "value": "env.ANTHROPIC_API_KEY",
      "models": ["*"],
      "weight": 1.0
    }]
  }
}
```

Then pass `-e ANTHROPIC_API_KEY=...` to `docker run` (or add it to `.env` and the run
script). The request shape does not change: `gateway/bifrost.py` always calls
`/v1/chat/completions`.

## Evidence

- Bifrost UI at `:8080` shows request logs, routing and provider health.
- `gateway/bifrost.py` writes one JSON line per request to `data/logs/bifrost.jsonl`.
- `data/bifrost_budget.json` holds the local daily token counter.
- `GET /api/bifrost/usage` returns the same counter and the configured models.
