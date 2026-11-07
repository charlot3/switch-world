"""Artifact contract: explicit writes to durable, user-facing files.

Reading or listing must never create directories or write files; a GET route
that renders a scene card must not leave an artifact behind.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ArtifactNotFound(FileNotFoundError):
    """The named artifact does not exist."""


@dataclass(frozen=True)
class ArtifactRef:
    """A stored artifact's public identity."""

    name: str
    path: str
    media_type: str = "text/markdown"
    size: int = 0


class ArtifactStore(Protocol):
    def write(
        self, name: str, content: str, *, media_type: str = "text/markdown"
    ) -> ArtifactRef: ...

    def read(self, name: str) -> str: ...

    def list(self, prefix: str = "") -> list[ArtifactRef]: ...


__all__ = ["ArtifactNotFound", "ArtifactRef", "ArtifactStore"]
