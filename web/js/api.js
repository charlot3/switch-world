/* The dashboard's single fetch layer.
 *
 * Every request goes through `api()`, which keeps the old error contract:
 * non-2xx responses throw an Error whose `message` is the server detail (nested
 * `detail` objects included) and which carries `status`, `body` and `code`.
 * The `http` helpers mirror the request bodies in
 * `switch_world/interfaces/http/schemas.py`; the current views still call
 * `api()` with the same hand-built payloads until they are migrated. */

export async function api(path, options = {}) {
  const { fetchImpl = globalThis.fetch, ...init } = options;
  const response = await fetchImpl(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    const nested = body && body.detail && typeof body.detail === "object"
      ? { ...body, ...body.detail }
      : body;
    const detail = nested && (nested.detail || nested.message || nested.reason || nested.error)
      ? (nested.detail || nested.message || nested.reason || nested.error)
      : (text || response.statusText);
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = response.status;
    error.body = body;
    error.code = nested && nested.error ? String(nested.error) : "";
    throw error;
  }
  return body;
}

export function get(path) {
  return api(path);
}

export function post(path, payload) {
  const options = { method: "POST" };
  if (payload !== undefined) options.body = JSON.stringify(payload);
  return api(path, options);
}

let requestSequence = 0;

/** An idempotency key for routes that accept `request_id`. */
export function newRequestId(prefix = "web") {
  const random = globalThis.crypto && typeof globalThis.crypto.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${(requestSequence += 1).toString(36)}-`
      + Math.random().toString(36).slice(2, 10);
  return `${prefix}-${random}`;
}

/** Add `request_id` only when the caller supplied one, so old payloads stay byte-identical. */
export function withRequestId(payload, requestId) {
  return requestId ? { ...payload, request_id: requestId } : { ...payload };
}

function compact(object) {
  return Object.fromEntries(
    Object.entries(object).filter(([, value]) => value !== undefined && value !== null),
  );
}

function query(params) {
  const entries = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  return entries.length ? `?${entries.join("&")}` : "";
}

export const http = {
  state: () => get("/api/state"),
  canon: () => get("/api/canon"),
  matrix: () => get("/api/matrix"),
  clock: () => get("/api/clock"),
  safety: () => get("/api/safety"),
  friends: () => get("/api/friends"),
  whoKnows: (key) => get(`/api/who-knows/${encodeURIComponent(key)}`),
  sceneCard: () => get("/api/scene-card"),
  studioSummary: () => get("/api/studio/summary"),

  groupSay: ({ message = "", characters = null, timeout = null, requestId = null,
    expectedRevision = null } = {}) => post("/api/group/say", compact({
    message,
    characters,
    timeout,
    request_id: requestId,
    expected_revision: expectedRevision,
  })),
  groupWhisper: ({ to = "", message = "", timeout = null } = {}) => post(
    "/api/group/whisper",
    compact({ to, message, timeout }),
  ),
  dm: ({ character = "", message = "" } = {}) => post("/api/dm", { character, message }),
  dmHistory: (character, { limit = 100, beforeId = null } = {}) => get(
    `/api/dm/${encodeURIComponent(character)}${query({ limit, before_id: beforeId })}`,
  ),
  addFriend: (character) => post(`/api/friends/${encodeURIComponent(character)}`),

  scenarios: () => get("/api/scenarios"),
  loadScenario: (id) => post(`/api/scenarios/${encodeURIComponent(id)}/load`),
  evaluateEnding: () => post("/api/endings/evaluate", {}),

  takes: () => get("/api/takes"),
  takeCurrent: () => get("/api/takes/current"),
  loadTake: (id) => post(`/api/takes/${encodeURIComponent(id)}/load`),
  takesNext: ({ force = false, requestId = null, expectedRevision = null } = {}) => post(
    "/api/takes/next",
    withRequestId(compact({ force, expected_revision: expectedRevision }), requestId),
  ),
  takesCue: ({ line = "", choice = null } = {}) => post(
    "/api/takes/cue",
    compact({ line, choice }),
  ),

  clockMode: ({ mode = "", scale = null } = {}) => post(
    "/api/clock/mode",
    compact({ mode, scale }),
  ),
  clockAdvance: ({ offscreen = false, minutes = null, character = null, kind = null,
    beat = null, run = false } = {}) => post("/api/clock/advance", compact({
    offscreen,
    minutes,
    character,
    kind,
    beat,
    run,
  })),
  safetyPause: (paused = true) => post("/api/safety/pause", { paused }),
  safetyResume: () => post("/api/safety/resume", {}),

  tellAlice: ({ secret = null, key = null } = {}) => post(
    "/api/dev/tell-alice",
    compact({ secret, key }),
  ),
  runCafe: ({ forceShare = null } = {}) => post(
    "/api/dev/run-cafe",
    compact({ force_share: forceShare }),
  ),
  runBeat: ({ beat = "cafe", transport = "local", forceShare = null } = {}) => post(
    "/api/dev/run-beat",
    compact({ beat, transport, force_share: forceShare }),
  ),
  runArc: ({ forceShare = null } = {}) => post(
    "/api/dev/run-arc",
    compact({ force_share: forceShare }),
  ),
  tavilyEvent: ({ query = null } = {}) => post(
    "/api/dev/tavily-event",
    compact({ query }),
  ),
  reset: () => post("/api/dev/reset", {}),
};
