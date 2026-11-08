from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "gen-js-contract.py"
VOCAB = ROOT / "web" / "js" / "vocab.js"


def test_vocab_js_matches_the_generator() -> None:
    assert VOCAB.exists(), "web/js/vocab.js must be checked in"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "web/js/vocab.js is stale; run scripts/gen-js-contract.py\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
