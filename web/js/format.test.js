import test from "node:test";
import assert from "node:assert/strict";

import {
  affinityFor,
  affinityHearts,
  asCastId,
  castIdForName,
  clockScaleLabel,
  connectionLabelFor,
  edgeClass,
  eventIdNumber,
  eventMeta,
  firstName,
  firstNameOf,
  formatClock,
  formatTime,
  heartGlyph,
  heartStrip,
  itemHolderLabel,
  lastEventKey,
  mergeTakeConfig,
  nameList,
  normalizeActionMode,
  normalizeConnection,
  normalizeResponse,
  normalizeText,
  parseSummary,
  scaleFactor,
  seqStep,
  sourceLabel,
  speakerFromText,
  stateRevision,
  stateTurnNumber,
  stripSpeakerPrefix,
  takeIndexForScene,
  takeSceneAt,
  takeSceneChangedFromEvents,
  takeSceneCount,
  takeSceneIsObject,
} from "./format.js";

globalThis.SWITCH_CAST = {
  alice: { id: "alice", name: "Alice Moreau", mood: "warm" },
  emily: { id: "emily", name: "Emily Park", mood: "sharp" },
  sophia: { id: "sophia", name: "Sophia Adeyemi", mood: "still" },
  mia: { id: "mia", name: "Mia Rossi", mood: "bright" },
};

test("clock formatting uses the story timezone", () => {
  assert.equal(formatTime("2026-11-08T09:30:00Z"), "18:30");
  assert.match(formatClock("2026-11-08T09:30:00Z"), /18:30/);
  assert.match(formatClock("2026-11-08T09:30:00Z"), /Nov/);
});

test("first names and cast ids handle the summary prefixes", () => {
  assert.equal(firstName("Alice Moreau"), "Alice");
  assert.equal(firstName(""), "");
  assert.equal(castIdForName("Alice Moreau"), "alice");
  assert.equal(castIdForName("emily"), "emily");
  assert.equal(castIdForName("nobody"), null);
  assert.equal(firstNameOf("emily"), "Emily");
  assert.equal(nameList(["alice", "emily", "mia"]), "Alice, Emily and Mia");
  assert.equal(nameList(["sophia"]), "Sophia");
  assert.equal(asCastId("user"), "user");
  assert.equal(asCastId("Alice (whisper)"), "alice");
  assert.equal(asCastId("Mia: hello"), "mia");
  assert.equal(asCastId("nobody"), null);
  assert.equal(speakerFromText("Alice: hello"), "alice");
  assert.equal(speakerFromText("emily hello"), "emily");
  assert.equal(speakerFromText("nobody"), null);
  assert.equal(stripSpeakerPrefix("Alice hello there", "alice"), "hello there");
  assert.equal(stripSpeakerPrefix("Alice: hello", "alice"), "Alice: hello");
});

test("text and event normalisation is lossless where it should be", () => {
  assert.equal(normalizeText("  Hello\n  WORLD  "), "hello world");
  assert.equal(normalizeActionMode(" Attempt "), "attempt");
  assert.equal(normalizeActionMode("unknown"), "");
  assert.equal(normalizeResponse(" Refuse "), "refuse");
  assert.equal(normalizeResponse("no"), "");
  assert.deepEqual(parseSummary("Alice: hi there"), { who: "Alice", text: "hi there" });
  assert.deepEqual(parseSummary("no colon"), { who: "", text: "no colon" });
  assert.deepEqual(eventMeta({ metadata: { a: 1 } }), { a: 1 });
  assert.deepEqual(eventMeta({ metadata_json: '{"b":2}' }), { b: 2 });
  assert.deepEqual(eventMeta({ metadata: "not json" }), {});
  assert.deepEqual(eventMeta(null), {});
  assert.equal(eventIdNumber({ id: "7" }), 7);
  assert.equal(eventIdNumber({ id: "x" }), null);
});

test("take helpers normalise scenes and config merging", () => {
  const scenes = [
    { id: "one", title: "One" },
    { id: "two", title: "Two" },
  ];
  const take = { id: "w1", title: "Route", scenes };
  assert.equal(takeSceneIsObject(scenes[0]), true);
  assert.equal(takeSceneIsObject({ id: "one" }), false);
  assert.equal(takeSceneCount(take), 2);
  assert.equal(takeSceneCount({ scene_count: "3" }), 3);
  assert.equal(takeSceneCount(null), 0);
  assert.equal(takeSceneAt(take, 1).id, "two");
  assert.equal(takeSceneAt(take, 5), null);
  assert.equal(takeIndexForScene(take, { id: "two" }), 1);
  assert.equal(takeIndexForScene(take, { id: "none" }), null);
  assert.deepEqual(
    mergeTakeConfig({ id: "w1", title: "New" }, take).scenes,
    scenes,
  );
  assert.equal(mergeTakeConfig(null, take), take);
});

