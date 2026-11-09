/* Studio, Settings and the dev-harness actions. */

import { api } from "../api.js";
import { asCastId, formatClock, formatTime, scaleFactor } from "../format.js";
import { state } from "../state.js";
import { CAST_ORDER as ORDER } from "../vocab.js";
import { $, CAST, SECRET_KEY } from "./dom.js";
import { openProfile, renderCanon } from "./ledger.js";
import { isFriend } from "./phone.js";
import { absentSet, renderSafety } from "./stage.js";
import { refresh } from "../views.js";

/* ---- settings --------------------------------------------------------- */

export function renderSettings(data) {
  const current = data || state.data || {};
  renderCanon(current);
  const scene = current.scene || {};
  const mode = (current.clock && current.clock.mode) || "mock";
  const clockNow = $("#clock-now");
  if (clockNow) clockNow.textContent = formatClock(current.clock.now);
  const clockMode = $("#clock-mode");
  if (clockMode) {
    clockMode.textContent = mode === "realtime"
      ? `real time · ${scaleFactor(current.clock.scale)}`
      : "mock time";
    clockMode.className = mode === "realtime" ? "is-real" : "";
  }
  const clockNext = $("#clock-next");
  if (clockNext) {
    clockNext.textContent = scene.next_beat
      ? `${scene.next_beat.time} · ${scene.next_beat.title}`
      : "—";
  }
  const clockStatus = $("#clock-status");
  if (clockStatus) {
    clockStatus.textContent = state.clockStatus || (mode === "realtime"
      ? "Real time · the story follows the wall clock until you jump."
      : "Mock time · the story waits for you.");
  }
  const beatSelect = $("#beat-select");
  if (beatSelect) {
    const previous = beatSelect.value;
    const beats = (current.canon && current.canon.beats) || [];
    const sig = beats.map((beat) => `${beat.id}:${beat.title}:${beat.time}:${beat.required}`).join("|");
    if (beatSelect.dataset.sig !== sig) {
    beatSelect.dataset.sig = sig;
    beatSelect.replaceChildren();
    beats.forEach((beat) => {
      const option = document.createElement("option");
      option.value = beat.id;
      option.textContent = `${beat.title} · ${beat.time}${beat.required ? " · required" : ""}`;
      beatSelect.appendChild(option);
    });
    }
    const ids = beats.map((beat) => beat.id);
    beatSelect.value = ids.includes(previous) ? previous : (ids.includes("cafe") ? "cafe" : (ids[0] || ""));
  }
  const events = current.events || [];
  const branchEvent = [...events].reverse().find((event) => event.kind === "branch");
  const worldEvent = [...events].reverse().find((event) => event.kind === "world_event");
  const bifrostStatus = $("#bifrost-status");
  if (bifrostStatus && branchEvent) {
    bifrostStatus.textContent = `Last branch: ${branchEvent.summary}`;
  }
  const tavilyStatus = $("#tavily-status");
  if (tavilyStatus && worldEvent) {
    tavilyStatus.textContent = worldEvent.summary;
  }
  const list = $("#provider-list");
  list.replaceChildren();
  (window.SWITCH_PROVIDERS || []).forEach((provider) => {
    const row = document.createElement("div");
    row.className = "provider-row";
    const left = document.createElement("div");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = provider.label;
    left.appendChild(name);
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = provider.note;
    left.appendChild(note);
    row.appendChild(left);
    const status = document.createElement("span");
    status.className = `provider-status ${provider.status}`;
    status.textContent = provider.status;
    row.appendChild(status);
    list.appendChild(row);
  });
}
/* ---- shell ------------------------------------------------------------ */

/* ---- studio ----------------------------------------------------------- */

export const STUDIO_HEALTH = ["world", "switch", "mattermost", "gateway", "bifrost"];
export const STUDIO_REFRESH_MS = 5000;
export const STUDIO_RETRY_MS = 15000;

export function maybeLoadStudio() {
  const retry = state.studio.error ? STUDIO_RETRY_MS : STUDIO_REFRESH_MS;
  if (!state.studio.fetchedAt || Date.now() - state.studio.fetchedAt >= retry) loadStudio();
  else renderStudio();
}

