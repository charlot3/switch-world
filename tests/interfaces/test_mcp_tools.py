"""The advertised MCP surface is exactly the documented surface.

The tool names, input schemas and result shapes are a public contract: agents
in the demo are configured against them, so a rename or a dropped tool must
fail here before it reaches the cast.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from switch_world.interfaces.mcp.server import create_mcp
from switch_world.interfaces.mcp.tools import TOOL_NAMES
from switch_world import config
from switch_world.application.facade import WorldService

DOCS = Path(__file__).resolve().parents[2] / "docs" / "MCP.md"
TOOL_PATTERN = re.compile(r"world__[a-z_]+")


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def _advertised(service) -> list[str]:
    return [tool.name for tool in create_mcp(service)._tool_manager.list_tools()]


def test_advertises_exactly_the_fourteen_tools(service):
    names = _advertised(service)
    assert len(names) == 14
    assert len(set(names)) == 14
    assert set(names) == set(TOOL_NAMES)


def test_docs_list_the_same_fourteen_tools(service):
    documented = set(TOOL_PATTERN.findall(DOCS.read_text(encoding="utf-8")))
    advertised = set(_advertised(service))
    assert len(documented) == 14
    assert documented == advertised


def test_every_tool_has_a_description_and_object_schema(service):
    for tool in create_mcp(service)._tool_manager.list_tools():
        assert tool.description and tool.description.strip(), tool.name
        schema = tool.parameters
        assert schema["type"] == "object", tool.name
        assert "properties" in schema, tool.name


def test_give_item_and_record_event_keep_their_schemas(service):
    tools = {
        tool.name: tool for tool in create_mcp(service)._tool_manager.list_tools()
    }

    give = tools["world__give_item"].parameters["properties"]
    assert {"item_id", "to", "note"} <= set(give)
    assert {"item_id", "to"} <= set(tools["world__give_item"].parameters["required"])

    record = tools["world__record_event"].parameters["properties"]
    assert {"kind", "summary", "participants", "visibility"} <= set(record)
    assert {"kind", "summary"} <= set(
        tools["world__record_event"].parameters["required"]
    )


def test_tool_names_are_in_stable_document_order():
    """Argument order and registration order are part of the public contract."""
    assert TOOL_NAMES[0] == "world__recall"
    assert TOOL_NAMES[-1] == "world__advance_time"
    assert len(set(TOOL_NAMES)) == 14
