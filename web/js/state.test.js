import test from "node:test";
import assert from "node:assert/strict";

import {
  createState,
  initialMotion,
  initialTheme,
  initialView,
  notify,
  state,
  subscribe,
  VIEWS,
} from "./state.js";

function fakeStorage(values = {}) {
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null;
    },
    setItem(key, value) {
      values[key] = String(value);
    },
  };
}

test("initial view, theme and motion come from the URL and local storage", () => {
  assert.deepEqual(VIEWS, ["story", "worlds", "tree", "ledger", "studio", "settings"]);
  assert.equal(initialView("?view=ledger"), "ledger");
  assert.equal(initialView("?view=nope"), "story");
  assert.equal(initialView(""), "story");
  assert.equal(initialTheme("?theme=light", fakeStorage()), "light");
  assert.equal(initialTheme("", fakeStorage({ "sw-theme": "light" })), "light");
  assert.equal(initialTheme("", fakeStorage()), "dark");
  assert.equal(initialMotion(fakeStorage({ "sw-motion": "off" })), false);
  assert.equal(initialMotion(fakeStorage()), true);
});

test("createState keeps the current field names and deep defaults", () => {
  const store = createState({ view: "tree", phone: { character: "mia" } });
  assert.equal(store.view, "tree");
  assert.equal(store.selected, "alice");
  assert.equal(store.data, null);
  assert.deepEqual(store.phone, {
    character: "mia",
    messages: [],
    hasMore: false,
    oldestId: null,
    loading: false,
    loadingFor: null,
    sending: false,
    loadedFor: null,
    error: "",
    paintSig: null,
  });
  assert.deepEqual(store.group, { sending: false });
  assert.equal(store.takes.changed, false);
  assert.equal(store.safety.paused, false);
  assert.equal(store.studio.data, null);
  assert.equal(store.treeLens, "user");
  assert.notEqual(createState(), createState());
});

test("the singleton is mutable and subscribers hear notify()", () => {
  const calls = [];
  const off = subscribe((store, reason) => calls.push([store, reason]));
  state.selected = "emily";
  notify("selection");
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], state);
  assert.equal(calls[0][1], "selection");
  off();
  notify("after-unsubscribe");
  assert.equal(calls.length, 1);
  state.selected = "alice";
});