export async function loadStudio(force = false) {
  if (state.studio.loading) return;
  const now = Date.now();
  const retry = state.studio.error ? STUDIO_RETRY_MS : STUDIO_REFRESH_MS;
  if (!force && state.studio.fetchedAt && now - state.studio.fetchedAt < retry) {
    renderStudio();
    return;
  }
  state.studio.loading = true;
  renderStudio();
  try {
    const data = await api("/api/studio/summary");
    state.studio.data = data;
    state.studio.error = "";
    state.studio.fetchedAt = Date.now();
  } catch (error) {
    state.studio.error = error.message || "not connected";
    state.studio.fetchedAt = Date.now();
  } finally {
    state.studio.loading = false;
    renderStudio();
  }
}

export function renderStudioHealth(health) {
  const host = $("#studio-health");
  if (!host) return;
  host.replaceChildren();
  if (!health) {
    const chip = document.createElement("span");
    chip.className = "health-chip is-unknown";
    chip.textContent = "health unavailable";
    host.appendChild(chip);
    return;
  }
  const keys = [...new Set([...STUDIO_HEALTH, ...Object.keys(health)])];
  keys.forEach((key) => {
    const on = Boolean(health[key]);
    const chip = document.createElement("span");
    chip.className = `health-chip ${on ? "is-on" : "is-off"}`;
    const dot = document.createElement("i");
    dot.setAttribute("aria-hidden", "true");
    chip.appendChild(dot);
    const label = document.createElement("span");
    label.textContent = key.replaceAll("_", " ");
    chip.appendChild(label);
    const stateLabel = document.createElement("em");
    stateLabel.textContent = on ? "up" : "down";
    chip.appendChild(stateLabel);
    host.appendChild(chip);
  });
}

export function studioBeatCard(label, beat, className) {
  const item = document.createElement("div");
  item.className = `studio-beat-card ${className}`;
  const eyebrow = document.createElement("span");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = label;
  item.appendChild(eyebrow);
  const title = document.createElement("strong");
  title.textContent = beat ? (beat.title || beat.id || "—") : "—";
  item.appendChild(title);
  const meta = document.createElement("span");
  meta.className = "studio-beat-meta";
  meta.textContent = beat
    ? [beat.time, beat.id].filter(Boolean).join(" · ")
    : "not reported";
  item.appendChild(meta);
  return item;
}

export function renderStudioBeats(data) {
  const host = $("#studio-beats");
  if (!host) return;
  host.replaceChildren();
  const clock = (data && data.clock) || (state.data && state.data.clock) || {};
  const scene = (state.data && state.data.scene) || {};
  const current = (data && data.current_beat) || scene.current_beat || null;
  const next = (data && data.next_beat) || scene.next_beat || null;
  const mode = $("#studio-clock-mode");
  if (mode) {
    mode.textContent = `${clock.mode || "mock"} · ${scaleFactor(clock.scale)} · ${clock.now ? formatTime(clock.now) : "—"}`;
  }
  host.append(
    studioBeatCard("current beat", current, "is-current"),
    studioBeatCard("next beat", next, "is-next"),
  );
  if (data && data.arc_complete) {
    const done = document.createElement("div");
    done.className = "studio-beat-card is-done";
    const eyebrow = document.createElement("span");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "arc";
    const title = document.createElement("strong");
    title.textContent = "complete";
    done.append(eyebrow, title);
    host.appendChild(done);
  }
}

