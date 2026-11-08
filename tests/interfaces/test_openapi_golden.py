"""OpenAPI is a contract: a field rename or route move fails this snapshot.

Regenerate deliberately after an intended contract change::

    .venv/bin/python - <<'PY'
    import json, tempfile
    from pathlib import Path
    from switch_world.interfaces.http.app import create_app
    from switch_world import config
    from switch_world.application.facade import WorldService
    tmp = Path(tempfile.mkdtemp())
    app = create_app(WorldService(db_path=tmp / "world.sqlite", state_dir=config.STATE_DIR))
    Path("tests/interfaces/openapi_golden.json").write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\\n", encoding="utf-8"
    )
    PY
"""
from __future__ import annotations

import json
from pathlib import Path

from switch_world.interfaces.http.app import create_app
from switch_world import config
from switch_world.application.facade import WorldService

GOLDEN = Path(__file__).with_name("openapi_golden.json")


def _document(tmp_path) -> dict:
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    return create_app(service).openapi()


def test_openapi_matches_the_golden_snapshot(tmp_path):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert _document(tmp_path) == expected


def test_every_json_route_declares_a_response_model(tmp_path):
    document = _document(tmp_path)
    missing = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            responses = operation.get("responses", {})
            # A plain-text/file route documents its media type instead of a
            # pydantic model; every other 200 must have a JSON schema.
            content = responses.get("200", {}).get("content", {})
            if "application/json" not in content:
                continue
            if "schema" not in content["application/json"]:
                missing.append(f"{method.upper()} {path}")
    assert missing == []
