/* Story, Worlds, Takes and ending surfaces.

   Do not import main.js from here: it is the entry/wiring module. Actions in
   this module call back into views.js for refresh/render/setView. */

import { api } from "../api.js";
import {
  affinityFor,
  asCastId,
  clockScaleLabel,
  eventMeta,
  firstName,
  firstNameOf,
  formatTime,
  heartGlyph,
  heartStrip,
  itemHolderLabel,
  lastEventKey,
  mergeTakeConfig,
  nameList,
  normalizeActionMode,
  normalizeResponse,
  normalizeText,
  parseSummary,
  scaleFactor,
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
} from "../format.js";
import { state } from "../state.js";
import { CAST_ORDER as ORDER, SCENE_EVENT_KINDS, SPEECH_MODES } from "../vocab.js";
import { $, $$, CAST, SECRET_KEY, setArtWithFallback } from "./dom.js";
import { closeProfile, openProfile } from "./ledger.js";
import {
  addFriend,
  closePhone,
  isFriend,
  openPhone,
  renderPhone,
  resetPhoneFor,
  resetPhoneHistorySeq,
  selectCast,
} from "./phone.js";
import { loadStudio } from "./studio.js";
import { refresh, render, setView } from "../views.js";

export function currentBeat(data) {
  const scene = (data && data.scene) || {};
  if (scene.current_beat) return scene.current_beat;
  const beats = (data && data.canon && data.canon.beats) || [];
  return beats[0] || null;
}
/* ---- scenarios --------------------------------------------------------- */

/* GET /api/state carries `scenario` when a preset is active. The Worlds view
   also keeps the last loaded preset so the UI can render before the next poll.
   Every helper degrades to the base canon when the backend has no scenarios. */
export function currentScenario(data) {
  const source = data === undefined ? state.data : data;
  if (source && Object.prototype.hasOwnProperty.call(source, "scenario")) {
    const value = source.scenario;
    if (value && typeof value === "object" && (value.id || value.title)) return value;
    if (value === null) return null;
  }
  return state.worlds.current || null;
}
/* ---- takes ------------------------------------------------------------- */

/* A take is a linear recording route on top of a scenario. The backend may
   report it through GET /api/takes/current (the canonical shape) or inline in
   GET /api/state as take / take_scene. Both paths degrade to "no take". */











/* The backend keeps `take_scene_changed` in meta but does not expose it on
   /api/state. The same fact is derivable from the event log: a take_load or
   take_scene event opens a scene, and a turn/cue event after it changes it. */

/* Fall back to the recorded group turns when /api/state does not carry a
   numeric `turn`. Each group turn writes one stable turn_id into metadata. */
export function inferredTurnNumber(source) {
  const direct = stateTurnNumber(source);
  if (direct !== null) return direct;
  const events = source && Array.isArray(source.events) ? source.events : [];
  const ids = new Set();
  events.forEach((event) => {
    const meta = eventMeta(event);
    const id = meta.turn_id || meta.turnId;
    if (id) ids.add(String(id));
  });
  return ids.size;
}

/* The latest turn plan's action mode, from state.turn when available and from
   the recorded turn_plan event otherwise. Unknown values are dropped. */
export function latestActionMode(source) {
  const plan = (source && source.turn && source.turn.plan)
    || (state.turn && state.turn.plan)
    || {};
  const direct = normalizeActionMode(plan.action_mode || plan.actionMode);
  if (direct) return direct;
  const events = source && Array.isArray(source.events) ? source.events : [];
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (String((event && event.kind) || "") !== "turn_plan") continue;
    const meta = eventMeta(event);
    const eventPlan = meta.plan && typeof meta.plan === "object" ? meta.plan : {};
    return normalizeActionMode(
      eventPlan.action_mode || eventPlan.actionMode
      || meta.action_mode || meta.actionMode,
    );
  }
  return "";
}

export function setTakeCurrent(raw) {
  if (!raw) {
    state.takes.current = null;
    return null;
  }
  const take = raw.take && typeof raw.take === "object" ? raw.take : null;
  if (!take || !(take.id || take.title)) {
    state.takes.current = null;
    return null;
  }
  let scene = takeSceneIsObject(raw.scene) ? raw.scene : null;
  let index = Number(raw.index !== undefined ? raw.index : raw.scene_index);
  if (!Number.isFinite(index)) index = takeIndexForScene(take, scene);
  if (!Number.isFinite(index)) index = 0;
  index = Math.max(0, index);
  if (!scene) scene = takeSceneAt(take, index);
  state.takes.current = {
    take,
    scene,
    index,
    state: raw.state && typeof raw.state === "object" ? raw.state : null,
  };
  return state.takes.current;
}

export function takeSceneFromData(data) {
  if (!data) return null;
  const candidates = [data.take_scene, data.current_scene, data.scene];
  for (const value of candidates) {
    if (takeSceneIsObject(value)) return value;
  }
  return null;
}

export function takeIndexFromData(data) {
  const candidates = [
    data && data.take_index,
    data && data.scene_index,
    data && data.take && data.take.index,
  ];
  for (const value of candidates) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return null;
}

export function currentTakeInfo(data) {
  const source = data === undefined ? state.data : data;
  const current = state.takes.current;
  let take = current ? current.take : null;
  let scene = current ? current.scene : null;
  let index = current ? current.index : 0;
  let explicit = false;
  if (source && Object.prototype.hasOwnProperty.call(source, "take")) {
    explicit = true;
    take = source.take && typeof source.take === "object" ? source.take : null;
    if (!take) {
      return { take: null, scene: null, index: 0, count: 0, source };
    }
    take = mergeTakeConfig(take, current && current.take);
  }
  const directScene = takeSceneFromData(source);
  if (directScene) scene = directScene;
  const directIndex = takeIndexFromData(source);
  if (directIndex !== null) index = directIndex;
  if (!take && !explicit && current) {
    take = current.take;
    scene = current.scene;
    index = current.index;
  }
  if (take && !scene) scene = takeSceneAt(take, index);
  if (take && scene && directIndex === null) {
    const found = takeIndexForScene(take, scene);
    if (found !== null) index = found;
  }
  return { take, scene, index, count: takeSceneCount(take), source };
}

export function takeSource(data) {
  const current = state.takes.current;
  if (data && (Object.prototype.hasOwnProperty.call(data, "take")
    || Object.prototype.hasOwnProperty.call(data, "take_scene")
    || takeSceneIsObject(data.scene))) {
    return data;
  }
  if (current && current.state) return current.state;
  return data || state.data || {};
}

export function markSceneBaseline(source) {
  const data = source || state.data || {};
  state.takes.sceneRevision = stateRevision(data);
  state.takes.sceneTurn = stateTurnNumber(data);
  state.takes.sceneEventKey = lastEventKey(data);
  state.takes.changed = takeSceneChangedFromEvents(data) === true;
}

export function syncTakeChange(data) {
  if (!state.takes.current) return;
  const source = takeSource(data);
  const revision = stateRevision(source);
  const turn = stateTurnNumber(source);
  const eventKey = lastEventKey(source);
  // If the load response carried no revision/event baseline, adopt the first
  // observed value; later changes still count.
  if (state.takes.sceneRevision === null && revision !== null) {
    state.takes.sceneRevision = revision;
  }
  if (state.takes.sceneTurn === null && turn !== null) {
    state.takes.sceneTurn = turn;
  }
  if (state.takes.sceneEventKey === null && eventKey !== null) {
    state.takes.sceneEventKey = eventKey;
  }
  if (revision !== null && state.takes.sceneRevision !== null
    && revision > state.takes.sceneRevision) {
    state.takes.changed = true;
  }
  if (turn !== null && state.takes.sceneTurn !== null && turn > state.takes.sceneTurn) {
    state.takes.changed = true;
  }
  if (eventKey !== null && state.takes.sceneEventKey !== null
    && eventKey !== state.takes.sceneEventKey) {
    state.takes.changed = true;
  }
  if (takeSceneChangedFromEvents(source) === true) {
    state.takes.changed = true;
  }
  if (source && (source.scene_changed === true || source.take_changed === true
    || source.changed === true)) {
    state.takes.changed = true;
  }
  const takeState = state.takes.current.take;
  const sceneState = state.takes.current.scene;
  if (takeState && (takeState.changed === true || takeState.scene_changed === true)) {
    state.takes.changed = true;
  }
  if (sceneState && (sceneState.changed === true || sceneState.dirty === true
    || sceneState.player_turn === true)) {
    state.takes.changed = true;
  }
}

export function syncTakeState(data) {
  if (!data) return;
  const hasTake = Object.prototype.hasOwnProperty.call(data, "take");
  const scene = takeSceneFromData(data);
  if (!hasTake && !scene) {
    syncTakeChange(data);
    return;
  }
  if (hasTake && (!data.take || typeof data.take !== "object")) {
    state.takes.current = null;
    state.takes.changed = false;
    return;
  }
  const previous = state.takes.current;
  const incoming = hasTake ? data.take : (previous ? previous.take : null);
  const take = mergeTakeConfig(incoming, previous && previous.take);
  if (!take) {
    syncTakeChange(data);
    return;
  }
  let index = takeIndexFromData(data);
  if (index === null) index = previous ? previous.index : 0;
  const nextScene = scene || takeSceneAt(take, index) || (previous ? previous.scene : null);
  const changedScene = !previous
    || previous.index !== index
    || (previous.take && take.id && previous.take.id !== take.id)
    || (previous.scene && nextScene && previous.scene.id && nextScene.id
      && previous.scene.id !== nextScene.id);
  state.takes.current = { take, scene: nextScene, index, state: data };
  if (changedScene) markSceneBaseline(data);
  syncTakeChange(data);
}

export function takeAdvanceState(data) {
  const info = currentTakeInfo(data);
  if (!info.take) {
    return { ok: false, reason: "Load a take below to start a route." };
  }
  if (state.safety.paused) {
    return { ok: false, reason: "The scene is paused. Resume in Studio to advance." };
  }
  const scene = info.scene;
  const count = info.count;
  const isLast = (scene && scene.next === null)
    || (count > 0 && info.index >= count - 1);
  if (isLast) {
    return { ok: false, reason: "This is the last scene — the route ends here." };
  }
  const mustChange = !scene || scene.must_change !== false;
  if (mustChange && !state.takes.changed) {
    return { ok: false, reason: "Say a line or let a cue change the scene before advancing." };
  }
  const nextNumber = info.index + 2;
  return {
    ok: true,
    reason: count
      ? `Scene ${nextNumber} of ${count} is ready.`
      : "The next scene is ready.",
  };
}
export function scenarioCastIds(data) {
  const scenario = currentScenario(data);
  const list = scenario && Array.isArray(scenario.cast) ? scenario.cast : null;
  if (!list || !list.length) return null;
  const ids = list.map((id) => asCastId(id)).filter((id) => id && CAST[id]);
  return ids.length ? ids : null;
}

export function scenarioOutfits(data) {
  const direct = data && data.outfits;
  if (direct && typeof direct === "object" && Object.keys(direct).length) return direct;
  const scenario = currentScenario(data);
  return scenario && scenario.outfits && typeof scenario.outfits === "object"
    ? scenario.outfits
    : {};
}

export function outfitFor(data, id) {
  const row = scenarioOutfits(data)[id];
  const scenario = currentScenario(data);
  const spec = scenario && scenario.outfits && typeof scenario.outfits === "object"
    ? scenario.outfits[id]
    : null;
  if (!row && !spec) return null;
  if (typeof row === "string") return { id: row, label: row };
  const base = (spec && typeof spec === "object") ? spec : {};
  const stored = (row && typeof row === "object") ? row : {};
  return {
    ...base,
    ...stored,
    id: stored.id || stored.outfit_id || base.id || null,
    label: stored.label || base.label || stored.outfit_id || base.id || null,
    art: stored.art || base.art || "",
    reason: stored.reason || base.reason || "",
    source_belief: stored.source_belief || stored.source_belief_key
      || base.source_belief || null,
  };
}

export function outfitArtFor(data, id) {
  const outfit = outfitFor(data, id);
  if (!outfit) return null;
  if (outfit.art) return outfit.art;
  if (outfit.id) {
    return `/static/assets/portraits/outfits/${id}-${outfit.id}.jpg`;
  }
  return null;
}

export function scenarioCastArt(data) {
  const direct = data && data.cast_art;
  if (direct && typeof direct === "object" && Object.keys(direct).length) return direct;
  const scenario = currentScenario(data);
  return (scenario && scenario.cast_art && typeof scenario.cast_art === "object")
    ? scenario.cast_art
    : {};
}

export function castArtFor(data, id) {
  const value = scenarioCastArt(data)[id];
  if (!value) return null;
  return typeof value === "string" ? value : (value.art || null);
}

export function scenarioSceneArt(data) {
  const scenario = currentScenario(data);
  const evening = scenario && scenario.scene_art_evening;
  let hour = null;
  try { hour = new Date(data && data.clock && data.clock.now).getHours(); } catch { hour = null; }
  if (evening && hour !== null && hour >= 17) return evening;
  const direct = data && data.scene_art;
  if (direct) return typeof direct === "string" ? direct : (direct.art || null);
  const value = scenario && scenario.scene_art;
  if (!value) return null;
  return typeof value === "string" ? value : (value.art || null);
}

