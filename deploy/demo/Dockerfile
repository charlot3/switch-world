# switch-world guest demo image.
#
# Build context is the repository root:
#   docker build -f deploy/demo/Dockerfile -t switch-world-demo .
#
# The app is pure Python (fastapi/uvicorn/mcp/httpx/pydantic + stdlib sqlite3),
# so build-essential is not needed. Hatchling builds a pure-Python wheel.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build inputs for `pip install .` (the package list lives in pyproject.toml).
COPY pyproject.toml ./
COPY switch_world ./switch_world
COPY world_engine ./world_engine
COPY director ./director
COPY gateway ./gateway

RUN pip install --no-cache-dir .

# Runtime-only assets. These are not part of the wheel: world_engine resolves
# canon/scenarios/takes and the dashboard relative to the source tree at /app.
COPY world ./world
COPY web ./web
# Character identity/rules for the cloud reply path. Token-bearing connector
# configs are excluded by Dockerfile.dockerignore.
COPY agents ./agents
COPY deploy/demo/entrypoint.py ./deploy/demo/entrypoint.py

# Non-root runtime user. The bind-mounted /data directory must be writable by
# uid 10001 on the host (see README: chown -R 10001:10001 deploy/demo/data).
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /data /app

USER app

EXPOSE 8893

CMD ["python", "deploy/demo/entrypoint.py"]