export function renderStudioAgents(data) {
  const host = $("#studio-agents");
  if (!host) return;
  host.replaceChildren();
  const absent = absentSet(state.data || {});
  let agents = data && Array.isArray(data.agents) ? data.agents : null;
  if (!agents) {
    agents = ORDER.map((id) => ({
      id,
      name: CAST[id].name,
      role: CAST[id].role,
      friend: isFriend(state.data, id),
      absent: absent.has(id),
      last_event: "",
    }));
  }
  if (!agents.length) {
    const empty = document.createElement("p");
    empty.className = "tiny";
    empty.textContent = "No agents reported.";
    host.appendChild(empty);
    return;
  }
  agents.forEach((agent) => {
    const id = asCastId(agent.id || agent.character || agent.name);
    const cast = id && CAST[id] ? CAST[id] : null;
    const row = document.createElement("button");
    row.type = "button";
    row.className = "studio-agent";
    if (cast) {
      const img = document.createElement("img");
      img.src = cast.avatar;
      img.alt = "";
      img.onerror = () => {
        img.onerror = null;
        img.src = `/static/assets/portraits/${cast.id}-avatar.svg`;
      };
      row.appendChild(img);
    }
    const copy = document.createElement("div");
    copy.className = "studio-agent-copy";
    const name = document.createElement("strong");
    name.textContent = agent.name || (cast && cast.name) || agent.id || "agent";
    copy.appendChild(name);
    const role = document.createElement("span");
    role.textContent = agent.role || (cast && cast.role) || "character";
    copy.appendChild(role);
    const last = document.createElement("em");
    last.textContent = agent.last_event || "no recent event";
    copy.appendChild(last);
    row.appendChild(copy);

    const flags = document.createElement("div");
    flags.className = "studio-flags";
    const friend = agent.friend !== undefined ? Boolean(agent.friend) : isFriend(state.data, id);
    const gone = agent.absent !== undefined ? Boolean(agent.absent) : absent.has(id);
    const friendFlag = document.createElement("span");
    friendFlag.className = `agent-flag ${friend ? "is-friend" : "is-muted"}`;
    friendFlag.textContent = friend ? "friend" : "locked";
    flags.appendChild(friendFlag);
    const absentFlag = document.createElement("span");
    absentFlag.className = `agent-flag ${gone ? "is-absent" : "is-muted"}`;
    absentFlag.textContent = gone ? "absent" : "present";
    flags.appendChild(absentFlag);
    row.appendChild(flags);

    if (cast) row.addEventListener("click", () => openProfile(cast.id));
    host.appendChild(row);
  });
}

export function renderStudioRooms(data) {
  const host = $("#studio-rooms");
  if (!host) return;
  host.replaceChildren();
  const rooms = data && Array.isArray(data.rooms) ? data.rooms : [];
  if (!rooms.length) {
    const empty = document.createElement("p");
    empty.className = "tiny";
    empty.textContent = data ? "No rooms reported." : "Not connected — rooms will appear here.";
    host.appendChild(empty);
    return;
  }
  rooms.forEach((room) => {
    const row = document.createElement("div");
    row.className = "studio-room";
    const name = document.createElement("strong");
    name.textContent = room.name || room.room || "room";
    row.appendChild(name);
    const code = document.createElement("code");
    code.textContent = room.room_id || room.id || "—";
    row.appendChild(code);
    host.appendChild(row);
  });
}

export function renderStudioRecent(data) {
  const host = $("#studio-recent");
  if (!host) return;
  host.replaceChildren();
  const recent = data && Array.isArray(data.recent) ? data.recent : [];
  if (!recent.length) {
    const empty = document.createElement("li");
    empty.className = "studio-feed-empty";
    empty.textContent = data ? "No recent activity." : "Not connected — recent events will appear here.";
    host.appendChild(empty);
    return;
  }
  recent.slice(0, 24).forEach((item) => {
    const li = document.createElement("li");
    const kind = document.createElement("span");
    kind.className = "studio-feed-kind";
    kind.textContent = String(item.kind || "event").replaceAll("_", " ");
    li.appendChild(kind);
    const text = document.createElement("span");
    text.textContent = item.summary || item.text || "";
    li.appendChild(text);
    host.appendChild(li);
  });
}

export function renderStudio() {
  const data = state.studio.data;
  const conn = $("#studio-conn");
  if (conn) {
    conn.textContent = state.studio.loading ? "connecting…" : (data ? "connected" : "not connected");
    conn.className = `studio-conn${data ? " is-on" : " is-off"}${state.studio.loading ? " is-loading" : ""}`;
  }
  const status = $("#studio-status");
  if (status) {
    if (state.studio.loading) {
      status.hidden = false;
      status.textContent = "Trying the studio summary…";
    } else if (!data) {
      status.hidden = false;
      status.textContent = `Studio summary not connected${state.studio.error ? ` (${state.studio.error})` : ""}. The scene keeps working; retry when the backend ships GET /api/studio/summary.`;
    } else if (state.studio.error) {
      status.hidden = false;
      status.textContent = `Showing the last summary — reconnecting (${state.studio.error}).`;
    } else {
      status.hidden = true;
      status.textContent = "";
    }
  }
  renderStudioHealth(data && data.health ? data.health : null);
  renderStudioBeats(data);
  renderStudioAgents(data);
  renderStudioRooms(data);
  renderStudioRecent(data);
  renderSafety();
}

