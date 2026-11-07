"""Compatibility shim: the MCP surface now lives in ``switch_world.interfaces.mcp``.

Import-only.  New code should import :func:`create_mcp` from
:mod:`switch_world.interfaces.mcp.server`; this module exists for the step-7
rollback window and for callers that still import ``world_engine.mcp_server``.
"""
from __future__ import annotations

from switch_world.interfaces.mcp.server import create_mcp

__all__ = ["create_mcp"]
