PY ?= .venv/bin/python

.PHONY: check lint test web run

check: lint test web

lint:
	uv run --with ruff ruff check world_engine director gateway mcp tests
	$(PY) -m compileall -q world_engine director gateway mcp

test:
	$(PY) -m pytest -q

web:
	node --check web/app.js
	node --check web/cast.js

run:
	$(PY) -m world_engine
