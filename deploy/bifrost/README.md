# Bifrost local gateway

`data/config.json` is mounted at `/app/data/config.json` in the `maximhq/bifrost`
container. The default provider is the **OpenCode Go adapter** on
`host.docker.internal:8090` (OpenAI-compatible), so the Geek Room demo uses the free
`opencode-go/deepseek-v4.1-flash` model already signed in on the machine. The Ollama
provider remains as an optional local fallback.

```sh
scripts/run-bifrost.sh
# OpenCode adapter: http://127.0.0.1:8090
# Bifrost UI:       http://127.0.0.1:8080
# Bifrost API:      http://127.0.0.1:8080/v1
```

The script starts `scripts/opencode-gateway.py` (the OpenAI-compatible adapter) and, if
needed, `scripts/ollama-proxy.py` for the fallback provider. The Bifrost `openai`
provider points at the adapter; the requested `openai/deepseek-v4.1-flash` is mapped to
the OpenCode model by the adapter.

## Per-character routing

`world/models.json` is the source of truth the Python client uses:

- `model` — a provider-prefixed Bifrost model, default `openai/deepseek-v4.1-flash`
  (the adapter calls `opencode-go/deepseek-v4.1-flash`)
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

To use OpenAI or Anthropic instead of the OpenCode adapter, add the provider to
`config.json` and set the key in the container environment:

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
script). The request shape does not change: `switch_world/adapters/models/bifrost_compat.py` always calls
`/v1/chat/completions`.

## Evidence

- Bifrost UI at `:8080` shows request logs, routing and provider health.
- `switch_world/adapters/models/bifrost_compat.py` writes one JSON line per request to `data/logs/bifrost.jsonl`.
- `data/bifrost_budget.json` holds the local daily token counter.
- `GET /api/bifrost/usage` returns the same counter and the configured models.