export function scenarioItem(data) {
  const item = (data && data.item) || ((currentScenario(data) || {}).item);
  if (!item) return null;
  if (typeof item === "string") return { id: item, label: item };
  return item;
}

export function connectionList(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value).filter(Boolean);
  return [];
}

export function scenarioConnections(data) {
  const direct = data && data.connections;
  if (Array.isArray(direct) || (direct && typeof direct === "object")) {
    return connectionList(direct);
  }
  const scenario = currentScenario(data);
  return scenario ? connectionList(scenario.connections) : [];
}

export function sceneCharacters(data) {
  const takeInfo = currentTakeInfo(data);
  const takeScene = takeInfo.take ? takeInfo.scene : null;
  if (takeScene && Array.isArray(takeScene.cast) && takeScene.cast.length) {
    const ids = takeScene.cast.map((id) => asCastId(id)).filter((id) => id && CAST[id]);
    if (ids.length) return ids;
  }
  const scenarioCast = scenarioCastIds(data);
  if (scenarioCast) return scenarioCast;
  const beat = currentBeat(data);
  if (!beat || !beat.characters || !beat.characters.length) return ORDER.slice();
  return beat.characters.map((id) => String(id).toLowerCase()).filter((id) => CAST[id]);
}




/* Absent characters come from the optional state field, the studio summary, and
   the sanitised boundary_violation events (participants only, never act text). */
export function absentSet(data) {
  const result = new Set();
  const add = (value) => {
    if (!value) return;
    if (typeof value === "object") {
      const key = value.id || value.character || value.name;
      if (value.absent !== false && value.absent !== undefined) add(key);
      return;
    }
    const id = asCastId(value);
    if (id && CAST[id]) result.add(id);
  };
  const direct = data && (data.absent || data.absent_characters);
  if (Array.isArray(direct)) direct.forEach(add);
  else if (direct && typeof direct === "object") {
    Object.entries(direct).forEach(([key, value]) => { if (value) add(key); });
  }
  const sceneAbsent = data && data.scene && (data.scene.absent || data.scene.absent_characters);
  if (Array.isArray(sceneAbsent)) sceneAbsent.forEach(add);
  const studioAgents = state.studio.data && state.studio.data.agents;
  if (Array.isArray(studioAgents)) {
    studioAgents.forEach((agent) => { if (agent && agent.absent) add(agent.id || agent.character); });
  }
  ((data && data.events) || []).forEach((event) => {
    if (event.kind !== "boundary_violation") return;
    const meta = eventMeta(event);
    const target = meta.target
      || (event.participants || []).find((id) => String(id).toLowerCase() !== "user");
    if (target) add(target);
  });
  if (state.turn && state.turn.boundary && state.turn.boundaryTarget) {
    add(state.turn.boundaryTarget);
  }
  return result;
}

export function latestBoundary(data) {
  const events = ((data && data.events) || []).filter((event) => event.kind === "boundary_violation");
  return events.length ? events[events.length - 1] : null;
}


export const BEAT_ART = {
  "morning-shop": "/static/assets/portraits/beat-morning-shop.jpg",
  "truck-lunch": "/static/assets/portraits/beat-truck-lunch.jpg",
};
export function beatArtFor(data, cast) {
  const beat = currentBeat(data);
  return (beat && BEAT_ART[beat.id]) || cast.scene || cast.full || cast.portrait;
}

/* The portrait is the selected character: outfit art wins over cast art, then
   the scenario scene CG, then the authored beat CG. The backdrop is the scene
   CG so the stage still reads as the place, not only the person. */
export function sceneArtFor(data, cast) {
  const info = currentTakeInfo(data);
  const takeScene = info.take ? info.scene : null;
  if (takeScene && takeScene.art) return takeScene.art;
  return scenarioSceneArt(data)
    || outfitArtFor(data, cast.id)
    || castArtFor(data, cast.id)
    || beatArtFor(data, cast);
}

export function sceneBackdropFor(data, cast) {
  const info = currentTakeInfo(data);
  const takeScene = info.take ? info.scene : null;
  if (takeScene && (takeScene.art_backdrop || takeScene.art)) {
    return takeScene.art_backdrop || takeScene.art;
  }
  return scenarioSceneArt(data) || sceneArtFor(data, cast);
}



/* The scene log is built from events. Metadata is trusted when the backend sends
   it; otherwise the summary prefix ("Alice: ...") carries enough for a plain log. */
export function buildEventEntries(data) {
  const entries = [];
  ((data && data.events) || []).forEach((event) => {
    const kind = String(event.kind || "");
    if (!SCENE_EVENT_KINDS.has(kind)) return;
    const meta = eventMeta(event);
    const summary = parseSummary(event.summary);
    const boundary = kind === "boundary_violation";
    let mode = meta.mode || "";
    if (!mode) {
      if (boundary) mode = "boundary";
      else if (kind === "silence") mode = "silence";
      else if (kind === "reaction" || kind === "action" || kind === "chorus") mode = kind;
      else if (kind === "whisper" || kind === "whisper_reply") mode = kind;
      else mode = "speech";
    }
    let rawWho = meta.character || meta.speaker || summary.who || "";
    const inferred = !rawWho ? speakerFromText(summary.text) : null;
    if (inferred) rawWho = inferred;
    const isUser = /^(you|user|the user)\b/i.test(String(rawWho).trim());
    const castId = isUser ? null : asCastId(rawWho);
    let text = boundary ? String(event.summary || "") : summary.text;
    if (inferred && !boundary && text) text = stripSpeakerPrefix(text, inferred);
    if (!text && (mode === "silence" || meta.role === "silent")) {
      text = `${firstNameOf(castId || rawWho)} stays quiet.`;
    }
    const generator = String(meta.generator || "").toLowerCase();
    entries.push({
      key: `ev-${event.id}`,
      eventId: event.id,
      kind,
      mode,
      role: meta.role || "",
      castId: castId && CAST[castId] ? castId : null,
      isUser,
      speaker: isUser ? "You" : (CAST[castId] ? CAST[castId].name : (rawWho || "The room")),
      text: text || "",
      expression: meta.expression || "",
      target: meta.target || "",
      chorus: Boolean(meta.chorus) || mode === "chorus",
      private: Boolean(meta.private) || event.visibility === "private"
        || mode === "whisper" || mode === "whisper_reply",
      silent: mode === "silence" || meta.role === "silent",
      boundary: boundary || mode === "boundary",
      authored: generator === "authored" || meta.authored === true
        || meta.fallback === true || event.authored === true,
      generator,
      actionMode: normalizeActionMode(meta.action_mode || meta.actionMode),
      response: normalizeResponse(meta.response),
      turnId: meta.turn_id || meta.turnId || null,
      beatIndex: -1,
      ts: event.created_at,
      snapshot: event,
    });
  });
  const counters = new Map();
  entries.forEach((entry) => {
    if (entry.isUser) {
      entry.beatIndex = -1;
      return;
    }
    if (!entry.turnId) return;
    const next = counters.get(entry.turnId) || 0;
    entry.beatIndex = next;
    counters.set(entry.turnId, next + 1);
  });
  return entries;
}

export function beatFromResponse(raw, fallbackMode, plan) {
  if (!raw || typeof raw !== "object") return null;
  const who = raw.character || raw.speaker || raw.id || raw.agent || "";
  const castId = asCastId(who) || who;
  const mode = raw.mode || raw.kind || fallbackMode || "speech";
  let text = String(raw.text || raw.line || raw.message || "").trim();
  if (!text && (mode === "silence" || raw.role === "silent")) {
    text = `${firstNameOf(castId)} stays quiet.`;
  }
  const meta = raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {};
  const generator = String(raw.generator || meta.generator || "").toLowerCase();
  return {
    character: castId,
    castId: CAST[castId] ? castId : null,
    speaker: castId === "user" ? "You" : (CAST[castId] ? CAST[castId].name : (who || "The room")),
    mode,
    role: raw.role || "",
    text,
    expression: raw.expression || "",
    target: raw.target || (plan && plan.target) || null,
    chorus: Boolean(raw.chorus) || mode === "chorus"
      || Boolean(plan && plan.chorus && mode === "speech"),
    private: Boolean(raw.private) || mode === "whisper" || mode === "whisper_reply"
      || raw.visibility === "private",
    silent: mode === "silence" || raw.role === "silent",
    authored: generator === "authored" || raw.authored === true
      || raw.fallback === true || raw.rehearsal === true,
    generator,
    actionMode: normalizeActionMode(raw.action_mode || meta.action_mode || meta.actionMode),
    response: normalizeResponse(raw.response || meta.response),
    eventId: raw.event_id || null,
  };
}

/* The contract returns result.turn.lines. Keep the older replies shape as a
   fallback so the frontend keeps working while the backend is in flight. */
export function extractTurnLines(result, whisper, plan) {
  const raw = [];
  const push = (items, mode) => {
    if (!Array.isArray(items)) return;
    items.forEach((item) => {
      if (!item) return;
      if (typeof item === "string") raw.push({ character: null, text: item, mode });
      else raw.push({ ...item, mode: item.mode || item.kind || mode });
    });
  };
  if (result) {
    if (result.turn) push(result.turn.lines, "speech");
    const hasTurnLines = Boolean(result.turn && Array.isArray(result.turn.lines) && result.turn.lines.length);
    if (!hasTurnLines) {
      // Compatibility with the pre-turn backend shape.
      push(result.lines, "speech");
      push(result.reactions, "reaction");
      push(result.replies, whisper ? "whisper_reply" : "speech");
      if (result.reply && typeof result.reply === "object") {
        raw.push({ ...result.reply, mode: result.reply.mode || (whisper ? "whisper_reply" : "speech") });
      }
      if (result.whisper_reply && typeof result.whisper_reply === "object") {
        raw.push({ ...result.whisper_reply, mode: "whisper_reply" });
      }
    }
  }
  const seen = new Set();
  const beats = [];
  raw.forEach((item) => {
    const beat = beatFromResponse(item, whisper ? "whisper_reply" : "speech", plan);
    if (!beat || !beat.text) return;
    // The contract puts the user's own whispered words in turn.lines with the
    // target's character id; the optimistic user line already renders them.
    if (whisper && beat.mode === "whisper") return;
    if (beat.character === "user" || /^(you|user)$/i.test(String(beat.character || ""))) return;
    const key = `${beat.character}|${beat.mode}|${normalizeText(beat.text)}`;
    if (seen.has(key)) return;
    seen.add(key);
    beats.push(beat);
  });
  return beats;
}

export function directionText(turn) {
  if (!turn) return "";
  const plan = turn.plan || {};
  if (plan.whisper || turn.userPrivate) {
    const target = plan.target || turn.whisperTo || plan.primary || state.whisperTarget;
    const name = target && CAST[target] ? firstNameOf(target) : "";
    return name
      ? `You whisper to ${name}. The others only notice that something passed between you.`
      : "You whisper. The others only notice that something passed between you.";
  }
  if (plan.boundary && plan.boundary !== "none") {
    return "The scene cuts on the consequence. The act itself is not shown.";
  }
  const primary = plan.primary ? firstNameOf(plan.primary) : "";
  const reactors = (plan.reactors || []).map(firstNameOf).filter(Boolean);
  const silent = (plan.silent || []).map(firstNameOf).filter(Boolean);
  if (plan.chorus) {
    const chorusNames = [...new Set([
      primary,
      ...(plan.chorusNames || plan.chorus_speakers || plan.reactors || []).map(firstNameOf),
    ].filter(Boolean))];
    const chorus = chorusNames.length
      ? `A chorus: ${nameList(chorusNames)} answer together`
      : "A chorus answers together";
    return silent.length
      ? `${chorus}; ${nameList(silent)} stay${silent.length === 1 ? "s" : ""} quiet.`
      : `${chorus}.`;
  }
  const pieces = [];
  if (primary) pieces.push(`${primary} takes the lead`);
  if (reactors.length) pieces.push(`${nameList(reactors)} react${reactors.length === 1 ? "s" : ""}`);
  if (silent.length) pieces.push(`${nameList(silent)} stay${silent.length === 1 ? "s" : ""} quiet`);
  return pieces.length ? `${pieces.join(" · ")}.` : "The room responds.";
}
/* ---- story ------------------------------------------------------------ */

export function cancelTyping() {
  if (!state.typing) return;
  clearInterval(state.typing);
  state.typing = null;
  state.typingKey = null;
}

export function typeLine(element, text, key) {
  if (state.typing && state.typingKey === key) return;
  if (state.typing) {
    clearInterval(state.typing);
    state.typing = null;
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches || !state.motion;
  if (reduced || key === state.typedKey) {
    element.textContent = text;
    element.classList.add("is-done");
    state.typedKey = key;
    return;
  }
  element.textContent = "";
  element.classList.remove("is-done");
  let i = 0;
  state.typedKey = key;
  state.typingKey = key;
  state.typing = setInterval(() => {
    i += 1;
    element.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(state.typing);
      state.typing = null;
      state.typingKey = null;
      element.classList.add("is-done");
    }
  }, 16);
}
/* ---- scenario story surfaces ------------------------------------------ */


