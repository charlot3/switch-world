"""MCP interface: the actor-scoped tool surface and its server."""
from __future__ import annotations

from .server import SERVER_NAME, create_mcp
from .tools import TOOL_NAMES, register_tools

__all__ = ["SERVER_NAME", "TOOL_NAMES", "create_mcp", "register_tools"]
