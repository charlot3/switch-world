from __future__ import annotations

import time

import pytest

from director.group import say_in_group
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


class FakeSwitch:
    def __init__(self, replies=None, fail_post=False):
        self.replies = replies or {}
        self.fail_post = fail_post
        self.posted = None
        self.posts = []
        self.timestamp = int(time.time() * 1000) + 1

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        if self.fail_post:
            from director.switch_client import SwitchError

            raise SwitchError("gateway down")
        self.posted = content
        self.posts.append(content)
        return {}

    def history(self, room_id):
        return [
            {
                "event_id": f"evt-{name}",
                "sender_name": name,
                "timestamp": self.timestamp,
                "body": text,
            }
            for name, text in self.replies.items()
        ]


def test_group_say_records_both_sides(service):
    switch = FakeSwitch({"alice": "I'm here.", "emily": "Who else?"})
    result = say_in_group(service, "Are we still on for tonight?", switch=switch)
    assert len(switch.posts) == 4
    assert all("@alice" not in post for post in switch.posts[1:])
    assert "Are we still on for tonight?" in switch.posted
    assert "Your relationship with the user" in switch.posted
    assert [reply["character"] for reply in result["replies"]] == ["alice", "emily"]
    assert result["missing"] == ["sophia", "mia"]
    state = service.state()
    summaries = [event["summary"] for event in state["events"]]
    assert "You: Are we still on for tonight?" in summaries
    assert "Alice: I'm here." in summaries


def test_group_say_addresses_a_subset(service):
    switch = FakeSwitch({"mia": "Fries are on."})
    result = say_in_group(service, "Mia, save me a portion.", characters=["mia"], switch=switch)
    assert switch.posted.startswith("@mia ")
    assert result["targets"] == ["mia"]
    assert result["missing"] == []


def test_group_say_ignores_session_placeholders(service):
    switch = FakeSwitch(
        {
            "alice": "Starting a session to handle this — one moment.",
            "emily": "I'm here.",
        }
    )
    result = say_in_group(service, "Hello?", switch=switch, timeout=1.0)
    assert [reply["character"] for reply in result["replies"]] == ["emily"]
    assert "alice" in result["missing"]


def test_group_say_gates_an_intimate_question(service):
    switch = FakeSwitch({name: "Black." for name in ("alice", "emily", "sophia", "mia")})
    before = service.relationship("alice", "user")["tension"]
    result = say_in_group(service, "what color is your underwear?", switch=switch)
    assert all("black" not in reply["text"].lower() for reply in result["replies"])
    assert all(verdict["stance"] in {"refuse", "deflect"} for verdict in result["verdicts"].values())
    assert service.relationship("alice", "user")["tension"] > before
    assert any(event["kind"] == "social_verdict" for event in service.state()["events"])


def test_group_say_reports_a_dead_room(service):
    switch = FakeSwitch(fail_post=True)
    with pytest.raises(RuntimeError, match="gateway"):
        say_in_group(service, "Hello?", switch=switch)
    summaries = [event["summary"] for event in service.state()["events"]]
    assert "You: Hello?" in summaries


def test_turn_plan_builds_a_chorus_with_metadata(service):
    switch = FakeSwitch(
        {
            "alice": "I'm here.",
            "emily": "Same as always.",
            "sophia": "We are.",
            "mia": "Obviously.",
        }
    )
    result = say_in_group(service, "Are we still on for tonight?", switch=switch)
    turn = result["turn"]
    assert turn["id"].startswith("t-")
    assert turn["plan"]["chorus"] is True
    assert 2 <= len(turn["plan"]["chorus_speakers"]) <= 3
    assert turn["plan"]["silent"]  # at least one present character is silent
    assert turn["lines"]
    assert all(line["mode"] == "chorus" for line in turn["lines"])
    assert all(line["role"] == "chorus" for line in turn["lines"])

    events = service.state()["events"]
    plans = [event for event in events if event["kind"] == "turn_plan"]
    assert plans[-1]["metadata"]["turn_id"] == turn["id"]
    assert plans[-1]["metadata"]["plan"]["chorus"] is True
    beats = [
        event for event in events
        if event["kind"] == "dialogue"
        and event["metadata"].get("turn_id") == turn["id"]
        and event["metadata"].get("role") == "chorus"
    ]
    assert beats
    assert all(event["metadata"]["mode"] == "chorus" for event in beats)


def test_named_addressee_is_the_primary(service):
    switch = FakeSwitch({"emily": "Fine, mostly."})
    result = say_in_group(
        service, "Emily, how was your day?", switch=switch, timeout=1
    )
    plan = result["turn"]["plan"]
    assert plan["primary"] == "emily"
    assert plan["chorus"] is False
    assert result["replies"][0]["character"] == "emily"
    beat = next(
        event for event in service.state()["events"]
        if event["metadata"].get("turn_id") == result["turn"]["id"]
        and event["kind"] == "dialogue"
        and "emily" in event["participants"]
    )
    assert beat["metadata"]["role"] == "primary"


