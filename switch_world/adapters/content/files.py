"""Filesystem-backed authored content.

The content root is injected (normally the repository's ``world/`` directory).
Each file is parsed once and cached against its ``mtime``; parsing the story
bible and social policy on every turn was a verified defect. ``parse_count``
exposes cache misses so a test can prove parse-once behaviour.

A root may also be the repository root: if ``<root>/canon.json`` is absent the
store looks under ``<root>/world/`` as well, so both spellings of "content
root" work during the v2 migration.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from switch_world.domain.ports.content import ContentNotFound


class FileContentStore:
    """Read-only content store with an mtime cache and a parse counter."""

    def __init__(self, content_root: Path | str) -> None:
        self.root = Path(content_root)
        self._cache: dict[Path, tuple[tuple[int, int], Any]] = {}
        self.parses: dict[Path, int] = {}
        self.parse_count = 0

    # ---- public contract --------------------------------------------------
    def canon(self) -> Mapping[str, Any]:
        return self._load_json("canon.json")

    def social(self) -> Mapping[str, Any]:
        return self._load_json("social.json")

    def characters(self) -> Mapping[str, str]:
        directory = self._find_dir("characters")
        if directory is None:
            return {}
        characters: dict[str, str] = {}
        for path in sorted(directory.glob("*.md")):
            if path.stem.lower() == "readme":
                continue
            characters[path.stem] = self._read_text(path)
        return characters

    def scenario(self, scenario_id: str) -> Mapping[str, Any]:
        safe_id = self._safe_id(scenario_id, "scenario id")
        return self._load_json(f"scenarios/{safe_id}.json")

    def takes(self) -> list[Mapping[str, Any]]:
        directory = self._find_dir("takes")
        if directory is None:
            return []
        return [self._load_json_file(path) for path in sorted(directory.glob("*.json"))]

    # ---- cache ------------------------------------------------------------
    def _find_dir(self, relative: str) -> Path | None:
        direct = self.root / relative
        if direct.is_dir():
            return direct
        nested = self.root / "world" / relative
        if nested.is_dir():
            return nested
        return None

    def _find_file(self, relative: str) -> Path:
        direct = self.root / relative
        if direct.is_file():
            return direct
        nested = self.root / "world" / relative
        if nested.is_file():
            return nested
        raise ContentNotFound(
            f"content file {relative!r} not found under {self.root} "
            f"(also tried {self.root / 'world'})"
        )

    def _load_json(self, relative: str) -> Mapping[str, Any]:
        return self._load_json_file(self._find_file(relative))

    def _load_json_file(self, path: Path) -> Mapping[str, Any]:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == key:
            return cached[1]
        value = json.loads(path.read_text(encoding="utf-8"))
        self._cache[path] = (key, value)
        self.parse_count += 1
        self.parses[path] = self.parses.get(path, 0) + 1
        return value

    def _read_text(self, path: Path) -> str:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == key:
            return cached[1]
        value = path.read_text(encoding="utf-8")
        self._cache[path] = (key, value)
        self.parse_count += 1
        self.parses[path] = self.parses.get(path, 0) + 1
        return value

    @staticmethod
    def _safe_id(value: str, label: str) -> str:
        text = str(value).strip()
        if not text or "/" in text or "\\" in text or text in (".", ".."):
            raise ContentNotFound(f"invalid {label}: {value!r}")
        return text


__all__ = ["FileContentStore"]
