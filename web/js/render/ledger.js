/* World Tree, Secret Ledger, canon and the character-sheet modal. */

import {
  edgeClass,
  firstName,
  firstNameOf,
  formatClock,
  formatTime,
  normalizeConnection,
  seqStep,
  sourceLabel,
} from "../format.js";
import { state } from "../state.js";
import { CAST_ORDER as ORDER } from "../vocab.js";
import { $, CAST, SECRET_KEY, addText, bindTip, svgEl } from "./dom.js";
import { castArtFor, outfitArtFor, scenarioConnections } from "./stage.js";
import { resetPhoneFor } from "./phone.js";




export function renderCastConnectionsLayer(layer, positions, connections) {
  const seen = new Set();
  let drawn = 0;
  (Array.isArray(connections) ? connections : []).forEach((raw) => {
    const conn = normalizeConnection(raw);
    if (!conn || !conn.a || !conn.b || conn.a === conn.b) return;
    if (!CAST[conn.a] || !CAST[conn.b]) return;
    const key = [conn.a, conn.b].sort().join("|");
    if (seen.has(key)) return;
    seen.add(key);
    const from = positions[conn.a];
    const to = positions[conn.b];
    if (!from || !to) return;
    const midX = (from.x + to.x) / 2;
    const midY = (from.y + to.y) / 2;
    const lift = Math.abs(from.x - to.x) > 220 ? 70 : 112;
    const path = svgEl("path", {
      d: `M ${from.x} ${from.y} Q ${midX} ${midY - lift} ${to.x} ${to.y}`,
      class: `tree-edge ${edgeClass(conn.affinity)}`,
      "stroke-width": 2 + conn.affinity * 6,
      "stroke-dasharray": conn.tension > 0.35 ? "6 7" : null,
      tabindex: "0",
      role: "img",
      "aria-label": `${firstNameOf(conn.a)} and ${firstNameOf(conn.b)}: ${conn.label}, affinity ${conn.affinity.toFixed(2)}, tension ${conn.tension.toFixed(2)}`,
    });
    bindTip(path, [
      { value: conn.affinity.toFixed(2), label: "affinity" },
      { label: "edge", sub: `${firstNameOf(conn.a)} ↔ ${firstNameOf(conn.b)}` },
      { label: "label", sub: conn.label },
      { label: "tension", sub: conn.tension.toFixed(2) },
      { label: "shared secrets", sub: String(conn.shared_secret_count || 0) },
    ]);
    layer.appendChild(path);
    addText(layer, midX, midY - lift * 0.45, conn.label, "tree-sub");
    drawn += 1;
  });
  if (!drawn) addText(layer, 500, 300, "No cast connections reported yet", "tree-sub");
}

