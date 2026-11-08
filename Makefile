PY ?= .venv/bin/python

.PHONY: check lint test web run

check: lint test web

lint:
	uv run --with ruff ruff check switch_world world_engine director gateway tests
	$(PY) -m compileall -q switch_world world_engine director gateway

test:
	$(PY) -m pytest -q

web:
	for f in web/cast.js web/js/*.js web/js/render/*.js; do node --check "$$f"; done
	node --test "web/js/*.test.js"
	$(PY) scripts/gen-js-contract.py --check

run:
	$(PY) -m world_engine