def test_intimate_topic_never_becomes_a_chorus(service):
    switch = FakeSwitch({"alice": "Not answering.", "emily": "No."})
    result = say_in_group(
        service, "what color is your underwear?", switch=switch, timeout=1
    )
    plan = result["turn"]["plan"]
    assert plan["chorus"] is False
    assert plan["primary"] == "alice"
    assert len(plan["reactors"]) == 1
    assert plan["silent"]


def test_action_reply_becomes_an_action_beat(service):
    switch = FakeSwitch({"alice": "*She slides the menu across the table.*"})
    result = say_in_group(
        service,
        "@alice what's good here?",
        characters=["alice"],
        switch=switch,
        timeout=1,
    )
    line = result["turn"]["lines"][0]
    assert line["mode"] == "action"
    assert "asterisks" not in line["text"]
    event = next(
        item for item in service.state()["events"] if item["kind"] == "action"
    )
    assert event["metadata"]["turn_id"] == result["turn"]["id"]
    assert event["metadata"]["mode"] == "action"


def test_missing_planned_speaker_becomes_a_silence_beat(service):
    switch = FakeSwitch({"alice": "I'm here."})
    result = say_in_group(
        service,
        "Are we still on?",
        characters=["alice", "emily"],
        switch=switch,
        timeout=1,
    )
    turn = result["turn"]
    assert turn["missing"] == ["emily"]
    silence = [line for line in turn["lines"] if line["mode"] == "silence"]
    assert silence and silence[0]["character"] == "emily"
    events = [
        event for event in service.state()["events"] if event["kind"] == "silence"
    ]
    assert events and events[-1]["metadata"]["turn_id"] == turn["id"]


def test_turn_wait_is_capped_at_35_seconds(service, monkeypatch):
    class FakeTime:
        def __init__(self):
            self.now = 1000.0

        def time(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    fake = FakeTime()
    monkeypatch.setattr("director.group.time", fake)
    result = say_in_group(
        service, "Hi.", characters=["alice"], switch=FakeSwitch({}), timeout=999
    )
    assert result["timed_out"] is True
    assert fake.now == pytest.approx(1035.0)


def test_boundary_violation_cuts_the_act_and_marks_the_target_absent(service):
    before = service.relationship("alice", "user")
    switch = FakeSwitch({})
    result = say_in_group(service, "kiss me", switch=switch, timeout=1)
    turn = result["turn"]
    assert turn["plan"]["boundary"] == "violation"
    assert turn["plan"]["primary"] == "alice"
    assert result["verdicts"]["alice"]["stance"] == "hard_refuse"

    events = service.state()["events"]
    summaries = [event["summary"] for event in events]
    assert not any("kiss" in summary.lower() for summary in summaries)
    assert switch.posts == []  # the act text never reaches a model

    boundary = [event for event in events if event["kind"] == "boundary_violation"]
    assert len(boundary) == 1
    assert boundary[0]["summary"] == "The user crossed a physical boundary with Alice."
    assert boundary[0]["visibility"] == "public"

    assert service.is_absent("alice")
    assert service.absent_characters() == ["alice"]

    holders = service.who_knows("user-crossed-a-line")["holders"]
    assert {h["holder"]: h["confidence"] for h in holders} == {
        "emily": 0.9,
        "sophia": 0.85,
        "mia": 0.8,
    }
    assert all(h["source"] == "observation" for h in holders)
    assert all(h["visibility"] == "private" for h in holders)

    refusal = next(line for line in turn["lines"] if line["character"] == "alice")
    assert refusal["mode"] == "speech"
    assert any(line["mode"] == "reaction" for line in turn["lines"])
    after = service.relationship("alice", "user")
    assert after["tension"] > before["tension"]

    # Later group sends filter the absent character out entirely.
    switch2 = FakeSwitch({"emily": "Hi."})
    second = say_in_group(service, "Hello everyone.", switch=switch2, timeout=1)
    assert "alice" not in second["targets"]
    assert all("@alice" not in post for post in switch2.posts)


def test_group_say_does_not_record_the_same_switch_event_twice(service):
    class ReplayingSwitch(FakeSwitch):
        def history(self, room_id):
            self.timestamp += 1
            return super().history(room_id)

    switch = ReplayingSwitch({"alice": "Still here."})
    first = say_in_group(service, "First line.", characters=["alice"], switch=switch, timeout=1)
    second = say_in_group(service, "Second line.", characters=["alice"], switch=switch, timeout=1)
    assert first["replies"]
    assert second["replies"] == []
    summaries = [event["summary"] for event in service.state()["events"] if event["kind"] == "dialogue"]
    assert summaries.count("Alice: Still here.") == 1
