/* switch-world dashboard — vanilla, no chart library.
   Data is rendered with textContent; only fixed markup uses innerHTML. */

const $ = (sel, root = document) => root.querySelector(sel);
const SECRET_KEY = "user-leaving-city";
const SEQ_STEPS = 5;

const state = {
  data: null,
  theme: initialTheme(),
};

function initialTheme() {
  const param = new URLSearchParams(location.search).get("theme");
  if (param === "light" || param === "dark") return param;
  return readTheme();
}

function readTheme() {
  try {
    return localStorage.getItem("sw-theme") || "dark";
  } catch {
    return "dark";
  }
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  const button = $("#theme-toggle");
  if (button) button.textContent = theme === "dark" ? "Light" : "Dark";
  try {
    localStorage.setItem("sw-theme", theme);
  } catch {
    /* private mode: keep the in-memory theme */
  }
}

function showError(message) {
  const box = $("#error");
  if (!message) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : text || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function formatClock(iso) {
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

function formatTime(iso) {
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

function firstName(name) {
  return (name || "").split(" ")[0];
}

function sourceLabel(cell) {
  if (!cell) return "";
  if (cell.source_kind === "character") return cell.source_id;
  if (cell.source_kind === "user") return "user";
  if (cell.source_kind === "event") return "event";
  return "obs";
}

function seqStep(confidence) {
  const n = Math.round(Number(confidence) * SEQ_STEPS);
  return Math.max(0, Math.min(SEQ_STEPS, n));
}

/* ---- tooltip ---------------------------------------------------------- */

const tooltip = $("#tooltip");

function showTip(target, lines) {
  tooltip.replaceChildren();
  lines.forEach((line, index) => {
    if (index === 0 && line.value) {
      const value = document.createElement("div");
      value.className = "tip-value";
      value.textContent = line.value;
      tooltip.appendChild(value);
      if (line.label) {
        const label = document.createElement("div");
        label.className = "tip-label";
        label.textContent = line.label;
        tooltip.appendChild(label);
      }
      return;
    }
    const row = document.createElement("div");
    row.className = "tip-line";
    if (line.label) {
      const label = document.createElement("span");
      label.className = "tip-label";
      label.textContent = line.label + " ";
      row.appendChild(label);
    }
    const sub = document.createElement("span");
    sub.className = "tip-sub";
    sub.textContent = line.sub || "";
    row.appendChild(sub);
    tooltip.appendChild(row);
  });
  tooltip.hidden = false;
  const rect = target.getBoundingClientRect();
  const width = tooltip.offsetWidth;
  const height = tooltip.offsetHeight;
  let left = rect.left + rect.width / 2 - width / 2;
  let top = rect.top - height - 8;
  if (top < 8) top = rect.bottom + 8;
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
  top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTip() {
  tooltip.hidden = true;
}

function bindTip(element, lines) {
  element.addEventListener("mouseenter", () => showTip(element, lines));
  element.addEventListener("focus", () => showTip(element, lines));
  element.addEventListener("mouseleave", hideTip);
  element.addEventListener("blur", hideTip);
}

/* ---- rendering -------------------------------------------------------- */

function render(data) {
  renderHero(data);
  renderKpis(data);
  renderMatrix(data);
  renderRelationships();
  renderFeed(data);
}

function renderHero(data) {
  const row = (data.matrix || []).find((r) => r.key === SECRET_KEY);
  const holders = row ? Object.entries(row.holders) : [];
  const names = Object.fromEntries(data.characters.map((c) => [c.id, firstName(c.name)]));
  $("#hero-value").textContent = String(holders.length);
  if (!holders.length) {
    $("#hero-sub").textContent = "Tell Alice a secret to begin.";
    return;
  }
  $("#hero-sub").textContent = holders
    .map(([id, cell]) => `${names[id] || id} ${Number(cell.confidence).toFixed(2)} (${sourceLabel(cell)})`)
    .join(" · ");
}

function renderKpis(data) {
  $("#kpi-clock").textContent = formatClock(data.clock.now);
  $("#kpi-beliefs").textContent = String(data.beliefs.length);
  $("#kpi-events").textContent = String(data.events.length);
  $("#kpi-relationships").textContent = String(data.relationships.length);
}

function renderMatrix(data) {
  const head = $("#matrix-head");
  const body = $("#matrix-body");
  head.replaceChildren();
  body.replaceChildren();

  const characters = data.characters || [];
  const first = document.createElement("th");
  first.scope = "col";
  first.textContent = "Proposition";
  head.appendChild(first);
  const names = Object.fromEntries(characters.map((c) => [c.id, firstName(c.name)]));
  characters.forEach((character) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.className = "character";
    th.textContent = names[character.id] || character.id;
    head.appendChild(th);
  });

  (data.matrix || []).forEach((row) => {
    const tr = document.createElement("tr");

    const label = document.createElement("td");
    label.className = "row-label";
    label.textContent = row.label;
    tr.appendChild(label);

    characters.forEach((character) => {
      const cell = row.holders[character.id];
      const td = document.createElement("td");
      if (!cell) {
        td.className = "cell empty";
        td.textContent = "—";
        td.setAttribute("aria-label", `${names[character.id] || character.id}: no belief`);
        tr.appendChild(td);
        return;
      }
      const conf = Number(cell.confidence);
      td.className = `cell seq-${seqStep(conf)}`;
      td.tabIndex = 0;

      const value = document.createElement("span");
      value.className = "conf";
      value.textContent = conf.toFixed(2);
      td.appendChild(value);

      const src = document.createElement("span");
      src.className = "src";
      src.textContent = sourceLabel(cell);
      td.appendChild(src);

      const holder = names[character.id] || character.id;
      td.setAttribute(
        "aria-label",
        `${holder}: ${conf.toFixed(2)} confidence, source ${sourceLabel(cell)}, ${cell.visibility}`
      );
      bindTip(td, [
        { value: `${Math.round(conf * 100)}%`, label: "confidence" },
        { label: "holder", sub: holder },
        { label: "proposition", sub: cell.proposition },
        { label: "source", sub: cell.source },
        { label: "visibility", sub: cell.visibility },
        { label: "learned", sub: formatClock(cell.learned_at) },
      ]);
      tr.appendChild(td);
    });

    body.appendChild(tr);
  });
}

function relationshipRow(edge, fromId, toId, names) {
  const row = document.createElement("div");
  row.className = "rel-row";

  const name = document.createElement("div");
  name.className = "rel-name";
  name.textContent = `${names[fromId] || fromId} → ${toId === "user" ? "You" : names[toId] || toId}`;
  row.appendChild(name);

  const bars = document.createElement("div");
  bars.className = "rel-bars";
  const values = [
    ["trust", Number(edge.trust), "trust"],
    ["closeness", Number(edge.closeness), "closeness"],
    ["tension", Number(edge.tension), "tension"],
  ];
  values.forEach(([label, value, cssClass]) => {
    const line = document.createElement("div");
    line.className = "rel-bar";
    line.tabIndex = 0;
    line.setAttribute(
      "aria-label",
      `${names[fromId] || fromId} to ${toId === "user" ? "you" : names[toId] || toId}: ${label} ${value.toFixed(2)}`
    );

    const text = document.createElement("span");
    text.className = "rel-label";
    text.textContent = label;
    line.appendChild(text);

    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = `fill ${cssClass}`;
    fill.style.width = `${Math.max(0, Math.min(100, value * 100))}%`;
    track.appendChild(fill);
    line.appendChild(track);

    const number = document.createElement("span");
    number.className = "rel-value";
    number.textContent = value.toFixed(2);
    line.appendChild(number);

    bindTip(line, [
      { value: value.toFixed(2), label },
      { label: "edge", sub: `${names[fromId] || fromId} → ${toId === "user" ? "you" : names[toId] || toId}` },
      { label: "shared secrets", sub: String(edge.shared_secret_count || 0) },
    ]);
    bars.appendChild(line);
  });
  row.appendChild(bars);
  return row;
}

function renderRelationships() {
  if (!state.data) return;
  const data = state.data;
  const selected = $("#rel-view").value;
  const names = Object.fromEntries(data.characters.map((c) => [c.id, firstName(c.name)]));
  const others = data.characters.map((c) => c.id).filter((id) => id !== selected).concat("user");
  const list = $("#relationships");
  list.replaceChildren();

  const edges = new Map(
    data.relationships.filter((edge) => edge.a === selected).map((edge) => [edge.b, edge])
  );

  others.forEach((other) => {
    const edge = edges.get(other) || {
      a: selected,
      b: other,
      trust: 0.5,
      closeness: 0.5,
      tension: 0,
      shared_secret_count: 0,
    };
    list.appendChild(relationshipRow(edge, selected, other, names));
  });

  const tbody = $("#rel-table tbody");
  tbody.replaceChildren();
  others.forEach((other) => {
    const edge = edges.get(other) || {
      trust: 0.5,
      closeness: 0.5,
      tension: 0,
      shared_secret_count: 0,
    };
    const tr = document.createElement("tr");
    [
      other === "user" ? "You" : names[other] || other,
      Number(edge.trust).toFixed(2),
      Number(edge.closeness).toFixed(2),
      Number(edge.tension).toFixed(2),
      String(edge.shared_secret_count || 0),
    ].forEach((value, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
}

function renderFeed(data) {
  const feed = $("#feed");
  feed.replaceChildren();
  const events = data.events || [];
  $("#feed-count").textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;
  if (!events.length) {
    const empty = document.createElement("li");
    empty.className = "feed-empty";
    empty.textContent = "No events yet.";
    feed.appendChild(empty);
    return;
  }
  events.forEach((event) => {
    const li = document.createElement("li");
    const time = document.createElement("span");
    time.className = "feed-time";
    time.textContent = formatTime(event.created_at);
    li.appendChild(time);

    const kind = document.createElement("span");
    kind.className = "feed-kind";
    kind.textContent = String(event.kind || "event").replaceAll("_", " ");
    li.appendChild(kind);

    const text = document.createElement("span");
    text.className = "feed-text";
    text.textContent = event.summary;
    li.appendChild(text);
    feed.appendChild(li);
  });
}

/* ---- actions ---------------------------------------------------------- */

async function refresh() {
  const main = $("#main");
  main.classList.add("refreshing");
  try {
    const data = await api("/api/state");
    state.data = data;
    render(data);
    showError(null);
  } catch (error) {
    showError(`Cannot reach the world engine: ${error.message}`);
  } finally {
    main.classList.remove("refreshing");
  }
}

async function tellAlice() {
  const secret = $("#secret").value.trim();
  if (!secret) {
    $("#status").textContent = "Write a secret first.";
    return;
  }
  try {
    await api("/api/dev/tell-alice", {
      method: "POST",
      body: JSON.stringify({ secret, key: SECRET_KEY }),
    });
    $("#status").textContent = "Alice recorded the secret. Check the matrix.";
    await refresh();
  } catch (error) {
    $("#status").textContent = `Tell Alice failed: ${error.message}`;
  }
}

async function runCafe() {
  try {
    const result = await api("/api/dev/run-cafe", { method: "POST", body: "{}" });
    $("#status").textContent = result.shared
      ? "The café beat ran. Emily now knows, with a lower confidence."
      : "Alice chose not to share. The scene card records a non-disclosure.";
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Café beat failed: ${error.message}`;
  }
}

async function resetWorld() {
  if (!window.confirm("Reset the world state? This re-seeds the demo.")) return;
  try {
    await api("/api/dev/reset", { method: "POST", body: "{}" });
    $("#status").textContent = "World reset to the seed state.";
    $("#card-preview").hidden = true;
    $("#card-preview").textContent = "";
    $("#card-path").textContent = "No card loaded yet.";
    await refresh();
  } catch (error) {
    $("#status").textContent = `Reset failed: ${error.message}`;
  }
}

async function loadSceneCard() {
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

/* ---- wiring ----------------------------------------------------------- */

setTheme(state.theme);
$("#theme-toggle").addEventListener("click", () => {
  setTheme(state.theme === "dark" ? "light" : "dark");
});
$("#rel-view").addEventListener("change", renderRelationships);
$("#tell-alice").addEventListener("click", tellAlice);
$("#run-cafe").addEventListener("click", runCafe);
$("#reset").addEventListener("click", resetWorld);
$("#load-card").addEventListener("click", loadSceneCard);

window.addEventListener("scroll", hideTip, { passive: true });
window.addEventListener("resize", hideTip);

refresh();
setInterval(() => {
  if (!document.hidden) refresh();
}, 2500);
