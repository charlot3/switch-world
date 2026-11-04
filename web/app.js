/* switch-world dashboard — vanilla JS, no framework, no chart library.
   Data is rendered with textContent; only fixed skeleton markup uses templates. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const CAST = window.SWITCH_CAST;
const ORDER = window.SWITCH_ORDER;
const SECRET_KEY = "user-leaving-city";
const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  data: null,
  view: initialView(),
  selected: "alice",
  lineId: null,
  typedKey: null,
  typingKey: null,
  typing: null,
  theme: initialTheme(),
  motion: initialMotion(),
};

function initialTheme() {
  const param = new URLSearchParams(location.search).get("theme");
  if (param === "light" || param === "dark") return param;
  try {
    return localStorage.getItem("sw-theme") || "dark";
  } catch {
    return "dark";
  }
}

function initialMotion() {
  try {
    return localStorage.getItem("sw-motion") !== "off";
  } catch {
    return true;
  }
}

function initialView() {
  const param = new URLSearchParams(location.search).get("view");
  return ["story", "tree", "ledger", "settings"].includes(param) ? param : "story";
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  const label = theme === "dark" ? "Twilight" : "Daylight";
  $("#theme-label").textContent = label;
  $("#theme-toggle-2").textContent = label;
  try {
    localStorage.setItem("sw-theme", theme);
  } catch {
    /* private mode */
  }
}

function setMotion(on) {
  state.motion = on;
  document.documentElement.dataset.motion = on ? "on" : "off";
  const toggle = $("#motion-toggle");
  if (toggle) toggle.checked = on;
  try {
    localStorage.setItem("sw-motion", on ? "on" : "off");
  } catch {
    /* private mode */
  }
  if (on) makePetals();
  else $("#petals").replaceChildren();
}

function makePetals() {
  const host = $("#petals");
  host.replaceChildren();
  if (!state.motion || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (let i = 0; i < 14; i += 1) {
    const petal = document.createElement("span");
    petal.className = "petal";
    petal.style.left = `${Math.random() * 100}%`;
    petal.style.animationDuration = `${10 + Math.random() * 14}s`;
    petal.style.animationDelay = `${-Math.random() * 20}s`;
    const size = 6 + Math.random() * 8;
    petal.style.width = `${size}px`;
    petal.style.height = `${size}px`;
    host.appendChild(petal);
  }
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

function castIdForName(name) {
  const needle = String(name || "").trim().toLowerCase();
  return ORDER.find((id) => {
    const c = CAST[id];
    return c.name.toLowerCase() === needle || c.name.split(" ")[0].toLowerCase() === needle;
  }) || null;
}

function dialogueEvents(data) {
  return (data.events || [])
    .filter((event) => event.kind === "dialogue")
    .map((event) => {
      const match = String(event.summary || "").match(/^([^:]+):\s*([\s\S]*)$/);
      if (!match) return null;
      return {
        id: event.id,
        name: match[1].trim(),
        castId: castIdForName(match[1]),
        text: match[2].trim(),
        ts: event.created_at,
      };
    })
    .filter(Boolean);
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

/* ---- story ------------------------------------------------------------ */

function typeLine(element, text, key) {
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

function renderStory(data) {
  const lines = dialogueEvents(data).slice(-8);
  if (state.lineId != null && !lines.some((line) => line.id === state.lineId)) {
    state.lineId = null;
  }
  const castLines = lines.filter((item) => item.castId === state.selected);
  const line = state.lineId != null
    ? lines.find((item) => item.id === state.lineId)
    : (castLines[castLines.length - 1] || null);
  if (line && state.lineId != null && line.castId) state.selected = line.castId;
  const cast = CAST[(line && line.castId) || state.selected] || CAST[state.selected];

  const scene = $(".scene");
  scene.style.setProperty("--scene-color", cast.color);
  const portrait = $("#scene-portrait");
  portrait.src = cast.portrait;
  portrait.alt = `${cast.name} portrait`;
  $("#scene-name").textContent = cast.name;
  $("#scene-jp").textContent = cast.jp;
  $("#scene-mood").textContent = cast.mood;
  $("#scene-stamp").textContent = "SCENE · THE CAFÉ";
  $("#scene-caption").textContent = line
    ? `${formatClock(line.ts)} · late autumn`
    : "18:30 · a Tuesday in late autumn";
  $("#scene-dm").href = cast.dm;

  const text = line ? line.text : cast.quote;
  typeLine($("#scene-line"), text, line ? `line:${line.id}` : `quote:${cast.id}`);

  const rail = $("#scene-rail");
  rail.replaceChildren();
  lines.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-chip" + ((line && line.id === item.id) ? " is-active" : "");
    button.textContent = `${firstName(item.name)}: ${item.text}`;
    button.title = item.text;
    button.addEventListener("click", () => {
      state.lineId = item.id;
      if (item.castId) state.selected = item.castId;
      renderStory(state.data);
    });
    rail.appendChild(button);
  });

  renderHero(data);
  renderCast(data);
}

function renderHero(data) {
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
    heart.textContent = index < holders.length ? "♥" : "♡";
  });
}

