/* Pure formatting and data-shape helpers for the dashboard.

   These functions do not touch the store or the DOM: text normalisation, first
   names, clock formatting, affinity/hearts and the small normalisers used by
   the scene and take views.  The cast map is read from `window.SWITCH_CAST`
   (classic `cast.js`) at call time so tests can install a fixture. */
import {
  ACTION_MODES,
  ORDER,
  RESPONSE_MODES,
  TAKE_BOUNDARY_EVENT_KINDS,
  TAKE_CHANGE_EVENT_KINDS,
} from "./vocab.js";

function currentCast() {
  return globalThis.SWITCH_CAST || {};
}

export function heartGlyph(filled) {
  return filled ? "♥" : "♡";
}

export function heartStrip(filled, max = 5) {
  const count = Math.max(0, Math.min(max, Math.round(Number(filled))));
  return "♥".repeat(count) + "♡".repeat(max - count);
}

export function affinityHearts(value, max = 5) {
  return heartStrip(Number(value) * max, max);
}

export function formatClock(iso) {
  try {
    return new Date(iso).toLocaleString("en-GB", {
      timeZone: "Asia/Tokyo",
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

export function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", {
      timeZone: "Asia/Tokyo",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

export function firstName(name) {
  return (name || "").split(" ")[0];
}

export function castIdForName(name) {
  const needle = String(name || "").trim().toLowerCase();
  return ORDER.find((id) => {
    const c = currentCast()[id];
    return c.name.toLowerCase() === needle || c.name.split(" ")[0].toLowerCase() === needle;
  }) || null;
}

export function normalizeActionMode(value) {
  const text = String(value || "").trim().toLowerCase();
  return ACTION_MODES.has(text) ? text : "";
}

export function normalizeResponse(value) {
  const text = String(value || "").trim().toLowerCase();
  return RESPONSE_MODES.has(text) ? text : "";
}

export function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

export function speakerFromText(text) {
  const lowered = String(text || "").trim().toLowerCase();
  if (!lowered) return null;
  return ORDER.find((id) => {
    const cast = currentCast()[id];
    const full = cast.name.toLowerCase();
    const first = cast.name.split(" ")[0].toLowerCase();
    return lowered.startsWith(`${full} `) || lowered.startsWith(`${first} `)
      || lowered.startsWith(`${full}:`) || lowered.startsWith(`${first}:`);
  }) || null;
}

export function stripSpeakerPrefix(text, id) {
  const cast = currentCast()[id];
  if (!cast) return text;
  const value = String(text || "");
  for (const name of [cast.name, cast.name.split(" ")[0]]) {
    if (value.toLowerCase().startsWith(`${name.toLowerCase()} `)) {
      return value.slice(name.length + 1).trim();
    }
  }
  return value;
}

export function firstNameOf(id) {
  const cast = currentCast()[id];
  return cast ? firstName(cast.name) : String(id || "them");
}

export function nameList(ids) {
  const names = ids.filter(Boolean).map(firstNameOf);
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function asCastId(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const lowered = raw.toLowerCase();
  if (lowered === "user" || lowered === "you" || lowered === "the user") return "user";
  if (currentCast()[lowered]) return lowered;
  // Event summaries use suffixes such as "Alice (whisper): ...".
  const cleaned = raw.replace(/\s*\([^)]*\)\s*$/, "").trim();
  if (currentCast()[cleaned.toLowerCase()]) return cleaned.toLowerCase();
  const byName = castIdForName(cleaned);
  if (byName) return byName;
  const firstWord = cleaned.split(/[\s:]+/)[0].toLowerCase();
  return currentCast()[firstWord] ? firstWord : null;
}

export function parseSummary(summary) {
  const text = String(summary || "");
  const match = text.match(/^([^:\n]{1,48}):\s*([\s\S]*)$/);
  return match
    ? { who: match[1].trim(), text: match[2].trim() }
    : { who: "", text: text.trim() };
}

export function eventMeta(event) {
  if (!event) return {};
  const raw = event.metadata !== undefined && event.metadata !== null
    ? event.metadata
    : event.metadata_json;
  if (!raw) return {};
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) || {};
    } catch {
      return {};
    }
  }
  return typeof raw === "object" ? raw : {};
}

export function eventIdNumber(event) {
  const value = Number(event && event.id);
  return Number.isFinite(value) ? value : null;
}

export function takeSceneIsObject(value) {
  return Boolean(value && typeof value === "object" && value.id && value.title);
}

export function takeSceneCount(take) {
  if (!take) return 0;
  if (Array.isArray(take.scenes)) return take.scenes.length;
  const count = Number(take.scene_count !== undefined ? take.scene_count : take.scenes_count);
  return Number.isFinite(count) && count >= 0 ? count : 0;
}

export function takeSceneAt(take, index) {
  if (!take || !Array.isArray(take.scenes)) return null;
  const scene = take.scenes[index];
  return takeSceneIsObject(scene) ? scene : null;
}

export function takeIndexForScene(take, scene) {
  if (!take || !scene || !Array.isArray(take.scenes)) return null;
  if (!scene.id) return null;
  const found = take.scenes.findIndex((item) => item && item.id === scene.id);
  return found >= 0 ? found : null;
}

export function mergeTakeConfig(incoming, previous) {
  if (!incoming) return previous || null;
  if (!previous) return incoming;
  if (Array.isArray(incoming.scenes) || !Array.isArray(previous.scenes)) return incoming;
  const same = (incoming.id && previous.id && incoming.id === previous.id)
    || (!incoming.id && incoming.title && incoming.title === previous.title);
  return same ? { ...previous, ...incoming, scenes: previous.scenes } : incoming;
}

export function stateRevision(source) {
  const value = Number(source && source.revision);
  return Number.isFinite(value) ? value : null;
}

export function stateTurnNumber(source) {
  const raw = source && source.turn;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (raw && typeof raw === "object") {
    const value = Number(raw.number !== undefined ? raw.number : raw.index);
    if (Number.isFinite(value)) return value;
  }
  const direct = Number(source && source.take_turn);
  return Number.isFinite(direct) ? direct : null;
}

export function lastEventKey(source) {
  const events = (source && source.events) || [];
  if (!Array.isArray(events) || !events.length) return null;
  const last = events[events.length - 1] || {};
  if (last.id !== undefined && last.id !== null) return String(last.id);
  if (last.event_id !== undefined && last.event_id !== null) return String(last.event_id);
  return String(events.length);
}

export function takeSceneChangedFromEvents(source) {
  const events = source && Array.isArray(source.events) ? source.events : null;
  if (!events || !events.length) return null;
  let boundaryIndex = -1;
  let boundaryId = null;
  events.forEach((event, index) => {
    const kind = String((event && event.kind) || "");
    if (!TAKE_BOUNDARY_EVENT_KINDS.has(kind)) return;
    const id = eventIdNumber(event);
    if (id === null) {
      boundaryIndex = index;
      boundaryId = null;
    } else if (boundaryId === null || id >= boundaryId) {
      boundaryId = id;
      boundaryIndex = index;
    }
  });
  if (boundaryIndex < 0) return null;
  const after = boundaryId === null
    ? events.slice(boundaryIndex + 1)
    : events.filter((event) => {
      const id = eventIdNumber(event);
      return id !== null && id > boundaryId;
    });
  return after.some((event) => TAKE_CHANGE_EVENT_KINDS.has(String((event && event.kind) || "")));
}

export function connectionLabelFor(affinity, tension) {
  if (tension > 0.55) return "rival";
  if (affinity >= 0.7) return "close";
  if (affinity >= 0.42) return "steady";
  if (affinity >= 0.24) return "strained";
  return "distant";
}

export function normalizeConnection(raw) {
  if (!raw) return null;
  const a = asCastId(raw.a || raw.from || raw.source || raw.character_a);
  const b = asCastId(raw.b || raw.to || raw.target || raw.character_b);
  const affinityValue = raw.affinity !== undefined
    ? raw.affinity
    : (raw.closeness !== undefined ? raw.closeness : raw.trust);
  const affinity = Number(affinityValue);
  const tension = Number(raw.tension);
  return {
    a,
    b,
    affinity: Number.isFinite(affinity) ? Math.max(0, Math.min(1, affinity)) : 0,
    tension: Number.isFinite(tension) ? Math.max(0, Math.min(1, tension)) : 0,
    label: String(raw.label || "").toLowerCase() || connectionLabelFor(affinity, tension),
    shared_secret_count: Number(raw.shared_secret_count || raw.secrets || 0),
  };
}

export function edgeClass(trust) {
  if (trust >= 0.7) return "is-high";
  if (trust >= 0.4) return "is-mid";
  return "is-low";
}

export function sourceLabel(cell) {
  if (!cell) return "";
  if (cell.source_kind === "character") return cell.source_id;
  if (cell.source_kind === "user") return "user";
  if (cell.source_kind === "event") return "event";
  return "obs";
}

export function seqStep(confidence) {
  const n = Math.round(Number(confidence) * 5);
  return Math.max(0, Math.min(5, n));
}

export function scaleFactor(value) {
  const scale = Number(value);
  if (!Number.isFinite(scale) || scale === 1) return "x1";
  const text = Number.isInteger(scale)
    ? String(scale)
    : String(Math.round(scale * 100) / 100);
  return `x${text}`;
}

export function clockScaleLabel(clock) {
  const scale = clock ? Number(clock.scale) : 1;
  if (Number.isFinite(scale) && scale !== 1) return `REAL ${scaleFactor(scale)}`;
  return "MOCK";
}

export function affinityFor(data, id) {
  const edge = (data.relationships || []).find((e) => e.a === id && e.b === "user");
  if (!edge) return 0.4;
  return Math.max(0, Math.min(1, (edge.trust + edge.closeness) / 2 - edge.tension / 2));
}

export function itemHolderLabel(holder) {
  if (!holder) return "";
  if (String(holder).toLowerCase() === "user") return "with you";
  const id = asCastId(holder);
  if (id && currentCast()[id]) return `with ${firstNameOf(id)}`;
  return `with ${holder}`;
}
