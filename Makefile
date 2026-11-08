PY ?= .venv/bin/python

.PHONY: check lint test web cov run

check: lint test web

lint:
	uv run --with ruff ruff check switch_world tests
	$(PY) -m compileall -q switch_world

test:
	$(PY) -m pytest -q

web:
	for f in web/cast.js web/js/*.js web/js/render/*.js; do node --check "$$f"; done
	node --test "web/js/*.test.js"
	$(PY) scripts/gen-js-contract.py --check

cov:
	$(PY) -m pytest -q --cov=switch_world --cov-report=term-missing

run:
	$(PY) -m switch_world.interfaces.cli.world