function chemistryFor(data, id) {
  const edge = (data.relationships || []).find((e) => e.a === id && e.b === "user");
  if (!edge) return 0.4;
  return Math.max(0, Math.min(1, (edge.trust + edge.closeness) / 2 - edge.tension / 2));
}

function renderCast(data) {
  const grid = $("#cast-grid");
  grid.replaceChildren();
  ORDER.forEach((id) => {
    const cast = CAST[id];
    const card = document.createElement("article");
    card.className = "cast-card" + (state.selected === id ? " is-selected" : "");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `Open ${cast.name} in the story view`);
    card.addEventListener("click", () => {
      state.selected = id;
      state.lineId = null;
      renderStory(state.data);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.selected = id;
        state.lineId = null;
        renderStory(state.data);
      }
    });

    const art = document.createElement("div");
    art.className = "cast-art";
    const img = document.createElement("img");
    img.src = cast.portrait;
    img.alt = `${cast.name} portrait`;
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
    jp.textContent = cast.jp;
    info.appendChild(jp);
    const tagline = document.createElement("p");
    tagline.className = "cast-tagline";
    tagline.textContent = cast.tagline;
    info.appendChild(tagline);

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
    const filled = Math.round(chemistryFor(data, id) * 5);
    hearts.textContent = "♥".repeat(filled) + "♡".repeat(5 - filled);
    hearts.setAttribute("aria-label", `${filled} of 5 chemistry`);
    foot.appendChild(hearts);
    const dm = document.createElement("a");
    dm.className = "cast-dm";
    dm.href = cast.dm;
    dm.target = "_blank";
    dm.rel = "noopener";
    dm.textContent = "DM ↗";
    foot.appendChild(dm);
    info.appendChild(foot);
    card.appendChild(info);
    grid.appendChild(card);
  });
}

/* ---- world tree ------------------------------------------------------- */

function svgEl(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value != null) node.setAttribute(key, String(value));
  });
  return node;
}

