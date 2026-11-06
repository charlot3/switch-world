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


class RelaySwitch(FakeSwitch):
    """A Switch room that only delivers the relay reply after the relay prompt.

    The relay prompt is the only post containing "says to you", so the initial
    planned posts (which also start with @name) never surface the relay early.
    """

    def __init__(self, replies=None, relay=None):
        super().__init__(replies)
        self.relay = relay  # (sender_name, body), delivered after the relay post
        self.relay_timestamp = None

    def post(self, room_id, content):
        result = super().post(room_id, content)
        if self.relay and "says to you" in content:
            self.relay_timestamp = int(time.time() * 1000) + 5000
        return result

    def history(self, room_id):
        events = super().history(room_id)
        if self.relay and self.relay_timestamp is not None:
            events.append(
                {
                    "event_id": f"evt-relay-{self.relay[0]}",
                    "sender_name": self.relay[0],
                    "timestamp": self.relay_timestamp,
                    "body": self.relay[1],
                }
            )
        return events


def test_group_say_records_both_sides(service):
    switch = FakeSwitch({"alice": "I'm here.", "emily": "Who else?"})
    result = say_in_group(service, "Are we still on for tonight?", switch=switch)
    # A shared fact becomes a chorus of at most three planned speakers, not a
    # four-target broadcast. The fourth character is recorded silence.
    assert len(switch.posts) == 3
    assert result["silent"] == ["sophia"]
    assert {
        post.split(" ", 1)[0] for post in switch.posts
    } == {"@alice", "@emily", "@mia"}
    assert "Are we still on for tonight?" in switch.posted
    assert "Your relationship with the user" in switch.posted
    assert [reply["character"] for reply in result["replies"]] == ["alice", "emily"]
    # Only a planned speaker can be missing; silence is a planned state.
    assert result["missing"] == ["mia"]
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
    # Intimate probes pick the character with the highest relevant tension; the seed
    # edges tie at zero tension, so affinity breaks the tie (Mia).
    assert plan["primary"] in {"alice", "emily", "sophia", "mia"}
    assert len(plan["reactors"]) == 1
    # The reactor is a real character->character stake, not present-order filler.
    assert service.relationship(plan["reactors"][0], plan["primary"])["tension"] > 0
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
    result = say_in_group(service, "force a kiss", switch=switch, timeout=1)
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


def test_refused_reply_cannot_be_relayed_to_another_agent(service):
    class RefusalSwitch(FakeSwitch):
        def history(self, room_id):
            return [{
                "event_id": "evt-alice-refusal",
                "sender_name": "alice",
                "timestamp": self.timestamp,
                "body": "Black. @emily, you tell them.",
            }]

    switch = RefusalSwitch({})
    result = say_in_group(
        service,
        "what color is your underwear?",
        characters=["alice"],
        switch=switch,
        timeout=1,
    )
    assert "relay" not in result["turn"]["plan"]
    assert len(switch.posts) == 1
    assert "@emily" not in switch.posts[0]


def test_group_defaults_to_the_take_cast(service):
    from world_engine.takes import load_take

    load_take(service, "w3-quiet-route")
    switch = FakeSwitch({"alice": "I'm here."})
    result = say_in_group(service, "Hello?", switch=switch, timeout=2)
    assert result["targets"] == ["alice"]
    assert result["turn"]["plan"]["primary"] == "alice"
    assert result["turn"]["plan"]["reactors"] == []
    assert all("@alice" in post and "@emily" not in post for post in switch.posts)