export function renderScenarioItem(data) {
  const box = $("#scene-item");
  if (!box) return;
  const item = scenarioItem(data);
  if (!item) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  box.replaceChildren();
  const label = document.createElement("span");
  label.className = "scene-item-label";
  label.textContent = "Item";
  const name = document.createElement("strong");
  name.textContent = item.label || item.id || "carried item";
  box.append(label, name);
  const holder = itemHolderLabel(item.holder);
  if (holder) {
    const who = document.createElement("span");
    who.className = "scene-item-holder";
    who.textContent = holder;
    box.appendChild(who);
  }
  if (item.id) box.title = `Item · ${item.id}`;
}

export function renderScenarioOpening(scenario) {
  const box = $("#scenario-opening");
  if (!box) return;
  const opening = scenario && scenario.opening ? scenario.opening : null;
  const title = opening && (typeof opening === "object" && !Array.isArray(opening))
    ? opening.title : "";
  const rawLine = opening && typeof opening === "object" && !Array.isArray(opening)
    ? opening.line
    : opening;
  const line = Array.isArray(rawLine) ? rawLine.filter(Boolean).join(" ") : rawLine;
  if (!scenario || (!title && !line)) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  $("#scenario-opening-title").textContent = title || scenario.title || "Opening";
  $("#scenario-opening-line").textContent = line || "";
}
/* ---- memory → outfit card --------------------------------------------- */

let outfitReturnFocus = null;
let endingReturnFocus = null;

export function findScenarioBelief(data, holder, key) {
  if (!key) return null;
  const scenario = currentScenario(data);
  const beliefs = scenario && Array.isArray(scenario.beliefs) ? scenario.beliefs : [];
  const match = beliefs.find((belief) => belief && belief.key === key
    && (!belief.holder || asCastId(belief.holder) === holder || belief.holder === holder));
  if (match) return match;
  const stored = ((data && data.beliefs) || []).find((belief) => belief
    && (belief.proposition_key === key || belief.key === key)
    && (!belief.holder || belief.holder === holder));
  if (stored) return stored;
  const row = ((data && data.matrix) || []).find((item) => item.key === key);
  const cell = row && row.holders ? row.holders[holder] : null;
  return cell ? { proposition: cell.proposition, key, holder, confidence: cell.confidence, source: cell.source } : null;
}

export function openOverlay(modal) {
  if (!modal) return;
  closePhone();
  closeProfile();
  closeEnding();
  closeOutfit();
  modal.hidden = false;
  const app = $(".app");
  if (app) app.inert = true;
  document.body.classList.add("modal-open");
}

export function closeOverlay(modal) {
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  const app = $(".app");
  if (app) app.inert = false;
  document.body.classList.remove("modal-open");
}

export function openOutfit(id) {
  const cast = CAST[id];
  const data = state.data || {};
  const outfit = outfitFor(data, id);
  if (!cast || !outfit) return;
  const modal = $("#outfit-modal");
  if (!modal) return;
  outfitReturnFocus = document.activeElement;
  $("#outfit-title").textContent = `${firstName(cast.name)} · ${outfit.label || outfit.id || "outfit"}`;
  setArtWithFallback(
    $("#outfit-art"),
    [outfit.art, outfitArtFor(data, id), castArtFor(data, id), cast.scene, cast.portrait],
    `${cast.name} outfit`,
  );

  const belief = findScenarioBelief(data, id, outfit.source_belief);
  const steps = [];
  if (belief) {
    const source = belief.source
      || (belief.source_kind
        ? (belief.source_kind === "character"
          ? `character:${belief.source_id}`
          : belief.source_kind)
        : "");
    const meta = [
      belief.key || belief.proposition_key,
      belief.confidence !== undefined ? Number(belief.confidence).toFixed(2) : "",
      belief.visibility || "",
      source ? `source ${source}` : "",
    ].filter(Boolean).join(" · ");
    steps.push({ label: "source belief", title: belief.proposition || belief.key || "recorded belief", meta });
  } else if (outfit.source_belief) {
    steps.push({ label: "source belief", title: outfit.source_belief, meta: "not reported by the world yet" });
  }
  steps.push({
    label: "became",
    title: outfit.label || outfit.id || "outfit",
    meta: outfit.id ? `outfit · ${outfit.id}` : "outfit",
  });

  const chain = $("#outfit-chain");
  chain.replaceChildren();
  steps.forEach((step, index) => {
    const item = document.createElement("div");
    item.className = "outfit-step";
    const badge = document.createElement("span");
    badge.className = "outfit-step-index";
    badge.textContent = String(index + 1);
    const copy = document.createElement("div");
    const label = document.createElement("span");
    label.className = "eyebrow";
    label.textContent = step.label;
    const title = document.createElement("p");
    title.textContent = step.title;
    copy.append(label, title);
    if (step.meta) {
      const meta = document.createElement("span");
      meta.className = "outfit-step-meta";
      meta.textContent = step.meta;
      copy.appendChild(meta);
    }
    item.append(badge, copy);
    chain.appendChild(item);
  });
  const reason = $("#outfit-reason");
  reason.textContent = outfit.reason || "";
  reason.hidden = !outfit.reason;

  openOverlay(modal);
  $("#outfit-close").focus();
}

export function closeOutfit() {
  const modal = $("#outfit-modal");
  if (!modal || modal.hidden) return;
  closeOverlay(modal);
  if (outfitReturnFocus && typeof outfitReturnFocus.focus === "function") outfitReturnFocus.focus();
  outfitReturnFocus = null;
}
/* ---- ending card ------------------------------------------------------ */

export const ENDING_ART = {
  good: "/static/assets/scenes/ending-good.jpg",
  bad: "/static/assets/scenes/ending-bad.jpg",
};

export function normalizeEnding(raw) {
  if (!raw) return null;
  if (typeof raw === "string") {
    return {
      id: raw,
      label: raw,
      tone: /bad|fail/i.test(raw) ? "bad" : (/good|true/i.test(raw) ? "good" : "neutral"),
      evidence: [],
    };
  }
  const toneRaw = String(raw.tone || raw.kind || "").toLowerCase();
  const tone = toneRaw.includes("bad")
    ? "bad"
    : (toneRaw.includes("good") ? "good" : "neutral");
  return {
    id: raw.id || "",
    label: raw.label || raw.title || raw.id || "Ending",
    tone,
    evidence: Array.isArray(raw.evidence) ? raw.evidence : [],
  };
}

export function endingEvidenceList(evidence) {
  if (Array.isArray(evidence)) return evidence;
  if (evidence && typeof evidence === "object") {
    return Object.entries(evidence).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);
  }
  return evidence ? [String(evidence)] : [];
}

export function showEnding(rawEnding, evidence, options = {}) {
  const ending = normalizeEnding(rawEnding);
  if (!ending) return;
  const modal = $("#ending-modal");
  if (!modal) return;
  endingReturnFocus = document.activeElement;
  const items = endingEvidenceList(
    evidence && evidence.length ? evidence : (options.evidence || ending.evidence),
  );
  modal.dataset.tone = ending.tone;
  $("#ending-eyebrow").textContent = ending.tone === "good"
    ? "good end"
    : (ending.tone === "bad" ? "bad end" : "ending");
  $("#ending-title").textContent = ending.label || "The end";
  $("#ending-sub").textContent = options.subtitle
    || (ending.id ? `Scenario ending · ${ending.id}` : "The world has reached an ending card.");
  $("#ending-art-tag").textContent = ending.tone === "good"
    ? "Ending · good"
    : (ending.tone === "bad" ? "Ending · bad" : "Ending card");

  const data = state.data || {};
  const cast = CAST[state.selected] || CAST[ORDER[0]];
  const fallback = scenarioSceneArt(data) || (cast ? (cast.scene || cast.portrait) : null);
  const primary = ENDING_ART[ending.tone] || fallback;
  setArtWithFallback($("#ending-art"), [primary, fallback, cast && cast.portrait], `${ending.label} art`);

  const host = $("#ending-evidence");
  host.replaceChildren();
  items.forEach((entry) => {
    const chip = document.createElement("span");
    chip.className = "ending-evidence-chip";
    let text = "";
    let meta = "";
    if (entry && typeof entry === "object") {
      text = entry.label || entry.text || entry.proposition || entry.key || "";
      meta = entry.meta || entry.value || "";
      if (!text && entry.reason) text = entry.reason;
    } else {
      text = String(entry);
    }
    if (!text && !meta) return;
    chip.textContent = text || String(meta);
    if (text && meta) {
      const em = document.createElement("em");
      em.textContent = ` ${meta}`;
      chip.appendChild(em);
    }
    host.appendChild(chip);
  });
  if (!items.length) {
    const note = document.createElement("p");
    note.className = "tiny";
    note.textContent = "No evidence reported for this ending card.";
    host.appendChild(note);
  }

  state.ending = { ending, evidence: items };
  openOverlay(modal);
  $("#ending-close").focus();
}

export function closeEnding() {
  const modal = $("#ending-modal");
  if (!modal || modal.hidden) return;
  closeOverlay(modal);
  if (endingReturnFocus && typeof endingReturnFocus.focus === "function") endingReturnFocus.focus();
  endingReturnFocus = null;
}

export function scenarioEndingIsFork(scenario) {
  const id = String((scenario && scenario.id) || "").toLowerCase();
  return /^w5-(good|bad)/.test(id);
}

export async function evaluateEnding() {
  const buttons = [$("#scene-ending"), $("#worlds-evaluate")];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  state.worlds.status = "Evaluating the ending with the world engine…";
  const statusBox = $("#worlds-status");
  if (statusBox) statusBox.textContent = state.worlds.status;
  try {
    const result = await api("/api/endings/evaluate", { method: "POST", body: "{}" });
    const ending = (result && result.ending)
      || (result && result.scenario && result.scenario.ending)
      || (currentScenario(state.data) || {}).ending;
    const evidence = (result && result.evidence) || (ending && ending.evidence) || [];
    if (!ending) {
      state.worlds.status = "The world has not reported an ending for this scenario yet.";
      return;
    }
    state.worlds.status = "Ending card opened.";
    showEnding(ending, evidence);
  } catch (error) {
    state.worlds.status = `Ending not available yet: ${error.message}`;
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
    renderWorlds();
  }
}

export function renderStory(data) {
  data = data || {};
  const beat = currentBeat(data);
  if (state.beatId && beat && state.beatId !== beat.id) {
    state.turn = null;
    state.groupStatus = "";
  }
  state.beatId = beat ? beat.id : null;

  const absent = absentSet(data);
  const beatCast = sceneCharacters(data);
  const present = beatCast.filter((id) => !absent.has(id));
  // Keep a deliberately selected absent character selected so the portrait dims
  // and the consequence stays visible; otherwise follow the first present member.
  if (present.length && !present.includes(state.selected) && !absent.has(state.selected)) {
    state.selected = present[0];
    resetPhoneFor(state.selected);
  }
  if (!CAST[state.selected]) {
    state.selected = present[0] || ORDER[0];
    resetPhoneFor(state.selected);
  }
  const cast = CAST[state.selected] || CAST[ORDER[0]];
  const selectedAbsent = absent.has(cast.id);

  const scene = $(".scene");
  if (scene) {
    scene.style.setProperty("--scene-color", cast.color);
    scene.classList.toggle("is-absent", selectedAbsent);
  }
  const portrait = $("#scene-portrait");
  const backdrop = $("#scene-backdrop");
  const fallbackArt = [
    cast.scene,
    cast.full,
    `/static/assets/portraits/${cast.id}-bust.png`,
  ];
  if (portrait) {
    setArtWithFallback(portrait, [sceneArtFor(data, cast), ...fallbackArt], `${cast.name} portrait`);
    portrait.classList.toggle("is-absent", selectedAbsent);
  }
  if (backdrop) {
    setArtWithFallback(backdrop, [sceneBackdropFor(data, cast), ...fallbackArt], "");
  }
  const scenario = currentScenario(data);
  const takeInfo = currentTakeInfo(data);
  const takeScene = takeInfo.take ? takeInfo.scene : null;
  const opening = scenario && scenario.opening ? scenario.opening : null;
  $("#scene-name").textContent = firstName(cast.name);
  $("#scene-jp").textContent = cast.route;
  $("#scene-mood").textContent = selectedAbsent ? "absent · left the scene" : cast.mood;
  $("#scene-stamp").textContent = takeScene
    ? `SCENE ${takeInfo.index + 1}${takeInfo.count ? `/${takeInfo.count}` : ""} · ${String(takeScene.title || takeInfo.take.title || "TAKE").toUpperCase()}`
    : (scenario
      ? `SCENE · ${String(scenario.title || scenario.id || "SCENARIO").toUpperCase()}`
      : (beat ? `SCENE · ${beat.title.toUpperCase()}` : "SCENE · THE CAFÉ"));
  $("#scene-caption").textContent = takeScene
    ? `${formatTime(data.clock && data.clock.now)} · ${takeScene.place || scenario && scenario.place || takeInfo.take.title || "the scene"}`
    : (scenario
      ? `${formatTime(data.clock && data.clock.now)} · ${scenario.place || (opening && opening.title) || scenario.title || "the scene"}`
      : (beat
        ? `${formatTime(data.clock && data.clock.now)} · ${beat.place || beat.title}`
        : "18:30 · a Tuesday in late autumn"));

  renderScenarioItem(data);
  renderScenarioOpening(
    takeScene && (takeScene.opening || takeScene.title) ? takeScene : scenario,
  );
  renderStoryHud(data);
  renderTranscript(data, absent);
  renderChoices(beat, present);
  renderSayBar(beatCast, present, absent);
  renderBoundary(data, absent);
  renderSceneCast(beatCast, absent);
  renderBacklog(data);

  const endingButton = $("#scene-ending");
  if (endingButton) endingButton.hidden = !scenario;

  const status = $("#scene-status");
  if (status) {
    if (state.group.sending) {
      status.textContent = present.length
        ? `${nameList(present)} ${present.length === 1 ? "is" : "are"} listening…`
        : "The room is listening…";
    } else if (state.turn) {
      const total = (state.turn.lines || []).length;
      let line;
      if (!total) line = "The turn is still forming…";
      else if (state.turn.done) line = `Turn complete · ${total} beat${total === 1 ? "" : "s"}.`;
      else line = `Beat ${state.turn.index} of ${total} · press Next to play the next beat.`;
      if (state.turn.transport === "staged") {
        line += " Whisper transport: staged — delivered locally, not through a private room.";
      } else if (state.turn.userPrivate && !state.turn.transport) {
        line += " Whisper · private lines stay in your log.";
      }
      status.textContent = [line, state.groupStatus].filter(Boolean).join(" ");
    } else {
      status.textContent = state.groupStatus || "";
    }
  }

  const next = $("#scene-next");
  if (next) next.disabled = state.group.sending || state.safety.paused;

  renderSafetyNotice();
  renderHero(data);
  renderCast(data);
  renderArc(data);
  renderPhone(data);
}
/* ---- story HUD + safety ----------------------------------------------- */