function addText(parent, x, y, text, cls) {
  const node = svgEl("text", { x, y, class: cls });
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function edgeClass(trust) {
  if (trust >= 0.7) return "is-high";
  if (trust >= 0.4) return "is-mid";
  return "is-low";
}

function renderTree(data) {
  const svg = $("#world-tree");
  svg.replaceChildren();
  const defs = svgEl("defs");
  svg.appendChild(defs);

  const user = { x: 500, y: 540 };
  const positions = {
    alice: { x: 160, y: 320 },
    emily: { x: 390, y: 225 },
    sophia: { x: 610, y: 225 },
    mia: { x: 840, y: 320 },
  };
  const secret = { x: 500, y: 86 };

  ORDER.forEach((id) => {
    const clip = svgEl("clipPath", { id: `clip-${id}` });
    const circle = svgEl("circle", { cx: positions[id].x, cy: positions[id].y, r: 52 });
    clip.appendChild(circle);
    defs.appendChild(clip);
  });
  const glow = svgEl("filter", { id: "node-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" });
  const blur = svgEl("feGaussianBlur", { stdDeviation: "10" });
  glow.appendChild(blur);
  defs.appendChild(glow);

  const edges = svgEl("g");
  svg.appendChild(edges);
  ORDER.forEach((id) => {
    const pos = positions[id];
    const edge = (data.relationships || []).find((e) => e.a === id && e.b === "user") || {
      trust: 0.4, closeness: 0.4, tension: 0,
    };
    const trust = Number(edge.trust);
    const closeness = Number(edge.closeness);
    const tension = Number(edge.tension);
    const path = svgEl("path", {
      d: `M ${user.x} ${user.y} C ${user.x} ${user.y - 120}, ${pos.x} ${pos.y + 170}, ${pos.x} ${pos.y + 54}`,
      class: `tree-edge ${edgeClass(trust)}`,
      "stroke-width": 2 + closeness * 6,
      "stroke-dasharray": tension > 0.35 ? "6 7" : null,
      tabindex: "0",
      role: "img",
      "aria-label": `${firstName(CAST[id].name)} to you: trust ${trust.toFixed(2)}, closeness ${closeness.toFixed(2)}, tension ${tension.toFixed(2)}`,
    });
    bindTip(path, [
      { value: trust.toFixed(2), label: "trust" },
      { label: "edge", sub: `${firstName(CAST[id].name)} → you` },
      { label: "closeness", sub: closeness.toFixed(2) },
      { label: "tension", sub: tension.toFixed(2) },
    ]);
    edges.appendChild(path);
  });

  const row = (data.matrix || []).find((item) => item.key === SECRET_KEY);
  const holders = row ? row.holders : {};
  Object.entries(holders).forEach(([id, cell]) => {
    const pos = positions[id];
    if (!pos) return;
    const path = svgEl("path", {
      d: `M ${secret.x} ${secret.y + 35} C ${secret.x} ${secret.y + 130}, ${pos.x} ${pos.y - 160}, ${pos.x} ${pos.y - 54}`,
      class: "tree-edge is-secret",
      "stroke-width": 2,
      tabindex: "0",
      role: "img",
      "aria-label": `the secret reaches ${firstName(CAST[id].name)} with confidence ${Number(cell.confidence).toFixed(2)}`,
    });
    bindTip(path, [
      { value: Number(cell.confidence).toFixed(2), label: "confidence" },
      { label: "secret →", sub: firstName(CAST[id].name) },
      { label: "source", sub: sourceLabel(cell) },
    ]);
    edges.appendChild(path);
    addText(edges, (secret.x + pos.x) / 2, (secret.y + pos.y) / 2 - 6, Number(cell.confidence).toFixed(2), "tree-sub");
  });

  const nodes = svgEl("g");
  svg.appendChild(nodes);

  const userGroup = svgEl("g", { class: "tree-node" });
  const userGlow = svgEl("circle", { cx: user.x, cy: user.y, r: 54, fill: "var(--rose)", opacity: "0.12", filter: "url(#node-glow)" });
  userGroup.appendChild(userGlow);
  userGroup.appendChild(svgEl("circle", { cx: user.x, cy: user.y, r: 40, fill: "var(--surface-2)", stroke: "var(--rose)", "stroke-width": "2" }));
  const you = addText(userGroup, user.x, user.y + 6, "you", "tree-user-label");
  you.setAttribute("fill", "var(--ink)");
  addText(userGroup, user.x, user.y + 64, "the fifth person", "tree-sub");
  nodes.appendChild(userGroup);

  ORDER.forEach((id) => {
    const cast = CAST[id];
    const pos = positions[id];
    const group = svgEl("g", {
      class: `tree-node${state.selected === id ? " is-selected" : ""}`,
      tabindex: "0",
      role: "button",
      "aria-label": `${cast.name}, ${cast.role}. Open details.`,
    });
    const halo = svgEl("circle", { cx: pos.x, cy: pos.y, r: 66, fill: cast.color, opacity: "0.14", filter: "url(#node-glow)" });
    group.appendChild(halo);
    group.appendChild(svgEl("circle", { cx: pos.x, cy: pos.y, r: 52, class: "node-ring" }));
    group.appendChild(svgEl("image", {
      href: cast.avatar,
      x: pos.x - 52,
      y: pos.y - 52,
      width: 104,
      height: 104,
      "clip-path": `url(#clip-${id})`,
      preserveAspectRatio: "xMidYMid slice",
      class: "node-image",
    }));
    addText(group, pos.x, pos.y + 76, firstName(cast.name), "tree-label");
    addText(group, pos.x, pos.y + 91, cast.role, "tree-sub");
    group.addEventListener("click", () => {
      state.selected = id;
      renderTree(state.data);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.selected = id;
        renderTree(state.data);
      }
    });
    bindTip(group, [
      { value: cast.role, label: "" },
      { label: "mood", sub: cast.mood },
      { label: "tagline", sub: cast.tagline },
      { label: "DM", sub: cast.dm.replace("http://", "") },
    ]);
    nodes.appendChild(group);
  });

  const secretGroup = svgEl("g", { class: "tree-node" });
  secretGroup.appendChild(svgEl("rect", { x: secret.x - 92, y: secret.y - 34, width: 184, height: 68, rx: 18, fill: "var(--surface-2)", stroke: "var(--lav)", "stroke-width": "1.5", opacity: "0.96" }));
  addText(secretGroup, secret.x, secret.y - 8, "THE SECRET", "tree-secret-label");
  addText(secretGroup, secret.x, secret.y + 22, `${Object.keys(holders).length} / 4 know`, "tree-secret-count");
  nodes.appendChild(secretGroup);

  renderTreePanel(data);
  renderTreeTable(data);
}

