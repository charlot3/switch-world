"""Architectural guardrails for the persistence refactor.

Production code must use the store. Only ``WorldService._conn`` may expose a raw
connection (and it is deprecated); scenario/take loaders must not run SQL.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PACKAGES = ("switch_world", "world_engine", "director", "gateway", "mcp")
SERVICE = REPO_ROOT / "world_engine" / "service.py"
SCHEMA = REPO_ROOT / "switch_world" / "adapters" / "persistence" / "schema.py"
STORE = REPO_ROOT / "switch_world" / "adapters" / "persistence" / "store.py"


def _python_files():
    for package in PRODUCTION_PACKAGES:
        root = REPO_ROOT / package
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def test_no_production_module_uses_the_private_connection_helper():
    offenders = []
    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "._conn(" in line or "._conn (" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == [], (
        "use store.transaction() instead of the deprecated service._conn():\n"
        + "\n".join(offenders)
    )


def test_private_connection_helper_is_marked_deprecated():
    text = SERVICE.read_text(encoding="utf-8")
    marker = text.index("def _conn(self)")
    docstring = text[marker:marker + 400]
    assert "Deprecated" in docstring


def test_only_the_schema_module_opens_sqlite_directly():
    offenders = []
    for path in _python_files():
        if path == SCHEMA:
            continue
        text = path.read_text(encoding="utf-8")
        if "sqlite3.connect(" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_scenarios_and_takes_contain_no_sql():
    for relative in ("world_engine/scenarios.py", "world_engine/takes.py"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "conn.execute" not in text, relative
        assert "SELECT " not in text, relative
        assert "INSERT INTO" not in text, relative
        assert "UPDATE " not in text, relative
        assert "DELETE FROM" not in text, relative


def test_store_is_the_only_persistence_adapter():
    assert STORE.is_file()
    text = STORE.read_text(encoding="utf-8")
    assert "def snapshot" in text
    assert "def transaction" in text