export function renderStoryHud(data) {
  data = data || {};
  const hud = $("#story-hud");
  if (!hud) return;
  const info = currentTakeInfo(data);
  const scenario = currentScenario(data);
  const beat = currentBeat(data);
  const scene = info.take ? info.scene : null;
  const take = info.take;
  const source = takeSource(data);

  const title = (scene && (scene.title || scene.name))
    || (take && (take.title || take.id))
    || (scenario && (scenario.title || scenario.id))
    || (beat && beat.title)
    || "The café";
  const place = (scene && scene.place)
    || (scenario && scenario.place)
    || (beat && beat.place)
    || "a Tuesday in late autumn";

  $("#hud-kicker").textContent = take
    ? `take · scene ${info.index + 1}${info.count ? ` of ${info.count}` : ""}`
    : (scenario ? "scenario" : "base canon");
  $("#hud-title").textContent = title;
  $("#hud-place").textContent = place;

  const chip = $("#hud-take");
  if (chip) {
    chip.hidden = !take;
    chip.textContent = take
      ? `${take.title || take.id || "take"} · ${info.index + 1}${info.count ? `/${info.count}` : ""}`
      : "";
    chip.title = take && take.id ? `Active take: ${take.id}` : "";
  }

  const action = latestActionMode(source);
  const actionChip = $("#hud-action");
  if (actionChip) {
    actionChip.hidden = !action;
    actionChip.textContent = action;
    actionChip.title = "Action mode for the latest turn";
  }

  const turn = inferredTurnNumber(source);
  $("#hud-turn").textContent = turn !== null ? `Turn ${turn}` : "Turn 0";

  const clock = data.clock || {};
  $("#hud-clock").textContent = formatTime(clock.now) || "--:--";
  const mode = clockScaleLabel(clock);
  const modeChip = $("#hud-mode");
  modeChip.textContent = mode;
  modeChip.classList.toggle("is-real", mode.startsWith("REAL"));
  modeChip.title = mode.startsWith("REAL")
    ? `Real time · story clock runs ${scaleFactor(clock.scale)} wall time`
    : "Mock time · the story waits for you";

  const revision = stateRevision(source);
  const revChip = $("#hud-revision");
  if (revChip) {
    revChip.hidden = revision === null;
    revChip.textContent = revision === null ? "" : `rev ${revision}`;
    revChip.title = "State revision — every turn increments it";
  }
}

export function renderSafetyNotice() {
  const box = $("#scene-pause");
  if (!box) return;
  box.hidden = !state.safety.paused;
}

export function renderSafety() {
  const badge = $("#safety-badge");
  const button = $("#safety-toggle");
  const status = $("#safety-status");
  if (badge) {
    badge.textContent = state.safety.paused ? "Paused" : "Running";
    badge.classList.toggle("is-paused", state.safety.paused);
    badge.classList.toggle("is-running", !state.safety.paused);
  }
  if (button) {
    button.textContent = state.safety.paused ? "Resume scene" : "Pause scene";
    button.disabled = state.safety.busy;
    button.setAttribute("aria-pressed", state.safety.paused ? "true" : "false");
    button.classList.toggle("is-paused", state.safety.paused);
  }
  if (status) {
    status.textContent = state.safety.status
      || (state.safety.paused
        ? "Paused. New scene and DM lines are on hold until you resume."
        : "New lines are allowed.");
  }
  renderSafetyNotice();
}

export async function setSafety(paused) {
  if (state.safety.busy) return;
  const target = Boolean(paused);
  state.safety.busy = true;
  state.safety.status = target ? "Pausing the scene…" : "Resuming the scene…";
  renderSafety();
  try {
    const result = await api("/api/safety/pause", {
      method: "POST",
      body: JSON.stringify({ paused: target }),
    });
    const value = result && Object.prototype.hasOwnProperty.call(result, "paused")
      ? Boolean(result.paused)
      : target;
    state.safety.paused = value;
    state.safety.ready = true;
    state.safety.status = value
      ? "Paused. New scene and DM lines are on hold until you resume."
      : "Running. New lines are allowed.";
  } catch (error) {
    state.safety.status = `Pause control unavailable: ${error.message}`;
  } finally {
    state.safety.busy = false;
    renderSafety();
    if (state.data) {
      renderStory(state.data);
      renderTakes();
    }
    if (state.view === "studio") loadStudio(true);
  }
}

export function syncSafety(data) {
  if (!data) return;
  let value = null;
  if (data.safety && typeof data.safety === "object"
    && Object.prototype.hasOwnProperty.call(data.safety, "paused")) {
    value = Boolean(data.safety.paused);
  } else if (Object.prototype.hasOwnProperty.call(data, "paused")) {
    value = Boolean(data.paused);
  } else if (data.meta && Object.prototype.hasOwnProperty.call(data.meta, "paused")) {
    value = Boolean(data.meta.paused);
  }
  if (value !== null && value !== state.safety.paused) {
    state.safety.paused = value;
    state.safety.ready = true;
    state.safety.status = value
      ? "Paused. New scene and DM lines are on hold until you resume."
      : "Running. New lines are allowed.";
  }
}
export function isSpeechBeat(entry) {
  return SPEECH_MODES.has(entry.mode) && !entry.chorus && !entry.silent && !entry.boundary;
}

export function optimisticEntryKey(turn, position) {
  return `opt-${turn.id}-${position}`;
}

export function sameOptimisticBeat(entry, turn) {
  if (!turn || turn.source !== "optimistic") return false;
  if (entry.turnId && entry.turnId === turn.id) return true;
  if (entry.boundary && turn.boundary) {
    const created = entry.ts ? Date.parse(entry.ts) : NaN;
    if (!Number.isFinite(created) || created >= (turn.startedAt || 0) - 10000) return true;
  }
  const ts = entry.ts ? Date.parse(entry.ts) : NaN;
  if (Number.isFinite(ts) && turn.startedAt && ts < turn.startedAt - 10000) return false;
  const key = normalizeText(entry.text);
  if (entry.isUser) return key === normalizeText(turn.userText);
  return (turn.lines || []).some((line) =>
    normalizeText(line.text) === key && (!entry.castId || line.character === entry.castId));
}

export function hiddenByPlayback(entry, turn) {
  if (!turn || turn.source !== "events") return false;
  if (entry.turnId !== turn.id || entry.isUser) return false;
  return entry.beatIndex >= turn.index;
}

export function transcriptSignature(rows, turn, absent) {
  const rowSig = rows.map((entry) => [
    entry.key, entry.mode || "", entry.private ? "p" : "", entry.boundary ? "b" : "",
    entry.silent ? "s" : "", entry.chorus ? "c" : "", entry.direction ? "d" : "",
    entry.castId || "", entry.text ? entry.text.length : 0,
  ].join(":")).join("|");
  const lineSig = turn
    ? (turn.lines || []).map((line) =>
      `${line.character || line.speaker || ""}:${line.mode}:${line.text.length}:${line.text.slice(0, 16)}`).join("~")
    : "";
  const turnSig = turn
    ? `${turn.id}:${turn.source}:${turn.index}:${turn.done ? 1 : 0}:${turn.boundary ? 1 : 0}:${turn.transport || ""}`
    : "-";
  return `${rowSig}#${turnSig}#${lineSig}#${[...absent].sort().join(",")}`;
}

export function currentBeatKey() {
  const turn = state.turn;
  if (!turn || turn.done || turn.index <= 0) return null;
  const line = (turn.lines || [])[turn.index - 1];
  if (!line || !isSpeechBeat(line)) return null;
  if (turn.source === "optimistic") return optimisticEntryKey(turn, turn.index - 1);
  return line.key || null;
}

export function avatarElement(entry, absent) {
  const span = document.createElement("span");
  span.className = "speaker-avatar";
  if (!entry.castId) {
    span.classList.add(entry.isUser ? "is-user" : "is-room");
    span.textContent = entry.isUser ? "Y" : (entry.boundary ? "!" : "·");
    return span;
  }
  const cast = CAST[entry.castId];
  const img = document.createElement("img");
  img.alt = "";
  img.loading = "lazy";
  img.onerror = () => {
    img.onerror = null;
    img.src = `/static/assets/portraits/${entry.castId}-avatar.svg`;
  };
  img.src = cast ? cast.avatar : `/static/assets/portraits/${entry.castId}-avatar.svg`;
  if (absent.has(entry.castId) || entry.silent) span.classList.add("is-dim");
  span.appendChild(img);
  return span;
}

export function turnChip(label, kind, title) {
  const chip = document.createElement("span");
  chip.className = `turn-chip ${kind || ""}`.trim();
  chip.textContent = label;
  if (title) chip.title = title;
  return chip;
}

export function speakerPlate(entry, absent) {
  const wrap = document.createElement("div");
  wrap.className = "turn-speaker";
  wrap.appendChild(avatarElement(entry, absent));
  const plate = document.createElement("span");
  plate.className = "speaker-plate";
  const name = document.createElement("span");
  name.className = "speaker-name";
  name.textContent = entry.isUser ? "You" : firstName(entry.speaker || "The room");
  plate.appendChild(name);
  wrap.appendChild(plate);
  if (entry.expression) {
    const expression = document.createElement("span");
    expression.className = "turn-expression";
    expression.textContent = entry.expression;
    wrap.appendChild(expression);
  }
  if (entry.private) {
    const lock = document.createElement("span");
    lock.className = "turn-lock";
    lock.textContent = "Private";
    lock.setAttribute("aria-label", "Private line, visible only to you");
    wrap.appendChild(lock);
  }
  if (entry.boundary) {
    const tag = document.createElement("span");
    tag.className = "turn-tag";
    tag.textContent = "Boundary";
    wrap.appendChild(tag);
  }
  if (entry.authored) {
    wrap.appendChild(turnChip(
      "authored",
      "is-authored",
      "Authored fallback line — this is a normal scene line, not an error.",
    ));
  }
  if (entry.actionMode) {
    wrap.appendChild(turnChip(entry.actionMode, "is-action", "Action mode"));
  }
  if (entry.response) {
    wrap.appendChild(turnChip(entry.response, `is-response is-${entry.response}`, "Character response"));
  }
  return wrap;
}