function renderTreePanel(data) {
  const panel = $("#tree-panel");
  panel.replaceChildren();
  const cast = CAST[state.selected];
  const header = document.createElement("div");
  const name = document.createElement("h3");
  name.textContent = cast.name;
  header.appendChild(name);
  const jp = document.createElement("span");
  jp.className = "jp";
  jp.textContent = cast.jp;
  header.appendChild(jp);
  const sub = document.createElement("p");
  sub.className = "panel-sub";
  sub.textContent = `${cast.role} · ${cast.mood}`;
  header.appendChild(sub);
  panel.appendChild(header);

  const tagline = document.createElement("p");
  tagline.className = "tiny";
  tagline.textContent = cast.tagline;
  panel.appendChild(tagline);

  const beliefs = (data.matrix || [])
    .map((row) => ({ row, cell: row.holders[state.selected] }))
    .filter((item) => item.cell)
    .slice(0, 6);
  if (beliefs.length) {
    beliefs.forEach(({ row, cell }) => {
      const item = document.createElement("div");
      item.className = "tree-belief";
      const title = document.createElement("b");
      title.textContent = row.label;
      item.appendChild(title);
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `${Number(cell.confidence).toFixed(2)} · ${sourceLabel(cell)} · ${cell.visibility}`;
      item.appendChild(meta);
      panel.appendChild(item);
    });
  } else {
    const empty = document.createElement("p");
    empty.className = "tiny";
    empty.textContent = "No beliefs recorded for this character yet.";
    panel.appendChild(empty);
  }

  const rels = document.createElement("div");
  rels.className = "rel-mini";
  const others = ORDER.filter((id) => id !== state.selected).concat("user");
  others.forEach((other) => {
    const edge = (data.relationships || []).find((e) => e.a === state.selected && e.b === other) || {
      trust: 0.5, closeness: 0.5, tension: 0,
    };
    const row = document.createElement("div");
    row.className = "rel-bar";
    const label = document.createElement("span");
    label.className = "rel-label";
    label.textContent = other === "user" ? "you" : firstName(CAST[other].name);
    row.appendChild(label);
    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = "fill trust";
    fill.style.width = `${Math.max(0, Math.min(100, Number(edge.trust) * 100))}%`;
    track.appendChild(fill);
    row.appendChild(track);
    const value = document.createElement("span");
    value.className = "rel-value";
    value.textContent = Number(edge.trust).toFixed(2);
    row.appendChild(value);
    rels.appendChild(row);
  });
  panel.appendChild(rels);

  const dm = document.createElement("a");
  dm.className = "btn ghost small";
  dm.href = cast.dm;
  dm.target = "_blank";
  dm.rel = "noopener";
  dm.textContent = "DM this character ↗";
  dm.style.marginTop = "12px";
  panel.appendChild(dm);
}

