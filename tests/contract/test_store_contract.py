"""Contract for the persistence store that the service facade delegates to.

These tests pin the three faces (reader/writer/admin), the single-connection
snapshot, transaction atomicity and parity with the compatibility facade.
"""
from __future__ import annotations

import pytest

from switch_world.adapters.persistence import WorldStore
from switch_world.domain import IdempotencyConflict
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def store(tmp_path):
    return WorldStore(
        db_path=tmp_path / "world.sqlite",
        state_dir=config.STATE_DIR,
        world_start=config.WORLD_START,
        world_day=config.WORLD_DAY,
    )


@pytest.fixture()
def service(tmp_path):
    return WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )


def test_store_exposes_reader_writer_and_admin(store):
    assert store.reader is store.reader
    assert store.writer is store.writer
    assert store.admin is store.admin
    # The faces are narrow: a reader cannot write and a writer cannot reset.
    with pytest.raises(AttributeError):
        store.reader.record_event
    with pytest.raises(AttributeError):
        store.writer.snapshot
    with pytest.raises(AttributeError):
        store.admin.remember


def test_snapshot_is_one_coherent_projection(store):
    snapshot = store.reader.snapshot()
    assert len(snapshot["characters"]) == 4
    assert len(snapshot["beliefs"]) == 16
    assert len(snapshot["relationships"]) == 16
    assert snapshot["clock"]["mode"] == "mock"
    assert snapshot["revision"] >= 1
    assert snapshot["turn"] == 0
    assert snapshot["scenario"] is None
    assert snapshot["take_meta"] is None
    assert len(snapshot["connections"]) == 6
    assert isinstance(snapshot["events"], list)
    assert snapshot["matrix"]
    assert all(isinstance(row["key"], str) for row in snapshot["matrix"])


def test_snapshot_matches_the_service_projection(store, service):
    expected = service.state_from_snapshot(service.store.reader.snapshot())
    assert service.state() == expected
    assert service.clock() == store.reader.clock()
    assert service.matrix() == store.reader.matrix()
    assert service.outfits() == store.reader.outfits()


def test_writer_changes_are_visible_to_the_reader(store):
    belief = store.writer.remember(
        "alice", "I am leaving.", source="user", confidence=1.0,
        proposition_key="user-leaving-city",
    )
    assert belief["holder"] == "alice"
    assert store.reader.who_knows("user-leaving-city")["holders"][0]["holder"] == "alice"

    store.writer.add_friend("alice")
    assert store.reader.is_friend("alice") is True
    assert [row["character"] for row in store.reader.friends()] == ["alice"]


def test_transaction_is_atomic(store):
    with pytest.raises(RuntimeError):
        with store.transaction() as conn:
            store.writer.record_event(
                "director", "note", "should roll back", ["alice"],
                visibility="public", conn=conn,
            )
            raise RuntimeError("abort")

    assert store.reader.events("note") == []


def test_transaction_commits_when_the_block_succeeds(store):
    with store.transaction() as conn:
        store.writer.record_event(
            "director", "note", "should commit", ["alice"],
            visibility="public", conn=conn,
        )
    assert [event["summary"] for event in store.reader.events("note")] == ["should commit"]


def test_idempotency_is_a_writer_then_reader_round_trip(store):
    store.writer.store_idempotent("scope", "request-1", "digest-a", {"ok": True})
    assert store.reader.idempotent_replay("scope", "request-1", "digest-a") == {
        "ok": True, "replayed": True,
    }
    with pytest.raises(IdempotencyConflict):
        store.reader.idempotent_replay("scope", "request-1", "digest-b")


def test_admin_reset_restores_the_base_seed(store):
    store.writer.remember("alice", "I am leaving.", "user", proposition_key="user-leaving-city")
    store.writer.add_friend("alice")
    store.admin.reset()

    assert store.reader.who_knows("user-leaving-city")["holders"] == []
    assert store.reader.friends() == []
    assert len(store.reader.characters()) == 4


def test_apply_scenario_is_a_transactional_admin_call(store):
    from world_engine.scenarios import get_scenario

    scenario = get_scenario("w1-gift")
    with store.transaction() as conn:
        store.admin.apply_scenario(
            conn,
            scenario,
            now_iso="2026-11-03T18:20:00+09:00",
            mode="mock",
            scale=1.0,
            anchor=None,
            cast=list(scenario["cast"]),
        )

    snapshot = store.reader.snapshot()
    assert snapshot["scenario"]["id"] == "w1-gift"
    assert snapshot["clock"]["now"] == "2026-11-03T18:20:00+09:00"
    assert [item["id"] for item in snapshot["items"]] == ["gift-book"]
    assert any(event["kind"] == "scenario_load" for event in snapshot["events"])


def test_db_shim_still_works(tmp_path):
    """``world_engine.db`` keeps its historical names over the new schema."""
    from world_engine import db

    path = tmp_path / "shim.sqlite"
    db.init_db(path, config.STATE_DIR)
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM characters").fetchone()["n"] == 4
    finally:
        conn.close()
    db.reset(path, config.STATE_DIR)
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM characters").fetchone()["n"] == 4
    finally:
        conn.close()
    assert "CREATE TABLE IF NOT EXISTS events" in db.SCHEMA


def test_deprecated_private_connection_still_works_for_legacy_callers(service):
    with service._conn() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM characters").fetchone()["n"] == 4
