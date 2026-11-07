"""Read-only authored content contract.

Content is the story bible, social policy, scenario and take JSON, and the
character identity files. It is not world state: the application never writes
it, and a store may cache parsed values for the life of a container.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ContentNotFound(FileNotFoundError):
    """A requested authored file is absent."""


class ContentStore(Protocol):
    def canon(self) -> Mapping[str, Any]: ...

    def social(self) -> Mapping[str, Any]: ...

    def characters(self) -> Mapping[str, str]: ...

    def scenario(self, scenario_id: str) -> Mapping[str, Any]: ...

    def takes(self) -> list[Mapping[str, Any]]: ...


__all__ = ["ContentNotFound", "ContentStore"]