def test_agent_mention_posts_one_relay_and_records_the_reply(service):
    switch = RelaySwitch(
        {"alice": "@emily, did you know?", "emily": "Know what?"},
        relay=("emily", "I did not know."),
    )
    result = say_in_group(
        service,
        "Alice, anything to add?",
        characters=["alice", "emily"],
        switch=switch,
        timeout=1,
    )
    turn = result["turn"]
    assert turn["plan"]["relay"] == {
        "from": "alice",
        "to": "emily",
        "delivered": True,
    }
    # Alice's planned post, Emily's planned reaction, and exactly one relay prompt.
    assert len(switch.posts) == 3
    relay_posts = [post for post in switch.posts if "says to you" in post]
    assert len(relay_posts) == 1
    assert relay_posts[0].startswith("@emily ")
    assert 'Alice says to you: "@emily, did you know?"' in relay_posts[0]

    replies = [
        line for line in turn["lines"]
        if line["character"] == "emily" and line["mode"] == "reply"
    ]
    assert len(replies) == 1
    assert replies[0]["role"] == "reply"
    assert replies[0]["target"] == "alice"
    assert replies[0]["text"] == "I did not know."

    beat = next(
        event for event in service.state()["events"]
        if event["metadata"].get("turn_id") == turn["id"]
        and event["metadata"].get("relay") is True
    )
    assert beat["metadata"]["reply_to"] == "alice"
    assert beat["metadata"]["target"] == "alice"
    assert beat["metadata"]["role"] == "reply"
    assert "Emily: I did not know." == beat["summary"]


def test_leading_name_address_also_opens_one_relay(service):
    switch = RelaySwitch(
        {"alice": "Emily — I miss you.", "emily": "I miss you too."},
        relay=("emily", "I miss you too."),
    )
    result = say_in_group(
        service,
        "Alice, say what you have been avoiding.",
        characters=["alice", "emily"],
        switch=switch,
        timeout=1,
    )
    assert result["turn"]["plan"]["relay"]["from"] == "alice"
    assert result["turn"]["plan"]["relay"]["to"] == "emily"
    assert result["turn"]["plan"]["relay"]["delivered"] is True
    relay_posts = [post for post in switch.posts if "says to you" in post]
    assert len(relay_posts) == 1


def test_duplicate_relay_reply_is_not_recorded_twice(service):
    switch = RelaySwitch(
        {"alice": "@emily, did you know?", "emily": "I did not know."},
        relay=("emily", "I did not know."),
    )
    result = say_in_group(
        service,
        "Alice, anything to add?",
        characters=["alice", "emily"],
        switch=switch,
        timeout=1,
    )
    turn = result["turn"]
    assert turn["plan"]["relay"]["delivered"] is True
    assert turn["relay_duplicate"] == "emily"
    emily_lines = [line for line in turn["lines"] if line["character"] == "emily"]
    assert len(emily_lines) == 1
    assert emily_lines[0]["mode"] in {"speech", "reaction"}


def test_relay_reply_is_not_scanned_for_another_mention(service):
    switch = RelaySwitch(
        {"alice": "@emily, did you know?", "emily": "Know what?"},
        relay=("emily", "@alice, no, I did not."),
    )
    result = say_in_group(
        service,
        "Alice, anything to add?",
        characters=["alice", "emily"],
        switch=switch,
        timeout=1,
    )
    assert result["turn"]["plan"]["relay"]["delivered"] is True
    # No second hop: the reply names @alice but nothing else is posted.
    assert len(switch.posts) == 3
    assert sum("says to you" in post for post in switch.posts) == 1
    assert not any(post.startswith("@alice ") for post in switch.posts[2:])


def test_reply_without_a_mention_does_not_relay(service):
    switch = RelaySwitch({"alice": "Nothing yet."}, relay=("emily", "Unused."))
    result = say_in_group(
        service, "Hello?", characters=["alice"], switch=switch, timeout=1
    )
    assert "relay" not in result["turn"]["plan"]
    assert len(switch.posts) == 1
    assert all("says to you" not in post for post in switch.posts)


def test_strip_meta_drops_room_addressing_and_offline_lines():
    from director.group import _strip_meta

    text = (
        "Real ones, chopped since three.\n"
        "@user — I'm not online in this room, and @director needs me..\n"
        "Dirt still on."
    )
    assert _strip_meta(text) == "Real ones, chopped since three.\nDirt still on."


