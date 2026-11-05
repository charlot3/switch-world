from __future__ import annotations

from director.tavily_beat import fetch_world_event, latest_world_event
from world_engine import config
from world_engine.service import WorldService


class FakeTavily:
    def __init__(self, offline: bool = False):
        self.offline = offline
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {
            "query": query,
            "answer": "A current answer",
            "offline": self.offline,
            "results": [
                {
                    "title": "A real-world topic",
                    "url": "https://example.com/topic",
                    "content": "A current snippet about the topic.",
                    "published_date": "2026-11-05",
                    "score": 0.9,
                }
            ],
        }


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_world_event_becomes_shared_memory(tmp_path):
    service = make_service(tmp_path)
    client = FakeTavily()
    result = fetch_world_event(service, query="agents this week", client=client)

    assert client.calls[0][0] == "agents this week"
    assert result["event"]["kind"] == "world_event"
    assert "A real-world topic" in result["event"]["summary"]
    assert result["key"].startswith("world-")
    assert set(result["holders"]) == {"alice", "emily", "sophia", "mia"}

    holders = service.who_knows(result["key"])["holders"]
    assert {holder["holder"] for holder in holders} == {"alice", "emily", "sophia", "mia"}
    assert all(holder["source"] == f"event:{result['event']['id']}" for holder in holders)
    assert all(holder["visibility"] == "shared" for holder in holders)

    assert latest_world_event(service)["id"] == result["event"]["id"]


def test_offline_event_is_marked(tmp_path):
    service = make_service(tmp_path)
    result = fetch_world_event(service, query="q", client=FakeTavily(offline=True))
    assert result["offline"] is True
    assert "[offline fixture]" in result["event"]["summary"]