test("state baselines read revision, turn and event keys", () => {
  assert.equal(stateRevision({ revision: 4 }), 4);
  assert.equal(stateRevision({}), null);
  assert.equal(stateTurnNumber({ turn: 3 }), 3);
  assert.equal(stateTurnNumber({ turn: { number: 4 } }), 4);
  assert.equal(stateTurnNumber({ turn: { index: 5 } }), 5);
  assert.equal(stateTurnNumber({ take_turn: "6" }), 6);
  assert.equal(stateTurnNumber({}), null);
  assert.equal(lastEventKey({ events: [{ id: 7 }] }), "7");
  assert.equal(lastEventKey({ events: [{ event_id: "e1" }] }), "e1");
  assert.equal(lastEventKey({ events: [] }), null);
});

test("take scene changes need a boundary and a later change event", () => {
  assert.equal(takeSceneChangedFromEvents({
    events: [
      { id: 1, kind: "take_load" },
      { id: 2, kind: "dialogue" },
    ],
  }), true);
  assert.equal(takeSceneChangedFromEvents({
    events: [
      { id: 1, kind: "take_load" },
      { id: 2, kind: "npc_mood" },
    ],
  }), false);
  assert.equal(takeSceneChangedFromEvents({
    events: [{ id: 1, kind: "dialogue" }],
  }), null);
  assert.equal(takeSceneChangedFromEvents({
    events: [{ kind: "take_scene" }, { kind: "silence" }],
  }), true);
});

test("relationship and affinity formatting keep the old thresholds", () => {
  assert.equal(connectionLabelFor(0.8, 0.1), "close");
  assert.equal(connectionLabelFor(0.5, 0.1), "steady");
  assert.equal(connectionLabelFor(0.3, 0.1), "strained");
  assert.equal(connectionLabelFor(0.1, 0.1), "distant");
  assert.equal(connectionLabelFor(0.9, 0.9), "rival");
  assert.equal(edgeClass(0.7), "is-high");
  assert.equal(edgeClass(0.4), "is-mid");
  assert.equal(edgeClass(0.39), "is-low");
  assert.equal(sourceLabel({ source_kind: "character", source_id: "alice" }), "alice");
  assert.equal(sourceLabel({ source_kind: "user" }), "user");
  assert.equal(sourceLabel(null), "");
  assert.equal(seqStep(0.61), 3);
  assert.equal(seqStep(1.7), 5);
  assert.equal(scaleFactor(1), "x1");
  assert.equal(scaleFactor(60), "x60");
  assert.equal(scaleFactor(2.555), "x2.56");
  assert.equal(clockScaleLabel({ scale: 1 }), "MOCK");
  assert.equal(clockScaleLabel({ scale: 60 }), "REAL x60");
  assert.equal(clockScaleLabel(null), "MOCK");
});

test("affinity and hearts render at five steps", () => {
  assert.equal(affinityFor({ relationships: [] }, "alice"), 0.4);
  const data = {
    relationships: [{ a: "alice", b: "user", trust: 1, closeness: 1, tension: 0 }],
  };
  assert.equal(affinityFor(data, "alice"), 1);
  assert.equal(affinityHearts(1), "♥♥♥♥♥");
  assert.equal(affinityHearts(0.4), "♥♥♡♡♡");
  assert.equal(affinityHearts(0.5), "♥♥♥♡♡");
  assert.equal(affinityHearts(-1), "♡♡♡♡♡");
  assert.equal(heartStrip(2), "♥♥♡♡♡");
  assert.equal(heartGlyph(true), "♥");
  assert.equal(heartGlyph(false), "♡");
  assert.equal(itemHolderLabel("user"), "with you");
  assert.equal(itemHolderLabel("alice"), "with Alice");
  assert.equal(itemHolderLabel("the shelf"), "with the shelf");
});

test("connections normalise aliases and clamp numbers", () => {
  const connection = normalizeConnection({
    from: "Alice",
    to: "Emily Park",
    closeness: 1.5,
    tension: -1,
    secrets: "2",
  });
  assert.deepEqual(connection, {
    a: "alice",
    b: "emily",
    affinity: 1,
    tension: 0,
    label: "close",
    shared_secret_count: 2,
  });
  assert.equal(normalizeConnection(null), null);
});
