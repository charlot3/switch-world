"""MCP server construction.

The server is an interface adapter: it knows the MCP protocol and the tool
names, and delegates every decision to :class:`WorldService`.  Importing this
module constructs nothing; :func:`create_mcp` is always called explicitly by
the app factory (or by tests).
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from switch_world.application.facade import WorldService

from .tools import TOOL_NAMES, register_tools

SERVER_NAME = "switch-world"
DESCRIPTION = (
    "A small social world with provenance-tracked beliefs and relationships."
)
INSTRUCTIONS = (
    "You are a character in a social world. Read your own beliefs with "
    "world__recall before making a claim about another person. Write what you "
    "learn with world__remember, including the source and a proposition_key. "
    "Write how you feel with world__update_relationship. Never reveal a private "
    "belief unless your disclosure policy says so. When a question is about the "
    "present or a fact after your training, call world__search_web instead of "
    "guessing; record what you learn from it as an observation."
)


def create_mcp(service: WorldService) -> MCPServer:
    """Build the actor-scoped MCP surface for ``service``."""
    mcp = MCPServer(
        SERVER_NAME,
        description=DESCRIPTION,
        instructions=INSTRUCTIONS,
    )
    return register_tools(mcp, service)


__all__ = ["INSTRUCTIONS", "SERVER_NAME", "create_mcp", "TOOL_NAMES"]
