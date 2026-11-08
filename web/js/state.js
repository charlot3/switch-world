/* The mutable dashboard store.
 *
 * Field names are the pre-split app.js names on purpose: the views can be moved
 * onto this store one at a time without a rename sweep.  `subscribe()` is the
 * seam a view uses to redraw when a mutation is announced; the existing render
 * functions still call each other directly, so behaviour is unchanged today. */

export const VIEWS = Object.freeze([
  "story", "worlds", "tree", "ledger", "studio", "settings",
]);

function currentSearch() {
  try {
    return globalThis.location ? globalThis.location.search : "";
  } catch {
    return "";
  }
}

function currentStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

export function initialTheme(search = currentSearch(), storage = currentStorage()) {
  const param = new URLSearchParams(search).get("theme");
  if (param === "light" || param === "dark") return param;
  try {
    return (storage && storage.getItem("sw-theme")) || "dark";
  } catch {
    return "dark";
  }
}

export function initialMotion(storage = currentStorage()) {
  try {
    return !storage || storage.getItem("sw-motion") !== "off";
  } catch {
    return true;
  }
}

export function initialView(search = currentSearch()) {
  const param = new URLSearchParams(search).get("view");
  return VIEWS.includes(param) ? param : "story";
}

function defaultState() {
  return {
    data: null,
    view: initialView(),
    selected: "alice",
    typedKey: null,
    typingKey: null,
    typing: null,
    theme: initialTheme(),
    motion: initialMotion(),
    phone: {
      character: null,
      messages: [],
      hasMore: false,
      oldestId: null,
      loading: false,
      loadingFor: null,
      sending: false,
      loadedFor: null,
      error: "",
      paintSig: null,
    },
    group: { sending: false },
    turn: null,
    whisper: false,
    whisperTarget: null,
    groupStatus: "",
    clockStatus: "",
    beatId: null,
    treeLens: "user",
    worlds: {
      scenarios: null,
      current: null,
      loading: false,
      loadingScenario: null,
      error: "",
      fetchedAt: 0,
      status: "",
    },
    takes: {
      list: null,
      current: null,
      loading: false,
      loadingTake: null,
      advancing: false,
      error: "",
      status: "",
      fetchedAt: 0,
      probed: false,
      currentFetchedAt: 0,
      nextNote: "",
      changed: false,
      sceneRevision: null,
      sceneTurn: null,
      sceneEventKey: null,
    },
    safety: {
      paused: false,
      busy: false,
      ready: false,
      status: "",
    },
    studio: { data: null, error: "", loading: false, fetchedAt: 0 },
  };
}

/** A fresh store with the same shape as the singleton. */
export function createState(seed = {}) {
  const base = defaultState();
  return {
    ...base,
    ...seed,
    phone: { ...base.phone, ...(seed.phone || {}) },
    group: { ...base.group, ...(seed.group || {}) },
    worlds: { ...base.worlds, ...(seed.worlds || {}) },
    takes: { ...base.takes, ...(seed.takes || {}) },
    safety: { ...base.safety, ...(seed.safety || {}) },
    studio: { ...base.studio, ...(seed.studio || {}) },
  };
}

export const state = createState();

const listeners = new Set();

/** Register a listener; returns an unsubscribe function. */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Tell subscribers that the store changed, without prescribing the shape. */
export function notify(reason = "state") {
  for (const listener of [...listeners]) listener(state, reason);
}
