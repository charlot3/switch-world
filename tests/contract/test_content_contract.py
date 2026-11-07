"""Contract for the authored-content store.

A missing file is a typed error, a read is cached until the file's mtime (or
size) changes, and each file is parsed once per container.
"""
from __future__ import annotations

import json
import os

import pytest

from switch_world.adapters.content import FileContentStore
from switch_world.domain.ports.content import ContentNotFound


def _write(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )


def test_missing_file_raises_content_not_found(tmp_path):
    store = FileContentStore(tmp_path)

    with pytest.raises(ContentNotFound) as caught:
        store.canon()

    assert isinstance(caught.value, FileNotFoundError)


def test_mtime_cache_parses_once(tmp_path):
    _write(tmp_path / "canon.json", {"title": "A Tuesday"})
    store = FileContentStore(tmp_path)

    first = store.canon()
    second = store.canon()

    assert first == second == {"title": "A Tuesday"}
    assert store.parse_count == 1
    assert store.parses[tmp_path / "canon.json"] == 1


def test_mtime_change_invalidates_the_cache(tmp_path):
    path = tmp_path / "canon.json"
    _write(path, {"title": "old"})
    store = FileContentStore(tmp_path)
    assert store.canon() == {"title": "old"}
    assert store.parse_count == 1

    _write(path, {"title": "a new title that is longer"})
    future = 2_000_000_000_000_000_000
    os.utime(path, ns=(future, future))

    assert store.canon() == {"title": "a new title that is longer"}
    assert store.parse_count == 2


def test_every_content_method_parses_each_file_once(tmp_path):
    _write(tmp_path / "canon.json", {"title": "canon"})
    _write(tmp_path / "social.json", {"tiers": []})
    _write(tmp_path / "scenarios" / "w1.json", {"id": "w1"})
    _write(tmp_path / "takes" / "w1.json", {"id": "w1"})
    _write(tmp_path / "takes" / "w2.json", {"id": "w2"})
    _write(tmp_path / "characters" / "alice.md", "Alice's identity")
    _write(tmp_path / "characters" / "README.md", "not a character")
    store = FileContentStore(tmp_path)

    assert store.canon() == {"title": "canon"}
    assert store.social() == {"tiers": []}
    assert store.scenario("w1") == {"id": "w1"}
    assert [take["id"] for take in store.takes()] == ["w1", "w2"]
    assert store.characters() == {"alice": "Alice's identity"}

    parsed_once = store.parse_count
    assert parsed_once == 6

    assert store.canon() == {"title": "canon"}
    assert store.social() == {"tiers": []}
    assert store.scenario("w1") == {"id": "w1"}
    assert store.takes() == [{"id": "w1"}, {"id": "w2"}]
    assert store.characters() == {"alice": "Alice's identity"}
    assert store.parse_count == parsed_once
    assert all(count == 1 for count in store.parses.values())


def test_missing_scenario_raises_content_not_found(tmp_path):
    _write(tmp_path / "canon.json", {"title": "canon"})
    store = FileContentStore(tmp_path)

    with pytest.raises(ContentNotFound):
        store.scenario("does-not-exist")


def test_repository_root_layout_is_also_supported(tmp_path):
    _write(tmp_path / "world" / "canon.json", {"title": "nested"})
    store = FileContentStore(tmp_path)

    assert store.canon() == {"title": "nested"}