export async function studioAdvance() {
  const button = $("#studio-advance");
  const note = $("#studio-advance-status");
  if (!button || button.disabled) return;
  button.disabled = true;
  if (note) note.textContent = "Advancing and playing the next beat…";
  try {
    const result = await api("/api/clock/advance", {
      method: "POST",
      body: JSON.stringify({ run: true }),
    });
    if (note) {
      note.textContent = result.arc_complete
        ? "Arc complete — every authored beat has run."
        : `Played ${(result.view && result.view.current_beat && result.view.current_beat.title)
          || (result.beat && result.beat.title) || "the next beat"}.`;
    }
    state.turn = null;
    await refresh();
    await loadStudio(true);
  } catch (error) {
    if (note) note.textContent = `Advance failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

/* ---- actions ---------------------------------------------------------- */

export async function tellAlice() {
  const secret = $("#secret").value.trim();
  if (!secret) {
    $("#status").textContent = "Write a secret first.";
    return;
  }
  try {
    await api("/api/dev/tell-alice", { method: "POST", body: JSON.stringify({ secret, key: SECRET_KEY }) });
    $("#status").textContent = "Alice recorded the secret. Check the ledger.";
    state.turn = null;
    await refresh();
  } catch (error) {
    $("#status").textContent = `Tell Alice failed: ${error.message}`;
  }
}

export async function runBifrost() {
  const button = $("#run-bifrost");
  const status = $("#bifrost-status");
  const beat = $("#beat-select")?.value || "cafe";
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Running Bifrost…";
  status.textContent = `Bifrost is generating ${beat}...`;
  try {
    const result = await api("/api/dev/run-beat", {
      method: "POST",
      body: JSON.stringify({ beat, transport: "bifrost" }),
    });
    const used = Object.values((result.bifrost && result.bifrost.characters) || {})
      .reduce((sum, item) => sum + Number(item.used_tokens || 0), 0);
    const branch = result.branch ? ` · ${result.branch.label} (${result.branch.id})` : "";
    status.textContent = `Bifrost beat: ${result.beat.title}${branch} · ${used} tokens logged · log: data/logs/bifrost.jsonl`;
    state.turn = null;
    await refresh();
    await loadSceneCard();
  } catch (error) {
    status.textContent = `Bifrost beat failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

export async function fetchTavily() {
  const button = $("#fetch-tavily");
  const status = $("#tavily-status");
  const query = $("#tavily-query").value.trim();
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Searching…";
  try {
    const result = await api("/api/dev/tavily-event", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
    const marker = result.offline ? " (offline fixture)" : "";
    status.textContent = `${result.title}${marker} · ${result.holders.length} characters now share this event · key ${result.key}`;
    await refresh();
  } catch (error) {
    status.textContent = `Tavily event failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

export async function setClockMode(mode) {
  const status = $("#clock-status");
  state.clockStatus = mode === "realtime" ? "Aligning the story to the wall clock…" : "Freezing the story clock…";
  if (status) status.textContent = state.clockStatus;
  try {
    const result = await api("/api/clock/mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    state.clockStatus = mode === "realtime"
      ? `Real time from ${formatClock(result.clock.now)}. The next beat arrives when the clock does.`
      : "Mock time · the story waits for you.";
    if (status) status.textContent = state.clockStatus;
    await refresh();
  } catch (error) {
    state.clockStatus = `Clock mode failed: ${error.message}`;
    if (status) status.textContent = state.clockStatus;
  }
}

export async function advanceClock(run) {
  const status = $("#clock-status");
  const buttons = [$("#clock-advance"), $("#clock-play")];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  state.clockStatus = run ? "Jumping to the next beat and playing it…" : "Jumping to the next beat…";
  if (status) status.textContent = state.clockStatus;
  try {
    const result = await api("/api/clock/advance", {
      method: "POST",
      body: JSON.stringify({ run: Boolean(run) }),
    });
    if (result.arc_complete) {
      state.clockStatus = "Arc complete — all five beats have run. Use Advance to move the clock on.";
    } else {
      const played = result.played ? " · beat played" : "";
      state.clockStatus = `Now ${result.view.current_beat.title} at ${formatClock(result.clock.now)}${played}.`;
    }
    if (status) status.textContent = state.clockStatus;
    state.turn = null;
    await refresh();
    if (run) await loadSceneCard();
  } catch (error) {
    state.clockStatus = `Clock advance failed: ${error.message}`;
    if (status) status.textContent = state.clockStatus;
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
  }
}

export async function runLocalBeat() {
  const beat = $("#beat-select")?.value || "cafe";
  try {
    const result = await api("/api/dev/run-beat", {
      method: "POST",
      body: JSON.stringify({ beat, transport: "local" }),
    });
    const branch = result.branch ? ` · ${result.branch.label} (${result.branch.id})` : "";
    $("#status").textContent = `Local beat: ${result.beat.title}${branch}.`;
    state.turn = null;
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Local beat failed: ${error.message}`;
  }
}

export async function runArc() {
  const button = $("#run-arc");
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Running arc…";
  try {
    const result = await api("/api/dev/run-arc", { method: "POST", body: "{}" });
    $("#status").textContent = `Local arc complete: five beats · ${result.branch.label} (${result.branch.id}).`;
    state.turn = null;
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Local arc failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

export async function resetWorld() {
  if (!window.confirm("Reset the world state, phone DMs, and current scene card? Switch/Mattermost room history stays.")) return;
  try {
    await api("/api/dev/reset", { method: "POST", body: "{}" });
    $("#status").textContent = "Demo world reset. Switch/Mattermost history is unchanged.";
    $("#card-preview").hidden = true;
    $("#card-preview").textContent = "";
    $("#card-path").textContent = "No card loaded yet.";
    state.turn = null;
    state.studio.data = null;
    state.studio.error = "";
    state.studio.fetchedAt = 0;
    await refresh();
  } catch (error) {
    $("#status").textContent = `Reset failed: ${error.message}`;
  }
}

export async function loadSceneCard() {
  try {
    const card = await api("/api/scene-card");
    $("#card-path").textContent = card.path;
    const preview = $("#card-preview");
    preview.textContent = card.text;
    preview.hidden = false;
  } catch (error) {
    $("#status").textContent = `Scene card failed: ${error.message}`;
  }
}

export async function copyLiveCommand() {
  const command = "uv run director --switch";
  try {
    await navigator.clipboard.writeText(command);
    $("#status").textContent = `Copied: ${command}. Run it in the switch-world terminal.`;
  } catch {
    $("#status").textContent = `Run in the terminal: ${command}`;
  }
  const button = $("#copy-command");
  if (button) {
    const old = button.textContent;
    button.textContent = "Copied ✓";
    setTimeout(() => { button.textContent = old; }, 1800);
  }
}

export async function loadBriefingStatus() {
  const status = $("#briefing-status");
  const link = $("#briefing-link");
  if (!status) return;
  try {
    const latest = await api("/api/briefing/latest");
    status.textContent = `Latest: ${latest.subject} · ${latest.meeting} · ${(latest.sources || []).length} sources${latest.offline ? " · offline fixture" : ""}.`;
    if (link) {
      link.hidden = false;
      link.href = "/api/briefing/latest.md";
    }
  } catch {
    status.textContent = "No briefing prepared yet.";
  }
}

export async function prepareBriefing() {
  const button = $("#prepare-briefing");
  const status = $("#briefing-status");
  const link = $("#briefing-link");
  const subject = ($("#briefing-subject")?.value || "").trim();
  const meetingInput = $("#briefing-meeting")?.value || "";
  if (!subject || !meetingInput) {
    status.textContent = "Add a company or person and a meeting time first.";
    return;
  }
  const when = new Date(meetingInput);
  const pad = (n) => String(n).padStart(2, "0");
  const offset = -when.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  const meeting = `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`
    + `T${pad(when.getHours())}:${pad(when.getMinutes())}:00`
    + `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Researching…";
  status.textContent = `Researching ${subject} through Tavily and Bifrost...`;
  try {
    const result = await api("/api/dev/briefing", {
      method: "POST",
      body: JSON.stringify({ subject, meeting }),
    });
    status.textContent = `Briefing ready: ${result.subject} · ${result.meeting} · ${(result.sources || []).length} sources${result.offline ? " · offline fixture" : ""}.`;
    if (link) {
      link.hidden = false;
      link.href = `/api/briefing/latest.md?ts=${Date.now()}`;
    }
    await refresh();
  } catch (error) {
    status.textContent = `Briefing failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}