export function renderTree(data) {
  const lens = state.treeLens === "cast" ? "cast" : "user";
  const connections = scenarioConnections(data);
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

  const row = (data.matrix || []).find((item) => item.key === SECRET_KEY);
  const holders = row ? row.holders : {};

  const edges = svgEl("g");
  svg.appendChild(edges);
  if (lens === "cast") {
    renderCastConnectionsLayer(edges, positions, connections);
  } else {
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
  }

  const nodes = svgEl("g");
  svg.appendChild(nodes);

  if (lens === "user") {
    const userGroup = svgEl("g", { class: "tree-node" });
    const userGlow = svgEl("circle", { cx: user.x, cy: user.y, r: 54, fill: "var(--rose)", opacity: "0.12", filter: "url(#node-glow)" });
    userGroup.appendChild(userGlow);
    userGroup.appendChild(svgEl("circle", { cx: user.x, cy: user.y, r: 40, fill: "var(--surface-2)", stroke: "var(--rose)", "stroke-width": "2" }));
    const you = addText(userGroup, user.x, user.y + 6, "you", "tree-user-label");
    you.setAttribute("fill", "var(--ink)");
    addText(userGroup, user.x, user.y + 64, "the fifth person", "tree-sub");
    nodes.appendChild(userGroup);
  }

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
    const nodeImage = svgEl("image", {
      href: cast.avatar,
      x: pos.x - 52,
      y: pos.y - 52,
      width: 104,
      height: 104,
      "clip-path": `url(#clip-${id})`,
      preserveAspectRatio: "xMidYMid slice",
      class: "node-image",
    });
    let avatarRetried = false;
    nodeImage.addEventListener("error", () => {
      if (!avatarRetried) {
        avatarRetried = true;
        nodeImage.setAttribute("href", `${cast.avatar}?retry=1`);
        return;
      }
      nodeImage.setAttribute("href", `/static/assets/portraits/${id}-avatar.svg`);
    });
    group.appendChild(nodeImage);
    addText(group, pos.x, pos.y + 76, firstName(cast.name), "tree-label");
    addText(group, pos.x, pos.y + 91, cast.role, "tree-sub");
    group.addEventListener("click", () => {
      state.selected = id;
      resetPhoneFor(id);
      renderTree(state.data);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.selected = id;
        resetPhoneFor(id);
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

  if (lens === "user") {
    const secretGroup = svgEl("g", { class: "tree-node" });
    secretGroup.appendChild(svgEl("rect", { x: secret.x - 92, y: secret.y - 34, width: 184, height: 68, rx: 18, fill: "var(--surface-2)", stroke: "var(--lav)", "stroke-width": "1.5", opacity: "0.96" }));
    addText(secretGroup, secret.x, secret.y - 8, "THE SECRET", "tree-secret-label");
    addText(secretGroup, secret.x, secret.y + 22, `${Object.keys(holders).length} / 4 know`, "tree-secret-count");
    nodes.appendChild(secretGroup);
  }

  const keyHigh = $("#tree-key-high");
  const keyMid = $("#tree-key-mid");
  const keyLow = $("#tree-key-low");
  const keySecret = $("#tree-key-secret");
  if (keyHigh) keyHigh.textContent = lens === "cast" ? "close" : "high trust";
  if (keyMid) keyMid.textContent = lens === "cast" ? "steady" : "medium";
  if (keyLow) keyLow.textContent = lens === "cast" ? "strained / distant" : "low / tense";
  if (keySecret) keySecret.hidden = lens === "cast";

  renderTreePanel(data);
  renderTreeTable(data);
}

export function renderConnectionsPanel(panel, data, cast) {
  const title = document.createElement("p");
  title.className = "eyebrow connection-title";
  title.textContent = "cast connections";
  panel.appendChild(title);
  const connections = scenarioConnections(data)
    .map(normalizeConnection)
    .filter((conn) => conn && (conn.a === cast.id || conn.b === cast.id));
  if (!connections.length) {
    const empty = document.createElement("p");
    empty.className = "tiny";
    empty.textContent = "No cast connections reported. Load a scenario or connect the backend.";
    panel.appendChild(empty);
    return;
  }
  connections.forEach((conn) => {
    const otherId = conn.a === cast.id ? conn.b : conn.a;
    const other = CAST[otherId];
    const card = document.createElement("div");
    card.className = "connection-card";
    const head = document.createElement("div");
    head.className = "connection-head";
    const name = document.createElement("strong");
    name.textContent = other ? other.name : otherId;
    head.appendChild(name);
    const label = document.createElement("span");
    label.className = `connection-label is-${conn.label}`;
    label.textContent = conn.label;
    head.appendChild(label);
    card.appendChild(head);
    const bars = document.createElement("div");
    bars.className = "rel-bars";
    bars.appendChild(relBar("affinity", conn.affinity));
    bars.appendChild(relBar("tension", conn.tension));
    card.appendChild(bars);
    if (conn.shared_secret_count) {
      const secrets = document.createElement("span");
      secrets.className = "connection-secrets";
      secrets.textContent = `${conn.shared_secret_count} shared secret${conn.shared_secret_count === 1 ? "" : "s"}`;
      card.appendChild(secrets);
    }
    panel.appendChild(card);
  });
}

export function renderTreePanel(data) {
  const panel = $("#tree-panel");
  panel.replaceChildren();
  const cast = CAST[state.selected];
  const header = document.createElement("div");
  const name = document.createElement("h3");
  name.textContent = cast.name;
  header.appendChild(name);
  const jp = document.createElement("span");
  jp.className = "jp";
  jp.textContent = cast.route;
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

  if (state.treeLens === "cast") {
    renderConnectionsPanel(panel, data, cast);
  } else {
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
  }

  const dm = document.createElement("a");
  dm.className = "btn ghost small";
  dm.href = cast.dm;
  dm.target = "_blank";
  dm.rel = "noopener";
  dm.textContent = "DM this character ↗";
  dm.style.marginTop = "12px";
  panel.appendChild(dm);
}

export function renderTreeTable(data) {
  const host = $("#tree-table");
  host.replaceChildren();
  const table = document.createElement("table");
  table.className = "rel-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  const castLens = state.treeLens === "cast";
  const headings = castLens
    ? ["from", "to", "label", "affinity", "tension", "secrets"]
    : ["from", "to", "trust", "closeness", "tension", "secrets"];
  headings.forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  if (castLens) {
    scenarioConnections(data).map(normalizeConnection).filter(Boolean).forEach((conn) => {
      const tr = document.createElement("tr");
      [conn.a, conn.b, conn.label, conn.affinity.toFixed(2), conn.tension.toFixed(2), String(conn.shared_secret_count || 0)].forEach((value, index) => {
        const cell = document.createElement(index === 0 ? "th" : "td");
        if (index === 0) cell.scope = "row";
        cell.textContent = value;
        tr.appendChild(cell);
      });
      tbody.appendChild(tr);
    });
  } else {
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
  }
  table.appendChild(tbody);
  host.appendChild(table);
}
/* ---- secret ledger ---------------------------------------------------- */



export function renderLedger(data) {
  renderMatrix(data);
  renderRelationships(data);
  renderFeed(data);
}

export function renderMatrix(data) {
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

export function renderRelationships(data) {
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

export function renderFeed(data) {
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

/* ---- canon ------------------------------------------------------------ */

export function renderCanon(data) {
  const canon = data.canon || {};
  $("#canon-act").textContent = canon.act || "Act I — The Secret";
  $("#canon-secret").textContent = (canon.secret && canon.secret.default_text) || "—";

  const facts = $("#canon-facts");
  facts.replaceChildren();
  (canon.public_facts || []).forEach((fact) => {
    const item = document.createElement("li");
    item.textContent = fact;
    facts.appendChild(item);
  });

  const invariants = $("#canon-invariants");
  invariants.replaceChildren();
  (canon.invariants || []).forEach((rule) => {
    const item = document.createElement("li");
    item.textContent = rule;
    invariants.appendChild(item);
  });

  const branches = $("#canon-branches");
  branches.replaceChildren();
  (canon.branches || []).forEach((branch) => {
    const card = document.createElement("article");
    card.className = "canon-branch";
    const title = document.createElement("b");
    title.textContent = branch.label;
    card.appendChild(title);
    const id = document.createElement("span");
    id.textContent = branch.id;
    card.appendChild(id);
    const outcome = document.createElement("p");
    outcome.textContent = branch.outcome;
    card.appendChild(outcome);
    card.title = branch.condition || "";
    branches.appendChild(card);
  });
}
/* ---- character sheet -------------------------------------------------- */

let profileReturnFocus = null;

export function relBar(key, value) {
  const bar = document.createElement("div");
  bar.className = "rel-bar";
  const label = document.createElement("span");
  label.className = "rel-label";
  label.textContent = key;
  const track = document.createElement("div");
  track.className = "track";
  const fill = document.createElement("div");
  fill.className = `fill ${key}`;
  fill.style.width = `${Math.max(0, Math.min(1, Number(value) || 0)) * 100}%`;
  track.appendChild(fill);
  const amount = document.createElement("span");
  amount.className = "rel-value";
  amount.textContent = Number(value || 0).toFixed(2);
  bar.append(label, track, amount);
  return bar;
}

export function castIdFor(value) {
  const raw = String(value || "").trim();
  const lowered = raw.toLowerCase();
  if (lowered === "user" || lowered === "you" || lowered === "the user") return "user";
  if (CAST[lowered]) return lowered;
  const byName = ORDER.find((id) => {
    const name = CAST[id].name.toLowerCase();
    return name === lowered || name.split(" ")[0] === lowered;
  });
  return byName || lowered;
}

export function renderProfileRelationships(data, id) {
  const host = $("#profile-rel");
  host.replaceChildren();
  const order = ["user", ...ORDER.filter((other) => other !== id)];
  const seen = new Set();
  const edges = (data.relationships || [])
    .filter((edge) => edge.a === id)
    .map((edge) => ({ ...edge, b: castIdFor(edge.b) }))
    .filter((edge) => {
      if (seen.has(edge.b)) return false;
      seen.add(edge.b);
      return true;
    })
    .sort((a, b) => order.indexOf(a.b) - order.indexOf(b.b));
  if (!edges.length) return;
  const title = document.createElement("div");
  title.className = "profile-rel-title";
  title.textContent = "outgoing relationships";
  host.appendChild(title);
  const list = document.createElement("div");
  list.className = "rel-list";
  edges.forEach((edge) => {
    const row = document.createElement("div");
    row.className = "rel-row";
    const name = document.createElement("div");
    name.className = "rel-name";
    name.textContent = edge.b === "user" ? "You" : ((CAST[edge.b] && CAST[edge.b].name) || edge.b);
    row.appendChild(name);
    const bars = document.createElement("div");
    bars.className = "rel-bars";
    ["trust", "closeness", "tension"].forEach((key) => bars.appendChild(relBar(key, edge[key])));
    row.appendChild(bars);
    list.appendChild(row);
  });
  host.appendChild(list);
}

export function openProfile(id) {
  const cast = CAST[id];
  if (!cast) return;
  const modal = $("#profile-modal");
  profileReturnFocus = document.activeElement;
  modal.style.setProperty("--scene-color", cast.color);
  $("#profile-route").textContent = cast.route || "";
  $("#profile-name").textContent = cast.name;
  $("#profile-jp").textContent = "";
  $("#profile-role").textContent = `${cast.role} · ${cast.mood}`;
  $("#profile-intro").textContent = cast.intro;

  const stats = $("#profile-stats");
  stats.replaceChildren();
  const profile = cast.profile || {};
  [["age", profile.age], ["height", profile.height], ["birthday", profile.birthday],
   ["specialty", profile.specialty]].forEach(([label, value]) => {
    if (value == null) return;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = String(value);
    row.append(term, detail);
    stats.appendChild(row);
  });

  $("#profile-likes").textContent = profile.likes || "—";
  $("#profile-dislikes").textContent = profile.dislikes || "—";
  $("#profile-secret").textContent = cast.secret || "—";
  $("#profile-quote").textContent = cast.quote;
  $("#profile-dm").href = cast.dm;

  const img = $("#profile-art-img");
  let fallback = 0;
  img.onerror = () => {
    if (fallback === 0) {
      fallback = 1;
      img.src = cast.portrait;
      return;
    }
    img.onerror = null;
    img.src = `/static/assets/portraits/${cast.id}.svg`;
  };
  const bg = $("#profile-art-bg");
  const art = outfitArtFor(state.data, id) || castArtFor(state.data, id)
    || cast.scene || cast.full || cast.portrait;
  if (bg) {
    bg.onerror = () => {
      bg.onerror = null;
      bg.src = cast.portrait;
    };
    bg.src = art;
  }
  img.style.transform = "none";
  img.src = art;
  img.alt = `${cast.name} character art`;

  renderProfileRelationships(state.data || {}, id);
  modal.hidden = false;
  const app = $(".app");
  if (app) app.inert = true;
  document.body.classList.add("modal-open");
  $("#profile-close").focus();
}

export function closeProfile() {
  const modal = $("#profile-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  const app = $(".app");
  if (app) app.inert = false;
  document.body.classList.remove("modal-open");
  if (profileReturnFocus && typeof profileReturnFocus.focus === "function") {
    profileReturnFocus.focus();
  }
  profileReturnFocus = null;
}
