"""Enforce the one-way dependency direction of the v2 layers.

The intended graph is Ports and Adapters:

* ``domain/`` is the centre. It may use the standard library and other
  ``switch_world.domain`` modules, nothing else.
* ``application/`` may use ``domain`` and ``config``. It must never import
  ``interfaces``. Seven composition-aware application modules still name
  concrete adapter defaults; that seam is pinned in
  ``APPLICATION_ADAPTER_SEAM`` so it cannot grow silently.
* ``adapters/`` may use ``domain``, ``config`` and other adapters. It must never
  import ``application`` or ``interfaces``.
* ``interfaces/`` is the outer driving edge and may use any inner module.

Imports are read from the AST, so a name in a docstring or a string literal is
not a dependency. Relative imports are resolved against the file's package.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "switch_world"
LAYERS = ("domain", "application", "adapters", "interfaces")

# Application modules that still construct a concrete adapter default. These
# are the pre-existing composition seams (WorldService/store, default model and
# transport factories, the Tavily probe, the Switch log). Keep this list
# shrinking; never add to it without moving the construction to ``container``.
APPLICATION_ADAPTER_SEAM = {
    "switch_world/application/arbiter.py",
    "switch_world/application/beat_runners.py",
    "switch_world/application/defaults.py",
    "switch_world/application/facade.py",
    "switch_world/application/simulate.py",
    "switch_world/application/switch_log.py",
    "switch_world/application/tavily_beat.py",
}


def _package(path: Path) -> str:
    dotted = ".".join(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if path.name == "__init__.py":
        return dotted.rsplit(".", 1)[0]
    return dotted.rsplit(".", 1)[0]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package(path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = "." * node.level + (node.module or "")
                found.append(importlib.util.resolve_name(relative, package))
            elif node.module:
                found.append(node.module)
    return found


def _layer_of(name: str) -> str | None:
    prefix = "switch_world."
    if not name.startswith(prefix):
        return None
    head = name[len(prefix):].split(".", 1)[0]
    return head if head in LAYERS else None


def _files(layer: str):
    for path in (PACKAGE_ROOT / layer).rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def test_domain_is_stdlib_and_domain_only():
    offenders: list[str] = []
    for path in _files("domain"):
        for name in _imports(path):
            if name == "__future__" or name.split(".", 1)[0] in sys.stdlib_module_names:
                continue
            if name == "switch_world.domain" or name.startswith("switch_world.domain."):
                continue
            offenders.append(f"{_relative(path)}: {name}")
    assert offenders == [], (
        "domain may only import the standard library and switch_world.domain:\n"
        + "\n".join(offenders)
    )


def test_application_never_imports_interfaces_or_unlisted_adapters():
    offenders: list[str] = []
    for path in _files("application"):
        for name in _imports(path):
            layer = _layer_of(name)
            if layer == "interfaces":
                offenders.append(f"{_relative(path)}: {name}")
            elif layer == "adapters" and _relative(path) not in APPLICATION_ADAPTER_SEAM:
                offenders.append(f"{_relative(path)}: {name}")
    assert offenders == [], (
        "application must depend inward; move concrete wiring to container.py:\n"
        + "\n".join(offenders)
    )


def test_application_adapter_seam_does_not_grow():
    discovered = {
        _relative(path)
        for path in _files("application")
        if any(_layer_of(name) == "adapters" for name in _imports(path))
    }
    assert discovered == APPLICATION_ADAPTER_SEAM, (
        "the application->adapter seam changed; update the allowlist only after "
        "moving the construction to the composition root. "
        f"new={sorted(discovered - APPLICATION_ADAPTER_SEAM)} "
        f"gone={sorted(APPLICATION_ADAPTER_SEAM - discovered)}"
    )


def test_adapters_never_import_application_or_interfaces():
    offenders: list[str] = []
    for path in _files("adapters"):
        for name in _imports(path):
            if _layer_of(name) in {"application", "interfaces"}:
                offenders.append(f"{_relative(path)}: {name}")
    assert offenders == [], (
        "adapters implement inward-facing ports; they must not know these layers:\n"
        + "\n".join(offenders)
    )


def test_interfaces_are_the_only_outer_edge():
    """``interfaces`` may use inner layers; no inner layer may use it."""
    for source in ("domain", "application", "adapters"):
        for path in _files(source):
            for name in _imports(path):
                assert _layer_of(name) != "interfaces", (
                    f"{_relative(path)} imports the outer interface layer: {name}"
                )


def test_every_layer_package_exists():
    for layer in LAYERS:
        assert (PACKAGE_ROOT / layer / "__init__.py").is_file(), layer
