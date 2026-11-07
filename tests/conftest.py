"""Hermetic defaults for the suite.

`world_engine.config` reads the environment at import time, so these values are
pinned here (conftest is imported before any test module) rather than in a
fixture. Tests that need another mode monkeypatch the module values explicitly.
"""
from __future__ import annotations

import os
import tempfile

os.environ["WORLD_DEV"] = "1"
os.environ["WORLD_AGENT_MODE"] = "switch"

# Never write a world database, exports or request logs into the checkout.
_SESSION_DATA = tempfile.mkdtemp(prefix="switch-world-tests-")
os.environ["WORLD_DATA_DIR"] = _SESSION_DATA
os.environ["WORLD_DB"] = os.path.join(_SESSION_DATA, "world.sqlite")

# Ambient credentials must not change what the fakes return.
for _key in list(os.environ):
    if _key.startswith(("BIFROST_", "SWITCH_", "TAVILY_", "WORLD_TOKEN_")):
        os.environ.pop(_key, None)