export function entryRow(entry, absent, activeKey) {
  const row = document.createElement("div");
  row.className = "turn-entry";
  row.dataset.key = entry.key;

  if (entry.direction) {
    row.classList.add("turn-direction");
    const label = document.createElement("span");
    label.className = "turn-direction-label";
    label.textContent = "stage direction";
    const text = document.createElement("p");
    text.className = "turn-text";
    text.textContent = entry.text;
    row.append(label, text);
    if (entry.actionMode) {
      row.appendChild(turnChip(entry.actionMode, "is-action", "Action mode for this turn"));
    }
    return row;
  }

  if (entry.isUser) row.classList.add("is-user");
  if (entry.boundary) row.classList.add("is-boundary");
  if (entry.private) row.classList.add("is-private");
  if (entry.silent) row.classList.add("is-caption", "is-silence");
  if (!entry.boundary && (entry.mode === "action" || entry.mode === "reaction")) {
    row.classList.add("is-caption", `is-${entry.mode}`);
  }

  row.appendChild(speakerPlate(entry, absent));

  if (entry.boundary) {
    const body = document.createElement("div");
    body.className = "turn-boundary-body";
    const title = document.createElement("strong");
    title.textContent = "A line was crossed";
    const text = document.createElement("p");
    text.className = "turn-text";
    text.textContent = entry.text || "The scene cuts on the consequence.";
    const note = document.createElement("span");
    note.className = "turn-note";
    note.textContent = "No act details are shown. Only the consequence is.";
    body.append(title, text, note);
    row.appendChild(body);
    return row;
  }

  const text = document.createElement("p");
  text.className = "turn-text";
  text.textContent = entry.text;
  if (entry.mode === "action" || entry.mode === "reaction" || entry.silent) {
    text.classList.add("is-italic");
  }
  if (entry.key === activeKey) {
    row.classList.add("is-current");
    typeLine(text, entry.text, `beat:${entry.key}`);
  } else {
    text.classList.add("is-done");
  }
  row.appendChild(text);
  if (entry.mode === "reply") {
    const replyTarget = asCastId(entry.target);
    if (replyTarget && CAST[replyTarget]) {
      const note = document.createElement("span");
      note.className = "turn-note";
      note.textContent = `↳ reply to ${firstNameOf(replyTarget)}`;
      row.appendChild(note);
    }
  }
  if (entry.private) {
    const note = document.createElement("span");
    note.className = "turn-note";
    if (entry.isUser) {
      const target = entry.target && CAST[entry.target] ? firstNameOf(entry.target) : "one character";
      note.textContent = `Whispered to ${target} · visible only in your log.`;
    } else {
      note.textContent = "Private line · visible only in your log.";
    }
    row.appendChild(note);
  }
  return row;
}

export function chorusRow(group, absent) {
  const row = document.createElement("div");
  row.className = "turn-entry is-chorus";
  row.dataset.key = group[0].key;
  const names = document.createElement("div");
  names.className = "chorus-names";
  group.forEach((entry) => {
    const line = document.createElement("div");
    line.className = "chorus-name";
    line.appendChild(avatarElement(entry, absent));
    const plate = document.createElement("span");
    plate.className = "speaker-plate";
    const name = document.createElement("span");
    name.className = "speaker-name";
    name.textContent = firstName(entry.speaker);
    plate.appendChild(name);
    line.appendChild(plate);
    if (entry.authored) {
      line.appendChild(turnChip("authored", "is-authored", "Authored fallback line — normal scene text, not an error."));
    }
    if (entry.actionMode) {
      line.appendChild(turnChip(entry.actionMode, "is-action", "Action mode"));
    }
    if (entry.response) {
      line.appendChild(turnChip(entry.response, `is-response is-${entry.response}`, "Character response"));
    }
    names.appendChild(line);
  });
  const body = document.createElement("div");
  body.className = "chorus-body";
  group.forEach((entry) => {
    const text = document.createElement("p");
    text.className = "turn-text";
    text.textContent = entry.text;
    body.appendChild(text);
  });
  row.append(names, body);
  return row;
}
export function renderTranscript(data, absent) {
  const host = $("#turn-log");
  if (!host) return;
  const turn = state.turn;
  let entries = buildEventEntries(data);
  if (turn && turn.source === "optimistic") {
    entries = entries.filter((entry) => !sameOptimisticBeat(entry, turn));
  }
  if (turn && turn.userText) {
    const userKey = normalizeText(turn.userText);
    entries = entries.filter(
      (entry) => !(entry.isUser && normalizeText(entry.text) === userKey)
    );
  }
  const rows = entries.filter((entry) => !hiddenByPlayback(entry, turn));

  if (turn && turn.source === "optimistic") {
    if (turn.userText && !turn.userHidden) {
      rows.push({
        key: `user-${turn.id}`,
        isUser: true,
        mode: turn.userPrivate ? "whisper" : "speech",
        speaker: "You",
        text: turn.userText,
        private: Boolean(turn.userPrivate),
        target: (turn.plan && turn.plan.target) || turn.whisperTo || null,
        boundary: false,
        chorus: false,
        silent: false,
        turnId: turn.id,
      });
    }
    const direction = directionText(turn);
    if (direction) {
      rows.push({
        key: `dir-${turn.id}`,
        direction: true,
        text: direction,
        actionMode: normalizeActionMode(
          turn.actionMode
          || (turn.plan && (turn.plan.action_mode || turn.plan.actionMode)),
        ),
      });
    }
    if (turn.boundary) {
      rows.push({
        key: `boundary-${turn.id}`,
        mode: "boundary",
        boundary: true,
        speaker: "Boundary",
        text: turn.boundaryText
          || `A physical boundary was crossed with ${turn.boundaryTarget ? firstNameOf(turn.boundaryTarget) : "another character"}. The act is cut; only the consequence is shown.`,
        private: false,
        chorus: false,
        silent: false,
        turnId: turn.id,
      });
    }
    (turn.lines || []).forEach((line, position) => {
      if (!turn.done && position >= turn.index) return;
      rows.push({
        ...line,
        key: optimisticEntryKey(turn, position),
        castId: line.castId || (line.character && CAST[line.character] ? line.character : null),
        isUser: false,
        boundary: false,
        turnId: turn.id,
        position,
      });
    });
  }

  const sig = transcriptSignature(rows, turn, absent);
  if (host.dataset.sig === sig) return;
  host.dataset.sig = sig;
  cancelTyping();
  const nearBottom = host.scrollHeight - host.scrollTop - host.clientHeight < 72;
  const activeKey = currentBeatKey();
  host.replaceChildren();

  let index = 0;
  while (index < rows.length) {
    const entry = rows[index];
    if (entry.chorus && !entry.isUser) {
      const group = [entry];
      let next = index + 1;
      while (next < rows.length && rows[next].chorus && !rows[next].isUser
        && rows[next].turnId === entry.turnId) {
        group.push(rows[next]);
        next += 1;
      }
      host.appendChild(chorusRow(group, absent));
      index = next;
      continue;
    }
    host.appendChild(entryRow(entry, absent, activeKey));
    index += 1;
  }
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "turn-empty";
    empty.textContent = "The scene is quiet. Say something to the room.";
    host.appendChild(empty);
  }
  if (nearBottom || activeKey) host.scrollTop = host.scrollHeight;
}

export function renderBacklog(data) {
  const rail = $("#scene-rail");
  if (!rail) return;
  const entries = buildEventEntries(data)
    .filter((entry) => !entry.boundary && !entry.private && entry.text)
    .slice(-8);
  const sig = entries.map((entry) => entry.key).join(",");
  if (rail.dataset.sig === sig) return;
  rail.dataset.sig = sig;
  rail.replaceChildren();
  entries.forEach((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-chip";
    button.textContent = `${entry.isUser ? "You" : firstName(entry.speaker)}: ${entry.text}`;
    button.title = entry.text;
    button.addEventListener("click", () => {
      if (entry.castId) {
        state.selected = entry.castId;
        resetPhoneFor(entry.castId);
      }
      if (state.data) renderStory(state.data);
      const target = document.querySelector(`.turn-entry[data-key="${entry.key}"]`);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "nearest" });
        target.classList.add("is-flash");
        setTimeout(() => target.classList.remove("is-flash"), 1200);
      }
    });
    rail.appendChild(button);
  });
}

export function renderSceneCast(ids, absent) {
  const row = $("#scene-cast");
  if (!row) return;
  const list = ids.length ? ids : ORDER.slice();
  const outfit = outfitFor(state.data, state.selected);
  const sig = `${list.join(",")}|${state.selected}|${[...absent].sort().join(",")}|${outfit ? `${outfit.id || ""}:${outfit.label || ""}` : ""}`;
  if (row.dataset.sig === sig) return;
  row.dataset.sig = sig;
  row.replaceChildren();
  list.forEach((id) => {
    const cast = CAST[id];
    if (!cast) return;
    const isAbsent = absent.has(id);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `scene-member${state.selected === id ? " is-active" : ""}${isAbsent ? " is-absent" : ""}`;
    button.title = isAbsent ? `${cast.name} — absent (left the scene)` : `${cast.name} — ${cast.role}`;
    button.setAttribute("aria-label", `${cast.name}, ${isAbsent ? "absent" : cast.role}`);
    const img = document.createElement("img");
    img.src = cast.avatar;
    img.alt = "";
    img.onerror = () => {
      img.onerror = null;
      img.src = `/static/assets/portraits/${id}-avatar.svg`;
    };
    button.appendChild(img);
    const label = document.createElement("span");
    label.textContent = firstName(cast.name);
    button.appendChild(label);
    if (isAbsent) {
      const tag = document.createElement("span");
      tag.className = "scene-member-tag";
      tag.textContent = "absent";
      button.appendChild(tag);
    }
    button.addEventListener("click", () => selectCast(id));
    row.appendChild(button);
  });
  if (outfit) {
    const badge = document.createElement("button");
    badge.type = "button";
    badge.className = "scene-outfit";
    badge.title = outfit.reason
      ? `Outfit: ${outfit.label || outfit.id} — ${outfit.reason}`
      : `Outfit: ${outfit.label || outfit.id}`;
    badge.setAttribute("aria-label", `Open the memory chain for ${firstNameOf(state.selected)}'s ${outfit.label || outfit.id}`);
    const label = document.createElement("span");
    label.className = "scene-outfit-label";
    label.textContent = "Outfit";
    const name = document.createElement("strong");
    name.textContent = outfit.label || outfit.id || "outfit";
    badge.append(label, name);
    badge.addEventListener("click", (event) => {
      event.stopPropagation();
      openOutfit(state.selected);
    });
    row.appendChild(badge);
  }
}

export function renderChoices(beat, present) {
  const box = $("#scene-choices");
  if (!box) return;
  const scenario = currentScenario(state.data);
  const takeInfo = currentTakeInfo(state.data);
  const takeScene = takeInfo.take ? takeInfo.scene : null;
  const opening = scenario && scenario.opening ? scenario.opening : null;
  const openingChoices = opening && Array.isArray(opening.choices)
    ? opening.choices.filter((choice) => typeof choice === "string" && choice.trim())
    : [];
  const takeChoices = takeScene && Array.isArray(takeScene.choices)
    ? takeScene.choices.filter((choice) => typeof choice === "string" && choice.trim())
    : [];
  const choices = takeChoices.length
    ? takeChoices
    : (openingChoices.length ? openingChoices : ((beat && beat.choices) || []));
  const sig = `${takeScene ? (takeScene.id || takeInfo.index) : ""}|${scenario ? scenario.id : ""}|${beat ? beat.id : ""}|${state.group.sending}|${state.safety.paused}|${present.join(",")}|${choices.join("|")}`;
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.replaceChildren();
  choices.forEach((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-choice";
    button.textContent = text;
    button.disabled = state.group.sending || state.safety.paused || !present.length;
    button.addEventListener("click", () => sendScene(text));
    box.appendChild(button);
  });
  box.hidden = choices.length === 0;
}

export function renderSayBar(beatCast, present, absent) {
  const toggle = $("#whisper-toggle");
  if (toggle) toggle.checked = Boolean(state.whisper);
  const form = $("#scene-say-form");
  if (form) form.classList.toggle("is-whisper", Boolean(state.whisper));

  const select = $("#whisper-target");
  if (select) {
    const ids = beatCast.length ? beatCast : ORDER.slice();
    const sig = `${ids.join(",")}|${[...absent].sort().join(",")}`;
    if (select.dataset.sig !== sig) {
      select.dataset.sig = sig;
      const previous = state.whisperTarget || select.value;
      select.replaceChildren();
      ids.forEach((id) => {
        const cast = CAST[id];
        if (!cast) return;
        const option = document.createElement("option");
        option.value = id;
        option.textContent = absent.has(id) ? `${firstName(cast.name)} (absent)` : firstName(cast.name);
        option.disabled = absent.has(id);
        select.appendChild(option);
      });
      const available = ids.filter((id) => CAST[id] && !absent.has(id));
      const chosen = available.includes(previous)
        ? previous
        : (available.includes(state.selected) ? state.selected : (available[0] || ""));
      state.whisperTarget = chosen || null;
    }
    if (state.whisperTarget && CAST[state.whisperTarget] && !absent.has(state.whisperTarget)) {
      select.value = state.whisperTarget;
    }
    select.disabled = !state.whisper || state.safety.paused || !present.length;
  }

  const input = $("#scene-say-input");
  if (input) {
    input.disabled = state.group.sending || state.safety.paused || !present.length;
    const target = state.whisperTarget ? firstNameOf(state.whisperTarget) : "them";
    input.placeholder = state.safety.paused
      ? "Scene paused — resume in Studio"
      : (state.whisper
        ? `Whisper to ${target}…`
        : (present.length > 1
          ? "Say something to the room…"
          : `Say something to ${present.length ? firstName(CAST[present[0]].name) : "them"}…`));
  }
  const send = $("#scene-say-send");
  if (send) send.disabled = state.group.sending || state.safety.paused || !present.length;
}

