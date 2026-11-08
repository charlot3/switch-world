"""An in-band cloud group reply writes beliefs and relationships.

The cloud room returns the same JSON envelope a DM uses. Step 4 turns that
envelope into an ``AgentReply`` and the turn recorder applies its writes with
the speaking character as the actor. Before this step a cloud group turn only
produced dialogue: memory and relationship deltas were silently dropped.
"""
from __future__ import annotations

from switch_world.adapters.models import ScriptedModelClient
from switch_world.adapters.transports import CloudRoomTransport
from switch_world.application.scene import say_in_group
from switch_world import config
from switch_world.application.facade import WorldService


def _service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def _beliefs(service, character):
    return service.recall(character)["memories"]


def test_cloud_group_turn_applies_the_envelope_writes(tmp_path):
    service = _service(tmp_path)
    model = ScriptedModelClient(
        {
            "alice": [
                {
                    "reply": "The lease renewal came back with a different number.",
                    "memory": {
                        "proposition": "The user asked Alice about the bookshop lease",
                        "source": "user",
                        "confidence": 0.7,
                        "visibility": "private",
                        "proposition_key": "user-asked-about-lease",
                    },
                    "relationships": [
                        {
                            "other": "user",
                            "trust_delta": 0.1,
                            "closeness_delta": 0.05,
                            "reason": "asked about the shop",
                        }
                    ],
                }
            ]
        }
    )
    transport = CloudRoomTransport(model)

    before_beliefs = len(_beliefs(service, "alice"))
    before_edge = service.relationship("alice", "user")

    result = say_in_group(
        service,
        "Alice, are we still on for tonight?",
        characters=["alice"],
        transport=transport,
        timeout=1.0,
    )

    assert result["replies"][0]["text"].startswith("The lease renewal")
    after_beliefs = _beliefs(service, "alice")
    assert len(after_beliefs) == before_beliefs + 1
    assert any(item["key"] == "user-asked-about-lease" for item in after_beliefs)

    after_edge = service.relationship("alice", "user")
    assert after_edge["trust"] > before_edge["trust"]
    # The relationship move is the character's own outgoing edge.
    assert after_edge["a"] == "alice"
    assert after_edge["b"] == "user"


def test_cloud_writes_use_the_speaking_character_as_actor(tmp_path):
    service = _service(tmp_path)
    model = ScriptedModelClient(
        {
            "mia": [
                {
                    "reply": "Truck's still in the red.",
                    "memory": {
                        "proposition": "Mia admitted the truck is in debt",
                        "source": "observation",
                        "confidence": 0.6,
                        "visibility": "private",
                    },
                    "relationships": [],
                }
            ]
        }
    )
    transport = CloudRoomTransport(model)

    say_in_group(
        service,
        "Mia, how are the books?",
        characters=["mia"],
        transport=transport,
        timeout=1.0,
    )

    memories = _beliefs(service, "mia")
    assert any(item["mine"] for item in memories)
    # The new belief is Mia's private memory, not a public fact every actor sees.
    assert not any(
        item["proposition"] == "Mia admitted the truck is in debt"
        for item in _beliefs(service, "alice")
    )