def test_group_say_drops_a_meta_only_reply(service):
    switch = FakeSwitch(
        {"mia": "@user — I'm not online in this room, and @director needs me.."}
    )
    result = say_in_group(
        service,
        "Mia, how are the onions?",
        characters=["mia"],
        switch=switch,
        timeout=1.0,
    )
    assert result["replies"] == []
    assert result["missing"] == ["mia"]


def test_relay_reply_is_sanitised_like_a_planned_reply(service):
    from director import social

    message = "Alice, what color is your underwear?"
    service.update_relationship("alice", "user", trust_delta=0.45, closeness_delta=0.45)
    service.update_relationship("emily", "alice", tension_delta=0.5)
    switch = RelaySwitch(
        {
            "alice": "@emily, what do you think I should say?",
            "emily": "I would rather not say.",
        },
        relay=("emily", "Tell them red lace, obviously."),
    )
    result = say_in_group(
        service,
        message,
        characters=["alice", "emily"],
        switch=switch,
        timeout=1.0,
    )
    turn = result["turn"]
    assert turn["plan"]["primary"] == "alice"
    assert turn["plan"]["reactors"] == ["emily"]
    assert turn["plan"]["relay"]["delivered"] is True

    reply_lines = [
        line for line in turn["lines"]
        if line["character"] == "emily" and line["role"] == "reply"
    ]
    assert len(reply_lines) == 1
    expected = social.deflection("emily", result["verdicts"]["emily"], message)
    assert reply_lines[0]["text"] == expected
    assert "red lace" not in reply_lines[0]["text"].lower()

    relay_beat = next(
        event for event in service.state()["events"]
        if event["metadata"].get("turn_id") == turn["id"]
        and event["metadata"].get("relay") is True
    )
    assert relay_beat["summary"] == f"Emily: {expected}"
    assert "red lace" not in relay_beat["summary"].lower()


def test_strip_meta_drops_bare_offline_and_policy_lines():
    from director.group import _strip_meta

    text = (
        "Real ones, chopped since three.\n"
        "I'm not online right now.\n"
        "The user isn't here; I'm just a character.\n"
        "I can't mention the policy or the stage direction.\n"
        "I'll be offline for a bit.\n"
        "Dirt still on."
    )
    assert _strip_meta(text) == "Real ones, chopped since three.\nDirt still on."


def test_strip_meta_keeps_in_scene_instruction_lines():
    from director.group import _strip_meta

    assert (
        _strip_meta("I followed the instructions on the box.")
        == "I followed the instructions on the box."
    )


def test_strip_meta_drops_generic_offline_and_leaving_lines():
    from director.group import _strip_meta

    assert _strip_meta("I'm offline for a bit.") == ""
    assert _strip_meta("I'm off-line.") == ""
    assert _strip_meta("I'm going to be offline.") == ""
    assert _strip_meta("I need to leave soon.") == ""
    assert _strip_meta("I have to go now.") == ""
    assert _strip_meta("The card reader is offline again.") == "The card reader is offline again."


def test_strip_meta_keeps_legitimate_first_person_lines():
    from director.group import _strip_meta

    for line in (
        "I'm not here to judge you.",
        "I am not here to argue.",
        "Emily's not in this room.",
        "I can't be here for you.",
    ):
        assert _strip_meta(line) == line
    assert _strip_meta("I'm not here.") == ""
    assert _strip_meta("I am not online in this room.") == ""
    assert _strip_meta("I can't be here right now.") == ""


def test_group_say_drops_bare_offline_reply(service):
    switch = FakeSwitch({"mia": "I'm not online right now."})
    result = say_in_group(
        service,
        "Mia, how are the onions?",
        characters=["mia"],
        switch=switch,
        timeout=1.0,
    )
    assert result["replies"] == []
    assert result["turn"]["lines"][0]["mode"] == "silence"