function renderTreeTable(data) {
  const host = $("#tree-table");
  host.replaceChildren();
  const table = document.createElement("table");
  table.className = "rel-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["from", "to", "trust", "closeness", "tension", "secrets"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  (data.relationships || []).forEach((edge) => {
    const tr = document.createElement("tr");
    [edge.a, edge.b, Number(edge.trust).toFixed(2), Number(edge.closeness).toFixed(2), Number(edge.tension).toFixed(2), String(edge.shared_secret_count || 0)].forEach((value, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  host.appendChild(table);
}

/* ---- secret ledger ---------------------------------------------------- */

function sourceLabel(cell) {
  if (!cell) return "";
  if (cell.source_kind === "character") return cell.source_id;
  if (cell.source_kind === "user") return "user";
  if (cell.source_kind === "event") return "event";
  return "obs";
}

function seqStep(confidence) {
  const n = Math.round(Number(confidence) * 5);
  return Math.max(0, Math.min(5, n));
}

function renderLedger(data) {
  renderMatrix(data);
  renderRelationships(data);
  renderFeed(data);
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
      td.setAttribute("aria-label", `${holder}: ${conf.toFixed(2)} confidence, source ${sourceLabel(cell)}, ${cell.visibility}`);
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

function renderRelationships(data) {
  const selected = $("#rel-view").value;
  const names = Object.fromEntries((data.characters || []).map((c) => [c.id, firstName(c.name)]));
  const others = (data.characters || []).map((c) => c.id).filter((id) => id !== selected).concat("user");
  const list = $("#relationships");
  list.replaceChildren();
  const edges = new Map((data.relationships || []).filter((edge) => edge.a === selected).map((edge) => [edge.b, edge]));
  others.forEach((other) => {
    const edge = edges.get(other) || { a: selected, b: other, trust: 0.5, closeness: 0.5, tension: 0, shared_secret_count: 0 };
    const row = document.createElement("div");
    row.className = "rel-row";
    const name = document.createElement("div");
    name.className = "rel-name";
    name.textContent = `${names[selected] || selected} → ${other === "user" ? "You" : names[other] || other}`;
    row.appendChild(name);
    const bars = document.createElement("div");
    bars.className = "rel-bars";
    [["trust", Number(edge.trust)], ["closeness", Number(edge.closeness)], ["tension", Number(edge.tension)]].forEach(([label, value]) => {
      const line = document.createElement("div");
      line.className = "rel-bar";
      line.tabIndex = 0;
      line.setAttribute("aria-label", `${label} ${value.toFixed(2)}`);
      const text = document.createElement("span");
      text.className = "rel-label";
      text.textContent = label;
      line.appendChild(text);
      const track = document.createElement("div");
      track.className = "track";
      const fill = document.createElement("div");
      fill.className = `fill ${label}`;
      fill.style.width = `${Math.max(0, Math.min(100, value * 100))}%`;
      track.appendChild(fill);
      line.appendChild(track);
      const number = document.createElement("span");
      number.className = "rel-value";
      number.textContent = value.toFixed(2);
      line.appendChild(number);
      bindTip(line, [
        { value: value.toFixed(2), label },
        { label: "edge", sub: `${names[selected] || selected} → ${other === "user" ? "you" : names[other] || other}` },
        { label: "shared secrets", sub: String(edge.shared_secret_count || 0) },
      ]);
      bars.appendChild(line);
    });
    row.appendChild(bars);
    list.appendChild(row);
  });

  const tbody = $("#rel-table tbody");
  tbody.replaceChildren();
  others.forEach((other) => {
    const edge = edges.get(other) || { trust: 0.5, closeness: 0.5, tension: 0, shared_secret_count: 0 };
    const tr = document.createElement("tr");
    [other === "user" ? "You" : names[other] || other, Number(edge.trust).toFixed(2), Number(edge.closeness).toFixed(2), Number(edge.tension).toFixed(2), String(edge.shared_secret_count || 0)].forEach((value, index) => {
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

/* ---- settings --------------------------------------------------------- */

function renderSettings() {
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

const VIEW_META = {
  story: { eyebrow: "Tonight at the café", title: "Story" },
  tree: { eyebrow: "The shape of the secret", title: "World Tree" },
  ledger: { eyebrow: "The god view", title: "Secret Ledger" },
  settings: { eyebrow: "The stage", title: "Settings" },
};

function setView(view) {
  state.view = view;
  $$(".rail-link").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  $$(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `view-${view}`);
  });
  const meta = VIEW_META[view] || VIEW_META.story;
  $("#view-eyebrow").textContent = meta.eyebrow;
  $("#view-title").textContent = meta.title;
  if (state.data) render(state.data);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function render(data) {
  $("#rail-clock").textContent = formatClock(data.clock.now);
  if (state.view === "story") renderStory(data);
  if (state.view === "tree") renderTree(data);
  if (state.view === "ledger") renderLedger(data);
  if (state.view === "settings") renderSettings(data);
}

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

/* ---- actions ---------------------------------------------------------- */

async function tellAlice() {
  const secret = $("#secret").value.trim();
  if (!secret) {
    $("#status").textContent = "Write a secret first.";
    return;
  }
  try {
    await api("/api/dev/tell-alice", { method: "POST", body: JSON.stringify({ secret, key: SECRET_KEY }) });
    $("#status").textContent = "Alice recorded the secret. Check the ledger.";
    await refresh();
  } catch (error) {
    $("#status").textContent = `Tell Alice failed: ${error.message}`;
  }
}

async function runCafe() {
  try {
    const result = await api("/api/dev/run-cafe", { method: "POST", body: "{}" });
    $("#status").textContent = result.shared
      ? "Local beat ran. Emily now knows, with a lower confidence."
      : "Local beat ran. Alice chose not to share.";
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Local beat failed: ${error.message}`;
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

async function copyLiveCommand() {
  const command = "uv run director --switch";
  try {
    await navigator.clipboard.writeText(command);
    $("#status").textContent = `Copied: ${command}. Run it in the switch-world terminal.`;
  } catch {
    $("#status").textContent = `Run in the terminal: ${command}`;
  }
  const button = $("#scene-run");
  const old = button.textContent;
  button.textContent = "Copied ✓";
  setTimeout(() => { button.textContent = old; }, 1800);
}

function nextLine() {
  const lines = dialogueEvents(state.data || {});
  if (!lines.length) return;
  const index = lines.findIndex((line) => line.id === state.lineId);
  const next = lines[(index + 1 + lines.length) % lines.length];
  state.lineId = next.id;
  if (next.castId) state.selected = next.castId;
  renderStory(state.data);
}

/* ---- wiring ----------------------------------------------------------- */

setTheme(state.theme);
setMotion(state.motion);
setView(state.view);

$$(".rail-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
$("#theme-toggle").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
$("#theme-toggle-2").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
$("#motion-toggle").addEventListener("change", (event) => setMotion(event.target.checked));
$("#rel-view").addEventListener("change", () => {
  if (state.data) renderRelationships(state.data);
});
$("#scene-next").addEventListener("click", nextLine);
$("#scene-run").addEventListener("click", copyLiveCommand);
$("#tell-alice").addEventListener("click", tellAlice);
$("#run-cafe").addEventListener("click", runCafe);
$("#reset").addEventListener("click", resetWorld);
$("#load-card").addEventListener("click", loadSceneCard);
$("#copy-command").addEventListener("click", copyLiveCommand);

window.addEventListener("scroll", hideTip, { passive: true });
window.addEventListener("resize", hideTip);

if (state.data == null) {
  refresh();
  setInterval(() => {
    if (!document.hidden) refresh();
  }, 2500);
}
