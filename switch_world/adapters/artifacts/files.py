"""Filesystem artifact store with an injected export directory.

Only :meth:`write` creates directories or files. ``read`` and ``list`` are
side-effect free, so an HTTP GET that renders a scene card cannot leave an
export behind; an explicit export use case calls ``write``.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from switch_world.domain.ports.artifacts import ArtifactNotFound, ArtifactRef

DEFAULT_MEDIA_TYPE = "text/markdown"


class FileArtifactStore:
    """Write named text artifacts under one directory."""

    def __init__(self, export_dir: Path | str) -> None:
        self.export_dir = Path(export_dir)

    def write(
        self, name: str, content: str, *, media_type: str = DEFAULT_MEDIA_TYPE
    ) -> ArtifactRef:
        path = self._path(name, create_parent=True)
        path.write_text(content, encoding="utf-8")
        return ArtifactRef(
            name=self._normalize(name),
            path=str(path),
            media_type=media_type,
            size=len(content.encode("utf-8")),
        )

    def read(self, name: str) -> str:
        path = self._path(name)
        if not path.is_file():
            raise ArtifactNotFound(f"artifact {name!r} not found in {self.export_dir}")
        return path.read_text(encoding="utf-8")

    def list(self, prefix: str = "") -> list[ArtifactRef]:
        if not self.export_dir.is_dir():
            return []
        normalized_prefix = prefix.strip("/")
        refs: list[ArtifactRef] = []
        for path in sorted(self.export_dir.rglob("*")):
            if not path.is_file():
                continue
            name = path.relative_to(self.export_dir).as_posix()
            if normalized_prefix and not name.startswith(normalized_prefix):
                continue
            media_type = mimetypes.guess_type(name)[0] or DEFAULT_MEDIA_TYPE
            refs.append(
                ArtifactRef(
                    name=name,
                    path=str(path),
                    media_type=media_type,
                    size=path.stat().st_size,
                )
            )
        return refs

    # ---- paths ------------------------------------------------------------
    @staticmethod
    def _normalize(name: str) -> str:
        return str(name).strip().lstrip("/")

    def _path(self, name: str, *, create_parent: bool = False) -> Path:
        normalized = self._normalize(name)
        relative = Path(normalized)
        if not normalized or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"artifact name must stay inside the export dir: {name!r}")
        path = self.export_dir / relative
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path


__all__ = ["FileArtifactStore"]