export function renderBoundary(data, absent) {
  const box = $("#scene-boundary");
  const scene = $(".scene");
  if (!box) return;
  const event = latestBoundary(data);
  const optimistic = Boolean(state.turn && state.turn.boundary);
  if (!event && !optimistic) {
    box.hidden = true;
    box.replaceChildren();
    if (scene) scene.classList.remove("has-boundary");
    return;
  }
  let target = null;
  if (event) {
    const meta = eventMeta(event);
    target = meta.target || (event.participants || []).find((id) => String(id).toLowerCase() !== "user");
  }
  if (!target && state.turn && state.turn.boundaryTarget) target = state.turn.boundaryTarget;
  const id = asCastId(target);
  const name = id && CAST[id] ? firstNameOf(id) : "";
  box.hidden = false;
  box.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = "A boundary was crossed";
  const text = document.createElement("p");
  text.textContent = name
    ? `${name} has left the scene. The act is cut; only the consequence and the room's reaction are shown.`
    : "A physical boundary was crossed. The act is cut; only the consequence and the room's reaction are shown.";
  const note = document.createElement("span");
  note.className = "turn-note";
  note.textContent = "Wording stays non-explicit. The scene continues from the consequence.";
  box.append(title, text, note);
  if (scene) scene.classList.toggle("has-boundary", Boolean(id && absent.has(id)));
}
export async function sendScene(text, options = {}) {
  text = String(text || "").trim();
  if (!text || state.group.sending) return;
  if (state.safety.paused) {
    state.groupStatus = "The scene is paused. New lines are on hold — resume in Studio when you choose.";
    renderStory(state.data);
    return;
  }
  const whisper = Boolean(options.whisper);
  const data = state.data || {};
  const absent = absentSet(data);
  const present = sceneCharacters(data).filter((id) => !absent.has(id));
  if (!present.length) {
    state.groupStatus = "No one is present. Advance the beat or reset the demo.";
    renderStory(state.data);
    return;
  }
  const target = whisper
    ? (CAST[options.to] ? options.to : (present.includes(state.whisperTarget) ? state.whisperTarget : present[0]))
    : null;
  if (whisper && (!target || absent.has(target))) {
    state.groupStatus = "Pick a present character to whisper to.";
    renderStory(state.data);
    return;
  }

  const startedAt = Date.now();
  state.group.sending = true;
  state.groupStatus = "";
  state.turn = {
    id: `local-${startedAt}`,
    source: "optimistic",
    plan: whisper ? { whisper: true, target } : {},
    userText: text,
    userPrivate: whisper,
    whisperTo: target,
    lines: [],
    index: 0,
    done: false,
    startedAt,
    transport: null,
    boundary: false,
    boundaryTarget: null,
  };
  renderStory(state.data);

  try {
    const result = whisper
      ? await api("/api/group/whisper", {
        method: "POST",
        body: JSON.stringify({ to: target, message: text, timeout: 50 }),
      })
      : await api("/api/group/say", {
        method: "POST",
        body: JSON.stringify({ message: text, characters: present, timeout: 50 }),
      });
    state.group.sending = false;
    const turn = result && result.turn ? result.turn : {};
    state.turn.id = turn.id || state.turn.id;
    state.turn.plan = turn.plan || state.turn.plan;
    state.turn.actionMode = normalizeActionMode(
      (state.turn.plan && (state.turn.plan.action_mode || state.turn.plan.actionMode))
      || (turn.action_mode || turn.actionMode),
    );
    state.turn.lines = extractTurnLines(result, whisper, state.turn.plan);
    state.turn.lines.forEach((line) => { line.turnId = state.turn.id; });
    // Show the returned beats immediately. The transcript is the performance; hiding
    // the first answer behind Next made a finished model call look like a stall.
    state.turn.index = state.turn.lines.length;
    state.turn.done = true;
    state.turn.transport = (result && result.transport) || null;
    if (state.takes.current) state.takes.changed = true;

    const boundaryValue = (result && result.boundary)
      || turn.boundary
      || (turn.plan && turn.plan.boundary);
    state.turn.boundary = Boolean(boundaryValue && boundaryValue !== "none");
    state.turn.boundaryTarget = (result && result.boundary_target)
      || (turn.plan && (turn.plan.target || turn.plan.primary))
      || (result && result.boundary && Array.isArray(result.boundary.participants)
        ? result.boundary.participants[0] : null)
      || null;

    if (state.turn.boundary) {
      // The act itself is cut from the log; only the consequence remains.
      state.turn.userHidden = true;
      if (state.turn.boundaryTarget && CAST[state.turn.boundaryTarget]) {
        state.selected = state.turn.boundaryTarget;
        resetPhoneFor(state.selected);
      }
    }
    if (state.turn.boundary && state.turn.boundaryTarget) {
      state.turn.boundaryText = `A physical boundary was crossed with ${firstNameOf(state.turn.boundaryTarget)}. The act is cut; only the consequence is shown.`;
    }
    if (state.turn.boundary) {
      // A boundary cuts the act; show the refusal and witnesses immediately.
      state.turn.index = state.turn.lines.length;
      state.turn.done = true;
    }
    if (whisper) {
      // The staged label is rendered from turn.transport in renderStory; keep
      // groupStatus for a verified non-staged transport only.
      state.groupStatus = state.turn.transport && state.turn.transport !== "staged"
        ? `Whisper transport: ${state.turn.transport}.`
        : "";
    } else if (result && result.missing && result.missing.length) {
      state.groupStatus = `No reply yet from ${nameList(result.missing)}. The room may be quiet.`;
    }
    await refresh();
  } catch (error) {
    state.group.sending = false;
    state.turn = null;
    if (error.status === 423) {
      state.safety.paused = true;
      state.safety.ready = true;
      state.safety.status = "Paused. New scene and DM lines are on hold until you resume.";
      state.groupStatus = "The scene is paused. New lines are on hold — resume in Studio when you choose.";
      renderSafety();
    } else {
      state.groupStatus = `The room didn't answer: ${error.message}`;
    }
    renderStory(state.data);
  } finally {
    state.group.sending = false;
    if (state.data) renderStory(state.data);
  }
}
export function renderHero(data) {
  const row = (data.matrix || []).find((item) => item.key === SECRET_KEY);
  const holders = row ? Object.entries(row.holders) : [];
  const names = Object.fromEntries((data.characters || []).map((c) => [c.id, firstName(c.name)]));
  $("#hero-value").textContent = String(holders.length);
  if (!holders.length) {
    $("#hero-sub").textContent = "Tell Alice a secret to begin.";
  } else {
    $("#hero-sub").textContent = holders
      .map(([id, cell]) => `${names[id] || id} ${Number(cell.confidence).toFixed(2)} (${sourceLabel(cell)})`)
      .join(" · ");
  }
  const host = $("#hero-holders");
  host.replaceChildren();
  holders.forEach(([id, cell]) => {
    const cast = CAST[id];
    if (!cast) return;
    const chip = document.createElement("span");
    chip.className = "holder-chip";
    const img = document.createElement("img");
    img.onerror = () => {
      img.onerror = null;
      img.src = `/static/assets/portraits/${cast.id}-avatar.svg`;
    };
    img.src = cast.avatar;
    img.alt = "";
    chip.appendChild(img);
    const name = document.createElement("b");
    name.textContent = firstName(cast.name);
    chip.appendChild(name);
    const conf = document.createElement("em");
    conf.textContent = Number(cell.confidence).toFixed(2);
    chip.appendChild(conf);
    host.appendChild(chip);
  });
  $$(".secret-hearts span").forEach((heart, index) => {
    heart.textContent = heartGlyph(index < holders.length);
  });
}
export function makeCastAction(label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "cast-action";
  button.textContent = label;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick();
  });
  return button;
}

export function renderCast(data) {
  const grid = $("#cast-grid");
  const sig = ORDER.map((id) => `${id}:${Math.round(affinityFor(data, id) * 5)}:${isFriend(data, id)}:${outfitArtFor(data, id) || castArtFor(data, id) || ""}`).join("|") + `|${state.selected}`;
  if (grid.dataset.sig === sig) return;
  grid.dataset.sig = sig;
  grid.replaceChildren();
  ORDER.forEach((id) => {
    const cast = CAST[id];
    const card = document.createElement("article");
    card.className = "cast-card" + (state.selected === id ? " is-selected" : "");
    card.setAttribute("role", "group");
    card.setAttribute("aria-label", `${cast.name} character card`);
    card.addEventListener("click", () => selectCast(id));

    const art = document.createElement("div");
    art.className = "cast-art";
    const img = document.createElement("img");
    setArtWithFallback(
      img,
      [outfitArtFor(data, id), castArtFor(data, id), cast.portrait, `/static/assets/portraits/${cast.id}.svg`],
      `${cast.name} portrait`,
    );
    img.loading = "lazy";
    art.appendChild(img);
    const role = document.createElement("span");
    role.className = "cast-role";
    role.textContent = cast.role;
    art.appendChild(role);
    card.appendChild(art);

    const info = document.createElement("div");
    info.className = "cast-info";
    const name = document.createElement("div");
    name.className = "cast-name";
    name.textContent = cast.name;
    info.appendChild(name);
    const jp = document.createElement("div");
    jp.className = "cast-jp";
    jp.textContent = cast.route;
    info.appendChild(jp);
    const tagline = document.createElement("p");
    tagline.className = "cast-tagline";
    tagline.textContent = cast.tagline;
    info.appendChild(tagline);
    const intro = document.createElement("p");
    intro.className = "cast-intro";
    intro.textContent = cast.intro;
    intro.title = cast.intro;
    info.appendChild(intro);

    const traits = document.createElement("div");
    traits.className = "cast-traits";
    cast.traits.forEach((trait) => {
      const chip = document.createElement("span");
      chip.className = "cast-trait";
      chip.textContent = trait;
      traits.appendChild(chip);
    });
    info.appendChild(traits);

    const foot = document.createElement("div");
    foot.className = "cast-foot";
    const hearts = document.createElement("span");
    hearts.className = "cast-hearts";
    const affinity = affinityFor(data, id);
    const filled = Math.round(affinity * 5);
    hearts.textContent = heartStrip(filled);
    hearts.setAttribute("aria-label", `${filled} of 5 affinity`);
    foot.appendChild(hearts);

    const chat = document.createElement("button");
    chat.type = "button";
    chat.className = "cast-dm";
    chat.textContent = isFriend(data, id) ? "Chat" : "Add friend";
    chat.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!isFriend(state.data, id)) {
        addFriend(id);
        return;
      }
      openPhone(id);
    });
    foot.appendChild(chat);

    const actions = document.createElement("div");
    actions.className = "cast-actions";
    actions.appendChild(makeCastAction("Story", () => selectCast(id)));
    actions.appendChild(makeCastAction("Profile", () => openProfile(id)));
    foot.appendChild(actions);
    info.appendChild(foot);
    card.appendChild(info);
    grid.appendChild(card);
  });
}
/* ---- authored arc ----------------------------------------------------- */

export function renderArc(data) {
  const canon = data.canon || {};
  const beats = canon.beats || [];
  const branchEvent = data.branch || [...(data.events || [])].reverse().find((event) => event.kind === "branch");
  $("#arc-act").textContent = canon.act || "Act I — The Secret";

  let branchLabel = "the café is open";
  if (branchEvent) {
    branchLabel = branchEvent.summary
      .replace(/^Branch:\s*/, "")
      .split(" — ")[0] || "act complete";
  }
  const branchNode = $("#arc-branch");
  branchNode.textContent = branchLabel;
  branchNode.title = branchEvent ? branchEvent.summary : "The authored café beat has not run yet.";

  const done = new Set(data.done_beats || []);
  if (!done.size) {
    (data.events || [])
      .filter((event) => event.kind === "beat")
      .forEach((event) => {
        const match = String(event.summary || "").match(/^Beat:\s*([a-z-]+)/i);
        if (match) done.add(match[1]);
      });
    if (branchEvent) done.add("cafe");
  }
  const current = beats.find((beat) => !done.has(beat.id));

  const list = $("#arc-beats");
  list.replaceChildren();
  beats.forEach((beat) => {
    const item = document.createElement("li");
    item.className = "arc-beat" + (beat.required ? " is-required" : "");
    if (done.has(beat.id)) {
      item.classList.add("is-done");
    } else if (current && current.id === beat.id) {
      item.classList.add("is-current");
    }
    const time = document.createElement("span");
    time.className = "arc-time";
    time.textContent = beat.time;
    item.appendChild(time);
    const title = document.createElement("span");
    title.className = "arc-title";
    title.textContent = beat.title;
    item.appendChild(title);
    const place = document.createElement("span");
    place.className = "arc-place";
    place.textContent = beat.place;
    item.appendChild(place);
    const flag = document.createElement("span");
    flag.className = "arc-flag";
    flag.textContent = beat.required ? "required" : "optional";
    item.appendChild(flag);
    item.title = beat.goal || "";
    list.appendChild(item);
  });
}
/* ---- worlds ----------------------------------------------------------- */

