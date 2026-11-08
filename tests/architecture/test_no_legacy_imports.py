"""The v1 packages are deleted; nothing may import them again.

Two guards, because either one alone has a blind spot:

* a static scan reads every Python file and inspects its ``Import`` /
  ``ImportFrom`` nodes, which catches code paths a test suite may not execute;
* an import hook runs the banned names through a real ``sys.meta_path`` finder,
  which catches a module that is somehow reintroduced or shadowed on the path.

The third-party ``mcp`` package is a dependency and stays importable. The
deleted ``mcp/`` was a *directory in this repository*, so the guard bans a local
``mcp`` package (a spec whose origin is inside the checkout) rather than the
installed distribution.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DELETED_PACKAGES = ("world_engine", "director", "gateway")
LOCAL_MCP = REPO_ROOT / "mcp"
SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".claude",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "scratch",
    "recordings",
}


def _python_files():
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def _imported_names(path: Path) -> list[str]:
    """Every module named by an import statement in ``path``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _is_banned(name: str) -> bool:
    return any(name == package or name.startswith(package + ".")
               for package in DELETED_PACKAGES)


def test_no_legacy_import_statements():
    offenders: list[str] = []
    for path in _python_files():
        for name in _imported_names(path):
            if _is_banned(name):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert offenders == [], (
        "import the switch_world target instead of the deleted package:\n"
        + "\n".join(offenders)
    )


def test_no_local_mcp_package():
    assert not LOCAL_MCP.exists(), "the local mcp/ package was deleted in v2"
    spec = importlib.util.find_spec("mcp")
    if spec is not None and spec.origin:
        origin = Path(spec.origin).resolve()
        assert LOCAL_MCP not in origin.parents, (
            f"a local mcp package shadows the mcp dependency: {origin}"
        )


@pytest.mark.parametrize("package", DELETED_PACKAGES)
def test_deleted_packages_cannot_be_imported(package):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(package)


class _LegacyImportGuard:
    """A meta-path finder that fails loudly for a deleted package."""

    def __init__(self, packages: tuple[str, ...]) -> None:
        self.packages = packages

    def find_module(self, fullname, path=None):  # pragma: no cover - py<3.12 API
        return None

    def find_spec(self, fullname, path=None, target=None):
        if any(
            fullname == package or fullname.startswith(package + ".")
            for package in self.packages
        ):
            raise AssertionError(f"blocked import of deleted package: {fullname}")
        return None


def test_import_hook_blocks_a_reintroduced_legacy_package():
    guard = _LegacyImportGuard(DELETED_PACKAGES)
    sys.meta_path.insert(0, guard)
    try:
        for package in DELETED_PACKAGES:
            # Drop any cached module first: the guard must run even then.
            for name in list(sys.modules):
                if name == package or name.startswith(package + "."):
                    del sys.modules[name]
            with pytest.raises((AssertionError, ModuleNotFoundError)):
                importlib.import_module(package)
    finally:
        sys.meta_path.remove(guard)


def test_switch_world_does_not_reimport_a_legacy_package_at_runtime():
    """Importing the whole v2 package must never touch a deleted module."""
    guard = _LegacyImportGuard(DELETED_PACKAGES)
    sys.meta_path.insert(0, guard)
    try:
        import switch_world  # noqa: F401
        import switch_world.compat  # noqa: F401
        import switch_world.container  # noqa: F401
        import switch_world.interfaces.http.app  # noqa: F401
        import switch_world.interfaces.mcp.server  # noqa: F401
    finally:
        sys.meta_path.remove(guard)
