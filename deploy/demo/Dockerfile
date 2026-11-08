# switch-world guest demo image.
#
# Build context is the repository root:
#   docker build -f deploy/demo/Dockerfile -t switch-world-demo .
#
# The app is pure Python (fastapi/uvicorn/mcp/httpx/pydantic + stdlib sqlite3),
# so build-essential is not needed. Hatchling builds a pure-Python wheel with
# the authored content (world/, web/ and the agent identities) force-included,
# so the runtime image installs one artifact and does not copy those trees a
# second time.

# ---- build -----------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

# Everything hatch needs to build the wheel: the v2 code and the authored
# resources. `.gitignore` travels with the build so hatchling keeps ignoring
# credentials that a developer checkout may hold (`switch_world/.env`,
# `.switch/...`).
COPY pyproject.toml ./
COPY .gitignore ./
COPY switch_world ./switch_world
COPY world ./world
COPY web ./web
COPY agents ./agents

RUN pip wheel --no-cache-dir --no-deps --wheel-dir /dist .

# ---- runtime ---------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORLD_DB=/data/world.sqlite \
    WORLD_DATA_DIR=/data \
    WORLD_ENGINE_HOST=0.0.0.0 \
    WORLD_ENGINE_PORT=8893 \
    WORLD_DEV=0

WORKDIR /app

# One wheel carries the API, MCP endpoint, dashboard and agent identities.
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# Non-root runtime user. The bind-mounted /data directory must be writable by
# uid 10001 on the host (see README: chown -R 10001:10001 deploy/demo/data).
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /data

USER app

EXPOSE 8893

# The console script seeds w5-good only on a fresh database, then serves.
CMD ["world-engine", "--seed", "w5-good"]
