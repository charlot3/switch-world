import test from "node:test";
import assert from "node:assert/strict";

import {
  ACTION_MODES,
  CAST_ORDER,
  CUE_OPS,
  EVENT_KINDS,
  ORDER,
  RESPONSE_MODES,
  SCENE_EVENT_KINDS,
  SPEECH_MODES,
  TAKE_BOUNDARY_EVENT_KINDS,
  TAKE_CHANGE_EVENT_KINDS,
  TAKE_ORDER,
} from "./vocab.js";

test("cast order is the four cast members once, in presentation order", () => {
  assert.deepEqual(CAST_ORDER, ["alice", "emily", "sophia", "mia"]);
  assert.equal(ORDER, CAST_ORDER);
  assert.equal(new Set(CAST_ORDER).size, CAST_ORDER.length);
});

test("scene vocabulary keeps the transcript kinds and speech modes", () => {
  for (const kind of [
    "dialogue", "silence", "reaction", "action", "chorus",
    "whisper", "whisper_reply", "boundary_violation",
  ]) {
    assert.ok(SCENE_EVENT_KINDS.has(kind), kind);
  }
  assert.ok(!SCENE_EVENT_KINDS.has("turn_plan"));
  assert.ok(SPEECH_MODES.has("speech"));
  assert.ok(SPEECH_MODES.has("whisper_reply"));
  assert.ok(!SPEECH_MODES.has("action"));
});

test("take boundaries and change kinds match the take protocol", () => {
  assert.deepEqual([...TAKE_BOUNDARY_EVENT_KINDS], ["take_load", "take_scene"]);
  for (const kind of ["dialogue", "turn_plan", "take_cue", "ending", "beat"]) {
    assert.ok(TAKE_CHANGE_EVENT_KINDS.has(kind), kind);
  }
  assert.ok(!TAKE_CHANGE_EVENT_KINDS.has("take_load"));
});

test("action and response modes are the vocabulary the UI may surface", () => {
  assert.deepEqual([...ACTION_MODES], ["result", "attempt", "continue", "wait"]);
  assert.deepEqual(
    [...RESPONSE_MODES],
    ["refuse", "negotiate", "limited", "surface", "sincere"],
  );
});

test("event, take and cue vocabularies are ordered and duplicate-free", () => {
  assert.equal(new Set(EVENT_KINDS).size, EVENT_KINDS.length);
  assert.ok(EVENT_KINDS.includes("dm"));
  assert.deepEqual(TAKE_ORDER[0], "w1-gift");
  assert.deepEqual(TAKE_ORDER.at(-1), "w7-last-call");
  assert.ok(CUE_OPS.includes("give_item"));
});