export function castIdsFromScenario(scenario) {
  const list = scenario && Array.isArray(scenario.cast) ? scenario.cast : [];
  return list
    .map((value) => asCastId(value && typeof value === "object" ? (value.id || value.name) : value))
    .filter((id) => id && CAST[id]);
}

export function scenarioEndingMeta(ending) {
  if (!ending) return null;
  const raw = typeof ending === "string"
    ? { label: ending.replace(/[-_]+/g, " "), tone: ending }
    : ending;
  const toneRaw = String(raw.tone || raw.kind || "").toLowerCase();
  const tone = toneRaw.includes("bad")
    ? "bad"
    : (toneRaw.includes("good") ? "good" : "neutral");
  return {
    label: raw.label || raw.title || raw.id || "Ending card",
    tone,
  };
}

export function scenarioCard(scenario) {
  const current = currentScenario(state.data);
  const isCurrent = Boolean(current && current.id === scenario.id);
  const ending = scenarioEndingMeta(scenario.ending);
  const castIds = castIdsFromScenario(scenario);
  const card = document.createElement("article");
  card.className = `scenario-card${isCurrent ? " is-current" : ""}`;
  card.setAttribute("aria-label", `${scenario.title || scenario.id || "Scenario"} scenario`);

  const head = document.createElement("header");
  head.className = "scenario-card-head";
  const title = document.createElement("h3");
  title.textContent = scenario.title || scenario.id || "Untitled scenario";
  head.appendChild(title);
  const badge = document.createElement("span");
  badge.className = `ending-badge ${ending ? ending.tone : "neutral"}`;
  badge.textContent = ending ? ending.label : "No ending card";
  head.appendChild(badge);
  card.appendChild(head);

  const meta = document.createElement("div");
  meta.className = "scenario-meta";
  const seed = document.createElement("span");
  seed.className = "scenario-seed";
  seed.textContent = scenario.seed !== undefined && scenario.seed !== null
    ? `seed ${scenario.seed}`
    : "seed not reported";
  meta.appendChild(seed);
  const id = document.createElement("code");
  id.textContent = scenario.id || "—";
  meta.appendChild(id);
  if (isCurrent) {
    const now = document.createElement("span");
    now.className = "scenario-current-tag";
    now.textContent = "current";
    meta.appendChild(now);
  }
  card.appendChild(meta);

  const cast = document.createElement("div");
  cast.className = "scenario-cast";
  if (!castIds.length) {
    const empty = document.createElement("span");
    empty.className = "scenario-cast-empty";
    empty.textContent = "cast not reported";
    cast.appendChild(empty);
  } else {
    castIds.forEach((castId) => {
      const member = CAST[castId];
      const chip = document.createElement("span");
      chip.className = "scenario-cast-chip";
      chip.title = member.name;
      const dot = document.createElement("i");
      dot.className = "cast-dot";
      dot.style.background = member.color;
      const name = document.createElement("span");
      name.textContent = firstName(member.name);
      chip.append(dot, name);
      cast.appendChild(chip);
    });
  }
  card.appendChild(cast);

  if (scenario.notes) {
    const notes = document.createElement("p");
    notes.className = "scenario-notes";
    notes.textContent = scenario.notes;
    card.appendChild(notes);
  }

  const foot = document.createElement("div");
  foot.className = "scenario-foot";
  const load = document.createElement("button");
  load.type = "button";
  load.className = "btn primary";
  load.textContent = isCurrent ? "Reload & play" : "Load & play";
  load.disabled = Boolean(state.worlds.loadingScenario);
  load.addEventListener("click", () => loadScenario(scenario.id));
  foot.appendChild(load);
  card.appendChild(foot);
  return card;
}

export function renderWorlds() {
  renderTakes();
  const current = currentScenario(state.data);
  const name = $("#worlds-current-name");
  if (name) {
    name.textContent = current
      ? (current.title || current.id || "Loaded scenario")
      : "No scenario loaded";
  }
  const meta = $("#worlds-current-meta");
  if (meta) {
    if (current) {
      const cast = castIdsFromScenario(current);
      const pieces = [
        current.id,
        current.seed !== undefined && current.seed !== null ? `seed ${current.seed}` : "",
        cast.length ? cast.map(firstNameOf).join(", ") : "",
        current.place || "",
      ].filter(Boolean);
      meta.textContent = pieces.join(" · ") || "Scenario loaded.";
    } else {
      meta.textContent = "The base café canon is active.";
    }
  }
  const reset = $("#worlds-reset");
  if (reset) reset.textContent = current ? "Reset scenario" : "Reset demo";
  const evaluate = $("#worlds-evaluate");
  if (evaluate) evaluate.disabled = Boolean(state.worlds.loadingScenario);

  const status = $("#worlds-status");
  if (status) {
    status.textContent = state.worlds.status
      || (state.worlds.error ? `Scenarios unavailable: ${state.worlds.error}` : "");
  }

  const grid = $("#worlds-grid");
  if (!grid) return;
  grid.replaceChildren();
  const scenarios = state.worlds.scenarios;
  if (state.worlds.loading && !scenarios) {
    const loading = document.createElement("p");
    loading.className = "worlds-empty-line";
    loading.textContent = "Loading scenarios…";
    grid.appendChild(loading);
    return;
  }
  if (state.worlds.error && !scenarios) {
    const empty = document.createElement("article");
    empty.className = "card worlds-empty";
    const title = document.createElement("h3");
    title.textContent = "Scenarios not connected";
    const note = document.createElement("p");
    note.className = "card-sub";
    note.textContent = "The backend has not shipped GET /api/scenarios yet. The Story keeps working with the base canon.";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "btn";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => loadScenarios(true));
    empty.append(title, note, retry);
    grid.appendChild(empty);
    const detail = document.createElement("p");
    detail.className = "tiny";
    detail.textContent = state.worlds.error;
    empty.appendChild(detail);
    return;
  }
  if (!scenarios || !scenarios.length) {
    const empty = document.createElement("article");
    empty.className = "card worlds-empty";
    const title = document.createElement("h3");
    title.textContent = scenarios ? "No scenarios on disk" : "Scenarios not loaded";
    const note = document.createElement("p");
    note.className = "card-sub";
    note.textContent = scenarios
      ? "Add a JSON preset under world/scenarios/ and refresh."
      : "Open Worlds again to fetch the scenario list.";
    empty.append(title, note);
    grid.appendChild(empty);
    return;
  }
  scenarios.forEach((scenario) => {
    if (scenario && (scenario.id || scenario.title)) grid.appendChild(scenarioCard(scenario));
  });
}

export async function loadScenarios(force = false) {
  if (state.worlds.loading) return;
  if (!force && state.worlds.scenarios && Date.now() - state.worlds.fetchedAt < 5000) {
    renderWorlds();
    return;
  }
  state.worlds.loading = true;
  renderWorlds();
  try {
    const result = await api("/api/scenarios");
    state.worlds.scenarios = Array.isArray(result) ? result : ((result && result.scenarios) || []);
    state.worlds.error = "";
  } catch (error) {
    state.worlds.error = error.message || "not connected";
  } finally {
    state.worlds.loading = false;
    state.worlds.fetchedAt = Date.now();
    renderWorlds();
  }
}

/* A switch is a reset + seed: clear the dashboard's phone thread, selected
   cast and turn playback before the next state poll repaints the world. */
export function clearScenarioRuntime(scenario) {
  state.turn = null;
  state.groupStatus = "";
  state.beatId = null;
  state.whisper = false;
  state.whisperTarget = null;
  state.phone.character = null;
  state.phone.messages = [];
  state.phone.hasMore = false;
  state.phone.oldestId = null;
  state.phone.loading = false;
  state.phone.loadingFor = null;
  state.phone.sending = false;
  state.phone.loadedFor = null;
  state.phone.error = "";
  state.phone.paintSig = null;
  resetPhoneHistorySeq();
  cancelTyping();
  closePhone();
  closeProfile();
  const thread = $("#phone-thread");
  if (thread) thread.replaceChildren();
  const typing = $("#phone-typing");
  if (typing) typing.hidden = true;
  ["#turn-log", "#scene-cast", "#scene-choices", "#scene-rail"].forEach((selector) => {
    const node = $(selector);
    if (node) node.dataset.sig = "";
  });
  const say = $("#scene-say-input");
  if (say) say.value = "";
  const ids = castIdsFromScenario(scenario || {});
  state.selected = ids[0] || ORDER[0];
}

export async function loadScenario(id, options = {}) {
  if (!id || state.worlds.loadingScenario) return false;
  let ok = false;
  state.worlds.loadingScenario = id;
  state.worlds.status = `Loading ${id}…`;
  renderWorlds();
  try {
    const result = await api(`/api/scenarios/${encodeURIComponent(id)}/load`, {
      method: "POST",
      body: "{}",
    });
    const scenario = (result && result.scenario) || { id };
    state.worlds.current = scenario;
    state.worlds.status = `Loaded ${scenario.title || scenario.id || id}.`;
    // Loading a scenario is a reset; any take is no longer active.
    state.takes.current = null;
    state.takes.changed = false;
    state.takes.nextNote = "";
    clearScenarioRuntime(scenario);
    if (result && result.state) {
      state.data = result.state;
      if (!state.data.scenario) state.data.scenario = scenario;
      render(state.data);
    } else if (state.data) {
      state.data.scenario = scenario;
    }
    await refresh();
    if (options.view !== false) setView("story");
    if (options.autoEnding !== false && scenarioEndingIsFork(scenario)) {
      const forkId = String(scenario.id || id);
      const bad = /bad/i.test(forkId);
      const ending = scenario.ending || {
        id: forkId,
        label: bad ? "BAD END" : "GOOD END",
        tone: bad ? "bad" : "good",
        evidence: [],
      };
      showEnding(ending, (ending && ending.evidence) || [], {
        subtitle: `${scenario.title || forkId} · loaded`,
      });
    }
    ok = true;
  } catch (error) {
    state.worlds.status = `Could not load ${id}: ${error.message}`;
  } finally {
    state.worlds.loadingScenario = null;
    renderWorlds();
  }
  return ok;
}

export async function resetCurrentScenario() {
  if (state.worlds.loadingScenario) return;
  const scenario = currentScenario(state.data);
  const label = scenario ? (scenario.title || scenario.id) : "the base canon";
  if (!window.confirm(`Reset ${label}? Phone DMs and the scene reset; Switch room history stays.`)) return;
  if (scenario && scenario.id) {
    state.worlds.status = `Resetting ${label}…`;
    const ok = await loadScenario(scenario.id, { autoEnding: false, view: false });
    if (ok) state.worlds.status = `Reset ${label} to its seed.`;
    renderWorlds();
    return;
  }
  state.worlds.status = "Resetting the base canon…";
  renderWorlds();
  try {
    await api("/api/dev/reset", { method: "POST", body: "{}" });
    state.worlds.current = null;
    state.takes.current = null;
    state.takes.changed = false;
    state.takes.nextNote = "";
    clearScenarioRuntime(null);
    await refresh();
    state.worlds.status = "Demo world reset to the base canon.";
  } catch (error) {
    state.worlds.status = `Reset failed: ${error.message}`;
  }
  renderWorlds();
}
/* ---- takes shelf ------------------------------------------------------ */

export function takeScenarioId(take) {
  if (!take) return "";
  if (typeof take.scenario === "string") return take.scenario;
  if (take.scenario && typeof take.scenario === "object") {
    return take.scenario.id || take.scenario.title || "";
  }
  return take.scenario_id || "";
}

export function takeCard(take) {
  const current = state.takes.current;
  const isCurrent = Boolean(current && current.take
    && ((current.take.id && current.take.id === take.id)
      || (!current.take.id && current.take.title === take.title)));
  const count = takeSceneCount(take);
  const ending = scenarioEndingMeta(take.ending);
  const scenarioId = takeScenarioId(take);
  const card = document.createElement("article");
  card.className = `take-card${isCurrent ? " is-current" : ""}`;
  card.setAttribute("aria-label", `${take.title || take.id || "Take"} take`);

  const head = document.createElement("header");
  head.className = "take-card-head";
  const title = document.createElement("h3");
  title.textContent = take.title || take.id || "Untitled take";
  head.appendChild(title);
  const badge = document.createElement("span");
  badge.className = `ending-badge ${ending ? ending.tone : "neutral"}`;
  badge.textContent = ending ? ending.label : "No ending card";
  head.appendChild(badge);
  card.appendChild(head);

  const meta = document.createElement("div");
  meta.className = "take-meta";
  const scenes = document.createElement("span");
  scenes.className = "take-scenes";
  scenes.textContent = count ? `${count} scene${count === 1 ? "" : "s"}` : "scene count not reported";
  meta.appendChild(scenes);
  if (scenarioId) {
    const scenario = document.createElement("code");
    scenario.textContent = scenarioId;
    scenario.title = "Source scenario";
    meta.appendChild(scenario);
  }
  if (isCurrent) {
    const now = document.createElement("span");
    now.className = "scenario-current-tag";
    now.textContent = `current · scene ${current.index + 1}`;
    meta.appendChild(now);
  }
  card.appendChild(meta);

  if (Array.isArray(take.scenes) && take.scenes.length) {
    const beat = document.createElement("p");
    beat.className = "take-beats";
    beat.textContent = take.scenes
      .slice(0, 4)
      .map((scene, index) => `${index + 1}. ${(scene && (scene.title || scene.id)) || "untitled"}`)
      .join(" · ")
      + (take.scenes.length > 4 ? " · …" : "");
    card.appendChild(beat);
  }

  const foot = document.createElement("div");
  foot.className = "take-foot";
  const load = document.createElement("button");
  load.type = "button";
  load.className = "btn primary";
  const busy = state.takes.loadingTake === take.id;
  load.textContent = busy ? "Loading…" : (isCurrent ? "Reload & play" : "Load & play");
  load.disabled = Boolean(state.takes.loadingTake) || state.safety.paused;
  load.addEventListener("click", () => loadTake(take.id));
  foot.appendChild(load);
  if (isCurrent) {
    const chip = document.createElement("span");
    chip.className = "take-now";
    chip.textContent = `scene ${current.index + 1}${count ? ` of ${count}` : ""}`;
    foot.appendChild(chip);
  }
  card.appendChild(foot);
  return card;
}

