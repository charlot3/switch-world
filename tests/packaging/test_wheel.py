"""The built wheel starts.

This is the regression test for the audited packaging failure: the wheel used
to omit ``world/`` and ``web/`` and both console scripts crashed on import.
The test builds the wheel, installs it into a clean venv (uv when available,
otherwise venv + pip), and starts the installed package from a directory that
is not the checkout.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import venv
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PACKAGED = (
    "switch_world/resources/world/canon.json",
    "switch_world/resources/world/social.json",
    "switch_world/resources/world/state/characters.json",
    "switch_world/resources/web/index.html",
    "switch_world/resources/agents/alice/IDENTITY.md",
    "switch_world/interfaces/cli/world.py",
    "switch_world/interfaces/cli/director.py",
)


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, (
        f"{' '.join(cmd)} failed ({result.returncode})\n"
        f"stdout:\n{result.stdout[-4000:]}\n"
        f"stderr:\n{result.stderr[-4000:]}"
    )


def _build_wheel(out_dir: Path) -> Path:
    uv = shutil.which("uv")
    if uv:
        _run([uv, "build", "--wheel", "--out-dir", str(out_dir)], cwd=REPO_ROOT)
    else:
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(out_dir),
                ".",
            ],
            cwd=REPO_ROOT,
        )
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def _install_wheel(wheel: Path, venv_dir: Path) -> Path:
    uv = shutil.which("uv")
    if uv:
        _run([uv, "venv", "--python", sys.executable, str(venv_dir)], cwd=REPO_ROOT)
        python = venv_dir / "bin" / "python"
        _run(
            [uv, "pip", "install", "--python", str(python), str(wheel)],
            cwd=REPO_ROOT,
        )
    else:
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = venv_dir / "bin" / "python"
        _run([str(python), "-m", "pip", "install", str(wheel)], cwd=REPO_ROOT)
    return python


def _env(data_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "WORLD_DEV": "1",
            "WORLD_AGENT_MODE": "local",
            "WORLD_DATA_DIR": str(data_dir),
            "WORLD_DB": str(data_dir / "world.sqlite"),
        }
    )
    return env


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    return _build_wheel(tmp_path_factory.mktemp("dist"))


@pytest.fixture(scope="module")
def installed(wheel, tmp_path_factory):
    venv_dir = tmp_path_factory.mktemp("wheel-venv")
    python = _install_wheel(wheel, venv_dir)
    return venv_dir, python


def test_wheel_contains_packaged_resources(wheel):
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = [name for name in PACKAGED if name not in names]
    assert not missing, missing
    # The force-included content must not leak the checkout's top-level names.
    assert "world/canon.json" not in names
    assert "web/index.html" not in names


def test_installed_package_serves_app(installed, tmp_path):
    venv_dir, python = installed
    data_dir = tmp_path / "data"
    script = textwrap.dedent(
        """
        import json
        import os
        import sys

        import switch_world
        from fastapi.testclient import TestClient
        from switch_world.config import load_settings
        from switch_world.container import build_container
        from switch_world.interfaces.http.app import create_app

        settings = load_settings(os.environ)
        resolved = {
            "package": switch_world.__file__,
            "canon": str(settings.content_root / "canon.json"),
            "social": str(settings.content_root / "social.json"),
            "index": str(settings.web_dir / "index.html"),
            "agents": str(settings.agents_dir / "alice" / "IDENTITY.md"),
        }
        for name, path in resolved.items():
            if name == "package":
                continue
            if not os.path.isfile(path):
                raise SystemExit(f"{name} missing from wheel: {path}")

        container = build_container(settings)
        app = create_app(container.service, settings, container=container)
        with TestClient(app) as client:
            for path in ("/health", "/api/state", "/"):
                response = client.get(path)
                if response.status_code != 200:
                    raise SystemExit(
                        f"{path} returned {response.status_code}: {response.text[:400]}"
                    )
        print(json.dumps(resolved))
        """
    )
    result = subprocess.run(
        [str(python), "-c", script],
        cwd=str(tmp_path),
        env=_env(data_dir),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    resolved = json.loads(result.stdout.strip().splitlines()[-1])
    assert str(venv_dir) in resolved["package"]
    assert resolved["package"].endswith("site-packages/switch_world/__init__.py")
    assert (data_dir / "world.sqlite").is_file()


def test_console_scripts_help(installed, tmp_path):
    venv_dir, _python = installed
    data_dir = tmp_path / "help-data"
    env = _env(data_dir)
    for script in ("world-engine", "director"):
        result = subprocess.run(
            [str(venv_dir / "bin" / script), "--help"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert "usage:" in result.stdout.lower()
    # --help must not construct the app or create the data directory.
    assert not data_dir.exists()
