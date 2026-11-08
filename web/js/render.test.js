import test from "node:test";
import assert from "node:assert/strict";

/* The render modules read a few browser globals while their top-level
   constants initialise. Stub the smallest surface so the pure ending helpers
   can be imported under the node test runner; no DOM code runs here. */
globalThis.window = {
  SWITCH_CAST: {},
  matchMedia: () => ({ matches: true }),
  addEventListener() {},
  visualViewport: null,
};
globalThis.document = {
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  documentElement: { dataset: {} },
  body: { classList: { add() {}, remove() {} } },
};
globalThis.location = { hostname: "", origin: "http://127.0.0.1:8890", search: "" };
globalThis.matchMedia = globalThis.window.matchMedia;

const {
  endingEvidenceList,
  normalizeEnding,
  scenarioEndingMeta,
} = await import("./render/stage.js");

test("normalizeEnding degrades strings and objects to one card shape", () => {
  assert.equal(normalizeEnding(null), null);
  assert.deepEqual(normalizeEnding("bad-end"), {
    id: "bad-end",
    label: "bad-end",
    tone: "bad",
    evidence: [],
  });
  const ending = normalizeEnding({
    id: "w5-good",
    title: "A quiet morning",
    tone: "good ending",
    evidence: [{ key: "secret" }],
  });
  assert.deepEqual(ending, {
    id: "w5-good",
    label: "A quiet morning",
    tone: "good",
    evidence: [{ key: "secret" }],
  });
});

test("endingEvidenceList keeps arrays and flattens objects", () => {
  const list = [{ label: "one" }];
  assert.equal(endingEvidenceList(list), list);
  assert.deepEqual(endingEvidenceList({ secret_shared: true, trust: 0.8 }), [
    "secret shared: true",
    "trust: 0.8",
  ]);
  assert.deepEqual(endingEvidenceList("a line"), ["a line"]);
  assert.deepEqual(endingEvidenceList(null), []);
});

test("scenarioEndingMeta reads string and object endings", () => {
  assert.equal(scenarioEndingMeta(null), null);
  assert.deepEqual(scenarioEndingMeta("w5-bad"), {
    label: "w5 bad",
    tone: "bad",
  });
  assert.deepEqual(scenarioEndingMeta({ id: "w5-good", tone: "GOOD" }), {
    label: "w5-good",
    tone: "good",
  });
  assert.deepEqual(scenarioEndingMeta({ title: "Still here", kind: "neutral" }), {
    label: "Still here",
    tone: "neutral",
  });
});