export function renderTakes() {
  const info = currentTakeInfo(state.data);
  const current = state.takes.current;
  const take = info.take;
  const name = $("#takes-current-name");
  const meta = $("#takes-current-meta");
  const next = $("#takes-next");
  const note = $("#takes-next-note");
  const status = $("#takes-status");

  if (name) name.textContent = take ? (take.title || take.id || "Loaded take") : "No take loaded";
  if (meta) {
    if (take) {
      const bits = [
        take.id && take.id !== (take.title || "") ? take.id : "",
        takeScenarioId(take) ? `scenario ${takeScenarioId(take)}` : "",
        `scene ${info.index + 1}${info.count ? ` of ${info.count}` : ""}`,
        info.scene && info.scene.title ? info.scene.title : "",
      ].filter(Boolean);
      meta.textContent = bits.join(" · ") || "Take loaded.";
    } else {
      meta.textContent = "Load a take below to start scene 1.";
    }
  }

  const gate = takeAdvanceState(state.data);
  if (next) {
    next.disabled = !gate.ok || state.takes.advancing;
    next.setAttribute("aria-disabled", next.disabled ? "true" : "false");
    next.title = gate.ok ? gate.reason : (state.takes.nextNote || gate.reason);
    next.classList.toggle("is-ready", gate.ok && !state.takes.advancing);
  }
  if (note) {
    note.textContent = state.takes.advancing
      ? "Advancing to the next scene…"
      : (state.takes.nextNote || gate.reason);
    note.classList.toggle("is-ready", gate.ok && !state.takes.advancing);
  }
  if (status) {
    status.textContent = state.takes.status
      || (state.takes.error ? `Takes unavailable: ${state.takes.error}` : "");
  }

  const grid = $("#takes-grid");
  if (!grid) return;
  const list = state.takes.list;
  const sig = [
    state.takes.loading ? "l" : "",
    state.takes.loadingTake || "",
    state.takes.error || "",
    take ? `${take.id || take.title}:${info.index}` : "",
    (list || []).map((item) => `${item && (item.id || item.title)}:${takeSceneCount(item)}`).join(","),
  ].join("|");
  if (grid.dataset.sig === sig) return;
  grid.dataset.sig = sig;
  grid.replaceChildren();

  if (state.takes.loading && !list) {
    const loading = document.createElement("p");
    loading.className = "worlds-empty-line";
    loading.textContent = "Loading takes…";
    grid.appendChild(loading);
    return;
  }
  if (state.takes.error && !list) {
    const empty = document.createElement("article");
    empty.className = "card worlds-empty";
    const title = document.createElement("h3");
    title.textContent = "Takes not connected";
    const body = document.createElement("p");
    body.className = "card-sub";
    body.textContent = "The backend has not shipped GET /api/takes yet. Worlds and the Story keep working.";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "btn";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => loadTakes(true));
    empty.append(title, body, retry);
    const detail = document.createElement("p");
    detail.className = "tiny";
    detail.textContent = state.takes.error;
    empty.appendChild(detail);
    grid.appendChild(empty);
    return;
  }
  if (!list || !list.length) {
    const empty = document.createElement("article");
    empty.className = "card worlds-empty";
    const title = document.createElement("h3");
    title.textContent = list ? "No takes on disk" : "Takes not loaded";
    const body = document.createElement("p");
    body.className = "card-sub";
    body.textContent = list
      ? "Add a JSON take under world/takes/ and refresh."
      : "Open Worlds again to fetch the take list.";
    empty.append(title, body);
    grid.appendChild(empty);
    return;
  }
  list.forEach((item) => {
    if (item && (item.id || item.title)) grid.appendChild(takeCard(item));
  });
}

export async function loadTakes(force = false) {
  if (state.takes.loading) return;
  if (!force && state.takes.list && Date.now() - state.takes.fetchedAt < 5000) {
    renderTakes();
    return;
  }
  state.takes.loading = true;
  renderTakes();
  try {
    const result = await api("/api/takes");
    state.takes.list = Array.isArray(result) ? result : ((result && result.takes) || []);
    state.takes.error = "";
  } catch (error) {
    state.takes.error = error.message || "not connected";
  } finally {
    state.takes.loading = false;
    state.takes.fetchedAt = Date.now();
    state.takes.probed = true;
    renderTakes();
  }
}

export async function loadTakeCurrent(force = false) {
  if (!force && state.takes.probed
    && Date.now() - state.takes.currentFetchedAt < 5000) return;
  try {
    const result = await api("/api/takes/current");
    state.takes.probed = true;
    state.takes.currentFetchedAt = Date.now();
    const previous = state.takes.current;
    const next = setTakeCurrent(result && result.take !== undefined ? result : null);
    if (next) {
      const moved = !previous
        || previous.index !== next.index
        || (previous.take && previous.take.id && next.take && next.take.id
          && previous.take.id !== next.take.id);
      if (moved) markSceneBaseline(result.state || state.data);
      else syncTakeChange(result.state || state.data);
    } else {
      state.takes.changed = false;
    }
    if (state.view === "worlds") renderTakes();
    if (state.view === "story" && state.data) renderStoryHud(state.data);
  } catch {
    state.takes.probed = true;
    state.takes.currentFetchedAt = Date.now();
  }
}

export async function loadTake(id) {
  if (!id || state.takes.loadingTake) return;
  if (state.safety.paused) {
    state.takes.status = "The scene is paused. Resume in Studio before loading a take.";
    renderTakes();
    return;
  }
  const listed = (state.takes.list || []).find((item) => item && item.id === id) || null;
  state.takes.loadingTake = id;
  state.takes.status = `Loading ${listed ? (listed.title || id) : id}…`;
  state.takes.nextNote = "";
  renderTakes();
  try {
    const result = await api(`/api/takes/${encodeURIComponent(id)}/load`, {
      method: "POST",
      body: "{}",
    });
    const raw = {
      take: result && result.take ? result.take : (listed || { id }),
      scene: result && result.scene,
      index: result && result.index,
      state: result && result.state,
    };
    setTakeCurrent(raw);
    markSceneBaseline((result && result.state) || raw);
    state.takes.status = `Loaded ${(raw.take && (raw.take.title || raw.take.id)) || id}.`;
    clearScenarioRuntime({ cast: (raw.scene && raw.scene.cast) || [] });
    if (result && result.state) {
      state.data = result.state;
      if (!state.data.take) state.data.take = raw.take;
      render(state.data);
    }
    await refresh();
    setView("story");
  } catch (error) {
    state.takes.status = `Could not load ${id}: ${error.message}`;
  } finally {
    state.takes.loadingTake = null;
    renderTakes();
  }
}

export async function advanceTake() {
  if (state.takes.advancing) return;
  const gate = takeAdvanceState(state.data);
  if (!gate.ok) {
    state.takes.nextNote = gate.reason;
    renderTakes();
    return;
  }
  state.takes.advancing = true;
  state.takes.nextNote = "";
  renderTakes();
  try {
    const result = await api("/api/takes/next", {
      method: "POST",
      body: "{}",
    });
    const raw = {
      take: result && result.take,
      scene: result && result.scene,
      index: result && result.index,
      state: result && result.state,
    };
    if (!raw.take && state.takes.current) raw.take = state.takes.current.take;
    const next = setTakeCurrent(raw);
    if (result && result.changed === false) {
      state.takes.changed = false;
      state.takes.nextNote = "Nothing has changed yet. Say a line or use a cue before advancing.";
    } else {
      markSceneBaseline((result && result.state) || raw);
      state.takes.changed = false;
      state.takes.nextNote = "";
      state.takes.status = next
        ? `Scene ${next.index + 1}${next.take && takeSceneCount(next.take) ? ` of ${takeSceneCount(next.take)}` : ""} loaded.`
        : "Scene advanced.";
    }
    if (result && result.state) {
      state.data = result.state;
      if (!state.data.take && result.take) state.data.take = result.take;
      render(state.data);
    }
    await refresh();
    const ending = (result && result.ending)
      || (result && result.done && result.take && result.take.ending);
    if (ending) {
      showEnding(ending, (ending && ending.evidence) || [], {
        subtitle: `${(result.take && (result.take.title || result.take.id)) || "Take"} · take complete`,
      });
    }
  } catch (error) {
    if (error.status === 409) {
      const body = error.body || {};
      const info = body.detail && typeof body.detail === "object"
        ? { ...body, ...body.detail }
        : body;
      const code = error.code || info.error || "";
      if (code === "STALE_REVISION") {
        state.takes.nextNote = "The world moved on. Refreshed the latest scene — try again.";
        await refresh();
      } else if (code === "NOTHING_CHANGED" || /nothing|change/i.test(error.message)) {
        state.takes.changed = false;
        state.takes.nextNote = "Nothing has changed yet. Say a line or use a cue before advancing.";
      } else {
        state.takes.nextNote = info.message || info.reason
          || "The scene cannot advance yet.";
      }
    } else {
      state.takes.nextNote = `Next scene is unavailable: ${error.message}`;
    }
  } finally {
    state.takes.advancing = false;
    renderTakes();
  }
}
/* The clock badge is explicit about the time machine: a non-1 scale is real
   time running faster, so it reads REAL x60; everything else reads MOCK. */

export function renderClockScale(data) {
  const clock = (data && data.clock) || {};
  const label = clockScaleLabel(clock);
  const badge = $("#clock-scale");
  if (badge) {
    badge.textContent = label;
    badge.classList.toggle("is-real", label.startsWith("REAL"));
    badge.title = label.startsWith("REAL")
      ? `Real time · story clock runs ${scaleFactor(clock.scale)} wall time`
      : "Mock time · the story waits for you";
  }
  return label;
}
export function nextBeat() {
  const turn = state.turn;
  if (!turn) {
    startLatestTurnPlayback();
    return;
  }
  if (turn.done) {
    if (turn.source === "events") {
      state.turn = null;
      renderStory(state.data);
      return;
    }
    state.groupStatus = "Turn complete. Say something else to start a new turn.";
    renderStory(state.data);
    return;
  }
  const lines = turn.lines || [];
  if (!lines.length) {
    turn.done = true;
    renderStory(state.data);
    return;
  }
  if (turn.index < lines.length) {
    if (state.groupStatus === "Replaying the latest turn.") state.groupStatus = "";
    let next = turn.index + 1;
    if (lines[turn.index] && lines[turn.index].chorus) {
      while (next < lines.length && lines[next].chorus
        && (lines[next].turnId || null) === (lines[turn.index].turnId || null)) {
        next += 1;
      }
    }
    turn.index = next;
    const revealed = lines[Math.min(next, lines.length) - 1];
    if (revealed) {
      const castId = revealed.castId || asCastId(revealed.character);
      if (castId && CAST[castId] && !absentSet(state.data).has(castId)) {
        state.selected = castId;
        resetPhoneFor(castId);
      }
    }
    if (next >= lines.length) turn.done = true;
    renderStory(state.data);
    return;
  }
  turn.done = true;
  renderStory(state.data);
}

/* On a fresh page, or after a completed turn, Next replays the latest turn
   recorded with turn metadata from the start. */
export function startLatestTurnPlayback() {
  const data = state.data || {};
  const entries = buildEventEntries(data).filter((entry) => entry.turnId && !entry.isUser);
  if (!entries.length) {
    state.groupStatus = "Nothing to replay yet. Say something to the room.";
    renderStory(data);
    return;
  }
  const lastTurnId = entries[entries.length - 1].turnId;
  const lines = entries.filter((entry) => entry.turnId === lastTurnId);
  state.turn = {
    id: lastTurnId,
    source: "events",
    plan: null,
    userText: null,
    lines,
    index: 0,
    done: false,
    startedAt: 0,
    transport: null,
    boundary: false,
    boundaryTarget: null,
  };
  state.groupStatus = "Replaying the latest turn.";
  renderStory(data);
}
