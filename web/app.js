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
  phone: {
    character: null,
    messages: [],
    hasMore: false,
    oldestId: null,
    loading: false,
    sending: false,
    loadedFor: null,
    error: "",
    paintSig: null,
  },
  performance: null,
  group: { sending: false },
  groupStatus: "",
  clockStatus: "",
  beatId: null,
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

function shellMode() {
  const visual = window.visualViewport ? window.visualViewport.width : window.innerWidth;
  const width = Math.min(window.innerWidth, visual || window.innerWidth);
  document.documentElement.dataset.shell = width <= 760 ? "phone" : width <= 1180 ? "compact" : "wide";
  if (width > 760) closePhone();
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

function currentBeat(data) {
  const scene = (data && data.scene) || {};
  if (scene.current_beat) return scene.current_beat;
  const beats = (data && data.canon && data.canon.beats) || [];
  return beats[0] || null;
}

function presentCharacters(data) {
  const beat = currentBeat(data);
  if (!beat) return ORDER.slice();
  return (beat.characters || []).map((id) => String(id).toLowerCase())
    .filter((id) => CAST[id]);
}

const BEAT_ART = {
  "morning-shop": "/static/assets/portraits/beat-morning-shop.jpg",
  "truck-lunch": "/static/assets/portraits/beat-truck-lunch.jpg",
};

function sceneArtFor(data, cast) {
  const beat = currentBeat(data);
  return (beat && BEAT_ART[beat.id]) || cast.scene || cast.full || cast.portrait;
}

function isFriend(data, id) {
  return Boolean(data && (data.friends || []).includes(id));
}

function phoneTarget() {
  return state.phone.character || state.selected || ORDER[0];
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
  const beat = currentBeat(data);
  if (state.beatId && beat && state.beatId !== beat.id) {
    state.performance = null;
    state.groupStatus = "";
    state.lineId = null;
  }
  state.beatId = beat ? beat.id : null;
  const present = presentCharacters(data);
  if (present.length && !present.includes(state.selected)) state.selected = present[0];

  const performance = state.performance && state.performance.items[state.performance.index];
  const lines = dialogueEvents(data).slice(-8);
  if (state.lineId != null && !lines.some((line) => line.id === state.lineId)) {
    state.lineId = null;
  }
  const castLines = lines.filter((item) => item.castId === state.selected);
  let line = state.lineId != null
    ? lines.find((item) => item.id === state.lineId)
    : (castLines[castLines.length - 1] || null);
  if (performance) {
    line = {
      id: `perf:${state.performance.index}:${performance.text.slice(0, 24)}`,
      name: performance.character === "user" ? "You" : (CAST[performance.character] || {}).name || performance.character,
      castId: performance.character === "user" ? null : performance.character,
      text: performance.text,
      ts: data.clock ? data.clock.now : null,
    };
  } else if (line && state.lineId != null && line.castId) {
    state.selected = line.castId;
  }
  const cast = CAST[(line && line.castId) || state.selected] || CAST[state.selected];

  const scene = $(".scene");
  scene.style.setProperty("--scene-color", cast.color);
  const portrait = $("#scene-portrait");
  const backdrop = $("#scene-backdrop");
  portrait.onerror = () => {
    portrait.onerror = null;
    portrait.src = `/static/assets/portraits/${cast.id}-bust.png`;
  };
  const sceneArt = sceneArtFor(data, cast);
  portrait.src = sceneArt;
  portrait.alt = `${cast.name} portrait`;
  if (backdrop) {
    backdrop.onerror = () => {
      backdrop.onerror = null;
      backdrop.src = `/static/assets/portraits/${cast.id}-bust.png`;
    };
    backdrop.src = sceneArt;
  }
  $("#scene-name").textContent = line ? line.name : cast.name;
  $("#scene-jp").textContent = line && line.name === "You" ? "" : cast.route;
  $("#scene-mood").textContent = line && line.name === "You" ? "in the room" : cast.mood;
  $("#scene-stamp").textContent = beat ? `SCENE · ${beat.title.toUpperCase()}` : "SCENE · THE CAFÉ";
  $("#scene-caption").textContent = beat
    ? `${formatTime(data.clock.now)} · ${beat.place || beat.title}`
    : "18:30 · a Tuesday in late autumn";

  const text = line ? line.text : cast.quote;
  typeLine($("#scene-line"), text, line ? `line:${line.id}` : `quote:${cast.id}`);

  renderSceneCast(present);
  renderChoices(beat);
  const sayInput = $("#scene-say-input");
  if (sayInput) {
    sayInput.placeholder = present.length > 1
      ? "Say something to the room…"
      : `Say something to ${present.length ? firstName(CAST[present[0]].name) : "them"}…`;
  }

  const status = $("#scene-status");
  if (status) {
    if (state.group.sending) {
      status.textContent = present.length
        ? `${present.map((id) => firstName(CAST[id].name)).join(", ")} ${present.length === 1 ? "is" : "are"} listening…`
        : "The room is listening…";
    } else if (state.performance) {
      status.textContent = `Line ${state.performance.index + 1} of ${state.performance.items.length} · Next line to continue`;
    } else {
      status.textContent = state.groupStatus || "";
    }
  }

  const rail = $("#scene-rail");
  const railSig = lines.map((item) => item.id).join(",") + "|" + (line ? line.id : "");
  if (rail.dataset.sig !== railSig) {
  rail.dataset.sig = railSig;
  rail.replaceChildren();
  lines.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-chip" + ((line && line.id === item.id) ? " is-active" : "");
    button.textContent = `${firstName(item.name)}: ${item.text}`;
    button.title = item.text;
    button.addEventListener("click", () => {
      state.lineId = item.id;
      state.performance = null;
      if (item.castId) state.selected = item.castId;
      renderStory(state.data);
    });
    rail.appendChild(button);
  });
  }

  renderHero(data);
  renderCast(data);
  renderArc(data);
  renderPhone(data);
}

function renderSceneCast(present) {
  const row = $("#scene-cast");
  if (!row) return;
  const sig = present.join(",") + "|" + state.selected;
  if (row.dataset.sig === sig) return;
  row.dataset.sig = sig;
  row.replaceChildren();
  present.forEach((id) => {
    const cast = CAST[id];
    if (!cast) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-member" + (state.selected === id ? " is-active" : "");
    button.title = `${cast.name} — ${cast.role}`;
    button.setAttribute("aria-label", `${cast.name}, ${cast.role}`);
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
    button.addEventListener("click", () => {
      state.performance = null;
      selectCast(id);
    });
    row.appendChild(button);
  });
}

function renderChoices(beat) {
  const box = $("#scene-choices");
  if (!box) return;
  const choices = (beat && beat.choices) || [];
  const sig = `${beat ? beat.id : ""}|${state.group.sending}|${choices.join("|")}`;
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.replaceChildren();
  choices.forEach((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scene-choice";
    button.textContent = text;
    button.disabled = state.group.sending;
    button.addEventListener("click", () => sendGroup(text));
    box.appendChild(button);
  });
  box.hidden = choices.length === 0;
}

async function sendGroup(text) {
  text = String(text || "").trim();
  if (!text || state.group.sending) return;
  const present = presentCharacters(state.data);
  state.group.sending = true;
  state.groupStatus = "";
  state.performance = { items: [{ character: "user", text }], index: 0 };
  renderStory(state.data);

  const input = $("#scene-say-input");
  const send = $("#scene-say-send");
  if (input) input.disabled = true;
  if (send) send.disabled = true;

  try {
    const result = await api("/api/group/say", {
      method: "POST",
      body: JSON.stringify({ message: text, characters: present, timeout: 50 }),
    });
    state.group.sending = false;
    if (result.replies && result.replies.length) {
      state.performance = {
        items: result.replies.map((reply) => ({ character: reply.character, text: reply.text })),
        index: 0,
      };
    } else {
      state.performance = null;
    }
    await refresh();
    if (result.missing && result.missing.length) {
      state.groupStatus = `No reply yet from ${result.missing.map((id) => firstName((CAST[id] || {}).name || id)).join(", ")}. The room may be quiet.`;
    }
  } catch (error) {
    state.group.sending = false;
    state.performance = null;
    state.groupStatus = `The room didn't answer: ${error.message}`;
    renderStory(state.data);
  } finally {
    state.group.sending = false;
    if (input) input.disabled = false;
    if (send) send.disabled = false;
    if (state.data) renderStory(state.data);
  }
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
    heart.textContent = index < holders.length ? "♥" : "♡";
  });
}

function affinityFor(data, id) {
  const edge = (data.relationships || []).find((e) => e.a === id && e.b === "user");
  if (!edge) return 0.4;
  return Math.max(0, Math.min(1, (edge.trust + edge.closeness) / 2 - edge.tension / 2));
}

function selectCast(id) {
  state.selected = id;
  state.lineId = null;
  renderStory(state.data);
}

function makeCastAction(label, onClick) {
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

function renderCast(data) {
  const grid = $("#cast-grid");
  const sig = ORDER.map((id) => `${id}:${Math.round(affinityFor(data, id) * 5)}:${isFriend(data, id)}`).join("|") + `|${state.selected}`;
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
    img.onerror = () => {
      img.onerror = null;
      img.src = `/static/assets/portraits/${cast.id}.svg`;
    };
    img.src = cast.portrait;
    img.alt = `${cast.name} portrait`;
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
    const filled = Math.round(affinityFor(data, id) * 5);
    hearts.textContent = "♥".repeat(filled) + "♡".repeat(5 - filled);
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

/* ---- phone DM --------------------------------------------------------- */

function renderPhone(data) {
  const targetId = phoneTarget();
  const cast = CAST[targetId] || CAST[ORDER[0]];
  if (!cast) return;
  state.phone.character = cast.id;
  const friend = isFriend(data, cast.id);
  const phone = $(".phone");
  if (phone) phone.classList.toggle("is-locked", !friend);
  const input = $("#phone-input");
  const send = $("#phone-send");
  if (input) {
    input.disabled = !friend || state.phone.sending;
    input.placeholder = friend ? `Message ${firstName(cast.name)}…` : "Add as a friend to chat";
  }
  if (send) send.disabled = !friend || state.phone.sending;
  const avatar = $("#phone-avatar");
  avatar.onerror = () => {
    avatar.onerror = null;
    avatar.src = `/static/assets/portraits/${cast.id}-avatar.svg`;
  };
  avatar.src = cast.avatar;
  avatar.alt = `${cast.name} avatar`;
  $("#phone-name").textContent = cast.name;
  $("#phone-mood").textContent = cast.mood;
  $("#phone-open").href = "http://127.0.0.1:8065/switch/channels/world";
  const clock = data.clock && data.clock.now
    ? new Date(data.clock.now).toLocaleTimeString("en-GB", {
        timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit",
      })
    : "--:--";
  $("#phone-time").textContent = clock;

  if (!friend) {
    $("#phone-mood").textContent = "not a friend yet";
    state.phone.messages = [];
    state.phone.hasMore = false;
    state.phone.error = "";
    paintPhone(cast);
    return;
  }
  $("#phone-mood").textContent = cast.mood;

  if (state.phone.sending) return;

  if (state.phone.character !== cast.id || state.phone.loadedFor !== cast.id) {
    state.phone.messages = [];
    state.phone.hasMore = false;
    state.phone.oldestId = null;
    state.phone.error = "";
    paintPhone(cast);
    loadPhoneHistory(cast.id);
    return;
  }
  paintPhone(cast);
}

function paintPhone(cast) {
  const thread = $("#phone-thread");
  if (!thread) return;
  const friend = isFriend(state.data, cast.id);
  const sig = [
    cast.id,
    friend,
    state.phone.loading,
    state.phone.hasMore,
    state.phone.error,
    state.phone.messages.map((message) => message.id).join(","),
  ].join("|");
  if (state.phone.paintSig === sig) return;
  state.phone.paintSig = sig;
  const atBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 48;
  const previousTop = thread.scrollTop;
  thread.replaceChildren();

  const divider = (label) => {
    const node = document.createElement("div");
    node.className = "phone-divider";
    node.textContent = label;
    thread.appendChild(node);
  };
  const bubbleFor = (text, role, label) => {
    const bubble = document.createElement("div");
    bubble.className = `phone-bubble ${role}`;
    const who = document.createElement("span");
    who.className = "phone-who";
    who.textContent = label;
    bubble.appendChild(who);
    bubble.appendChild(document.createTextNode(text));
    thread.appendChild(bubble);
  };

  if (!friend) {
    const lock = document.createElement("div");
    lock.className = "phone-lock";
    const icon = document.createElement("div");
    icon.className = "phone-lock-icon";
    icon.textContent = "◇";
    lock.appendChild(icon);
    const title = document.createElement("strong");
    title.textContent = `You haven't added ${firstName(cast.name)} yet.`;
    lock.appendChild(title);
    const note = document.createElement("p");
    note.textContent = "Phone chat unlocks after you add her as a friend. Talk to her in the scene first.";
    lock.appendChild(note);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn primary";
    button.textContent = `Add ${firstName(cast.name)} as a friend`;
    button.addEventListener("click", () => addFriend(cast.id));
    lock.appendChild(button);
    thread.appendChild(lock);
    return;
  }

  if (state.phone.error) {
    const failed = document.createElement("div");
    failed.className = "phone-bubble character";
    const label = document.createElement("span");
    label.className = "phone-who";
    label.textContent = "System";
    failed.appendChild(label);
    failed.appendChild(document.createTextNode(state.phone.error));
    thread.appendChild(failed);
    return;
  }
  if (state.phone.loading && !state.phone.messages.length) {
    const loading = document.createElement("div");
    loading.className = "phone-empty";
    loading.textContent = "Loading history…";
    thread.appendChild(loading);
    return;
  }
  if (state.phone.hasMore) {
    const older = document.createElement("button");
    older.type = "button";
    older.className = "phone-older";
    older.textContent = "Load older";
    older.disabled = state.phone.loading;
    older.addEventListener("click", () => {
      loadPhoneHistory(cast.id, state.phone.oldestId, true);
    });
    thread.appendChild(older);
  }
  if (!state.phone.messages.length) {
    bubbleFor(cast.quote, "character", firstName(cast.name));
    thread.scrollTop = thread.scrollHeight;
    return;
  }

  let lastKind = null;
  state.phone.messages.forEach((message) => {
    if (message.kind !== lastKind) {
      divider(message.kind === "dm" ? "Private DM" : "Earlier in the scene");
      lastKind = message.kind;
    }
    bubbleFor(
      message.text,
      message.role === "user" ? "user" : "character",
      message.role === "user" ? "You" : firstName(cast.name),
    );
  });
  thread.scrollTop = thread.scrollHeight;
}

async function addFriend(character) {
  if (!character) return;
  try {
    await api(`/api/friends/${encodeURIComponent(character)}`, { method: "POST" });
    state.phone.character = character;
    state.phone.loadedFor = null;
    state.phone.messages = [];
    state.phone.error = "";
    await refresh();
    openPhone(character);
  } catch (error) {
    const status = $("#scene-status");
    if (status) status.textContent = `Could not add ${character}: ${error.message}`;
  }
}

function openPhone(character) {
  const id = character || phoneTarget();
  if (!CAST[id]) return;
  state.phone.character = id;
  if (!isFriend(state.data, id)) {
    state.phone.loadedFor = null;
    if (state.data) renderPhone(state.data);
  } else {
    if (state.phone.loadedFor !== id) {
      state.phone.loadedFor = null;
      loadPhoneHistory(id);
    }
    if (state.data) renderPhone(state.data);
  }
  if (window.matchMedia("(max-width: 1360px)").matches) {
    $(".story-phone").classList.add("is-open");
  } else {
    $(".story-phone").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  if (isFriend(state.data, id)) $("#phone-input").focus();
}

function closePhone() {
  const phone = $(".story-phone");
  if (phone) phone.classList.remove("is-open");
}

async function loadPhoneHistory(character, beforeId = null, prepend = false) {
  if (!character || state.phone.loading || state.phone.sending) return;
  if (!isFriend(state.data, character)) return;
  state.phone.loading = true;
  const thread = $("#phone-thread");
  const previousHeight = thread ? thread.scrollHeight : 0;
  const cast = CAST[character];
  if (cast) paintPhone(cast);
  try {
    const query = `/api/dm/${encodeURIComponent(character)}?limit=100${beforeId ? `&before_id=${beforeId}` : ""}`;
    const result = await api(query);
    const messages = result.messages || [];
    if (prepend) {
      state.phone.messages = [...messages, ...state.phone.messages];
    } else {
      state.phone.messages = messages;
    }
    state.phone.character = character;
    state.phone.loadedFor = character;
    state.phone.error = "";
    state.phone.hasMore = Boolean(result.has_more);
    state.phone.oldestId = result.oldest_id || null;
    if (cast) paintPhone(cast);
    if (prepend && thread) {
      thread.scrollTop = thread.scrollHeight - previousHeight;
    }
  } catch (error) {
    state.phone.error = `History unavailable: ${error.message}`;
    state.phone.loadedFor = character;
  } finally {
    state.phone.loading = false;
    if (cast) paintPhone(cast);
    if (prepend && thread) {
      thread.scrollTop = thread.scrollHeight - previousHeight;
    }
  }
}

async function sendPhone(event) {
  event.preventDefault();
  const input = $("#phone-input");
  const send = $("#phone-send");
  const typing = $("#phone-typing");
  const message = input.value.trim();
  if (!message) return;
  const character = phoneTarget();
  if (!isFriend(state.data, character)) {
    addFriend(character);
    return;
  }
  const cast = CAST[character];
  const thread = $("#phone-thread");
  input.value = "";
  input.disabled = true;
  send.disabled = true;
  typing.hidden = false;
  state.phone.sending = true;

  const bubble = document.createElement("div");
  bubble.className = "phone-bubble user";
  const who = document.createElement("span");
  who.className = "phone-who";
  who.textContent = "You";
  bubble.appendChild(who);
  bubble.appendChild(document.createTextNode(message));
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;

  try {
    await api("/api/dm", {
      method: "POST",
      body: JSON.stringify({ character, message }),
    });
    state.phone.sending = false;
    await loadPhoneHistory(character);
    await refresh();
  } catch (error) {
    state.phone.sending = false;
    const failed = document.createElement("div");
    failed.className = "phone-bubble character";
    const label = document.createElement("span");
    label.className = "phone-who";
    label.textContent = "System";
    failed.appendChild(label);
    failed.appendChild(document.createTextNode(`The line went quiet: ${error.message}`));
    thread.appendChild(failed);
    thread.scrollTop = thread.scrollHeight;
  } finally {
    state.phone.sending = false;
    typing.hidden = true;
    const friend = isFriend(state.data, character);
    input.disabled = !friend;
    send.disabled = !friend;
    if (friend) input.focus();
    if (!cast) input.placeholder = "Message…";
  }
}

/* ---- authored arc ----------------------------------------------------- */

function renderArc(data) {
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

/* ---- canon ------------------------------------------------------------ */

function renderCanon(data) {
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

function relBar(key, value) {
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

function castIdFor(value) {
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

function renderProfileRelationships(data, id) {
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

function openProfile(id) {
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
  const art = cast.scene || cast.full || cast.portrait;
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

function closeProfile() {
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

/* ---- settings --------------------------------------------------------- */

function renderSettings(data) {
  const current = data || state.data || {};
  renderCanon(current);
  const scene = current.scene || {};
  const mode = (current.clock && current.clock.mode) || "mock";
  const clockNow = $("#clock-now");
  if (clockNow) clockNow.textContent = formatClock(current.clock.now);
  const clockMode = $("#clock-mode");
  if (clockMode) {
    clockMode.textContent = mode === "realtime" ? "real time · 1×" : "mock time";
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

const VIEW_META = {
  story: { eyebrow: "Tonight at the café", title: "Story" },
  tree: { eyebrow: "The shape of the secret", title: "World Tree" },
  ledger: { eyebrow: "The god view", title: "Secret Ledger" },
  settings: { eyebrow: "The stage", title: "Settings" },
};

function setView(view) {
  closeProfile();
  closePhone();
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
  if (view === "story" && state.data) loadPhoneHistory(phoneTarget());
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function render(data) {
  const mode = data.clock && data.clock.mode === "realtime" ? " · REAL" : " · MOCK";
  $("#rail-clock").textContent = formatClock(data.clock.now) + mode;
  if (state.view === "story") renderStory(data);
  if (state.view === "tree") renderTree(data);
  if (state.view === "ledger") renderLedger(data);
  if (state.view === "settings") renderSettings(data);
}

let initialProfileOpened = false;

let refreshInFlight = false;

async function refresh() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  const main = $("#main");
  main.classList.add("refreshing");
  try {
    const data = await api("/api/state");
    state.data = data;
    render(data);
    if (!initialProfileOpened) {
      initialProfileOpened = true;
      const profile = new URLSearchParams(location.search).get("profile");
      if (profile && CAST[profile]) openProfile(profile);
    }
    showError(null);
  } catch (error) {
    showError(`Cannot reach the world engine: ${error.message}`);
  } finally {
    main.classList.remove("refreshing");
    refreshInFlight = false;
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

async function runBifrost() {
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
    await refresh();
    await loadSceneCard();
  } catch (error) {
    status.textContent = `Bifrost beat failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

async function fetchTavily() {
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

async function setClockMode(mode) {
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

async function advanceClock(run) {
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
    state.performance = null;
    state.lineId = null;
    await refresh();
    if (run) await loadSceneCard();
  } catch (error) {
    state.clockStatus = `Clock advance failed: ${error.message}`;
    if (status) status.textContent = state.clockStatus;
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
  }
}

async function runLocalBeat() {
  const beat = $("#beat-select")?.value || "cafe";
  try {
    const result = await api("/api/dev/run-beat", {
      method: "POST",
      body: JSON.stringify({ beat, transport: "local" }),
    });
    const branch = result.branch ? ` · ${result.branch.label} (${result.branch.id})` : "";
    $("#status").textContent = `Local beat: ${result.beat.title}${branch}.`;
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Local beat failed: ${error.message}`;
  }
}

async function runArc() {
  const button = $("#run-arc");
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Running arc…";
  try {
    const result = await api("/api/dev/run-arc", { method: "POST", body: "{}" });
    $("#status").textContent = `Local arc complete: five beats · ${result.branch.label} (${result.branch.id}).`;
    await refresh();
    await loadSceneCard();
  } catch (error) {
    $("#status").textContent = `Local arc failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

async function resetWorld() {
  if (!window.confirm("Reset the world state, phone DMs, and current scene card? Switch/Mattermost room history stays.")) return;
  try {
    await api("/api/dev/reset", { method: "POST", body: "{}" });
    $("#status").textContent = "Demo world reset. Switch/Mattermost history is unchanged.";
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
  const button = $("#copy-command");
  if (button) {
    const old = button.textContent;
    button.textContent = "Copied ✓";
    setTimeout(() => { button.textContent = old; }, 1800);
  }
}

function nextLine() {
  if (state.performance) {
    if (state.performance.index < state.performance.items.length - 1) {
      state.performance.index += 1;
      renderStory(state.data);
      return;
    }
    const last = state.performance.items[state.performance.items.length - 1];
    if (last && last.character !== "user" && CAST[last.character]) state.selected = last.character;
    state.performance = null;
    renderStory(state.data);
    return;
  }
  const lines = dialogueEvents(state.data || {}).slice(-8);
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
shellMode();
window.addEventListener("resize", shellMode);
if (window.visualViewport) window.visualViewport.addEventListener("resize", shellMode);
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
/* Some embedded/browser previews block target=_blank popups; navigate the top page
   directly so Open #world always responds to the click. */
$$('a[href*="127.0.0.1:8065/switch/channels/world"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    try {
      if (window.top && window.top !== window.self) {
        window.top.location.href = link.href;
        return;
      }
    } catch {
      /* cross-origin top; fall back to this window */
    }
    window.location.assign(link.href);
  });
});
/* Same problem for the remaining new-tab links: if the browser refuses the popup,
   navigate the top page instead of failing silently. */
$$('a[target="_blank"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    const opened = window.open(link.href, "_blank");
    if (opened) {
      try { opened.opener = null; } catch { /* ignore */ }
      return;
    }
    try {
      if (window.top && window.top !== window.self) {
        window.top.location.href = link.href;
        return;
      }
    } catch {
      /* cross-origin top; fall back to this window */
    }
    window.location.assign(link.href);
  });
});

$("#arc-canon").addEventListener("click", () => setView("settings"));
$("#profile-close").addEventListener("click", closeProfile);
$("#profile-close-2").addEventListener("click", closeProfile);
$("#profile-modal").addEventListener("click", (event) => {
  if (event.target.matches("[data-close-profile]")) closeProfile();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if ($(".story-phone")?.classList.contains("is-open")) {
    closePhone();
    return;
  }
  closeProfile();
});
$("#scene-next").addEventListener("click", nextLine);
$("#scene-say-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#scene-say-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendGroup(text);
});
$("#scene-dm").addEventListener("click", () => {
  const cast = CAST[state.selected];
  if (cast && !isFriend(state.data, cast.id)) {
    addFriend(cast.id);
    return;
  }
  openPhone(state.selected);
});
$("#clock-mock").addEventListener("click", () => setClockMode("mock"));
$("#clock-real").addEventListener("click", () => setClockMode("realtime"));
$("#clock-advance").addEventListener("click", () => advanceClock(false));
$("#clock-play").addEventListener("click", () => advanceClock(true));
$("#tell-alice").addEventListener("click", tellAlice);
$("#run-cafe").addEventListener("click", runLocalBeat);
$("#run-arc").addEventListener("click", runArc);
$("#run-bifrost").addEventListener("click", runBifrost);
$("#phone-form").addEventListener("submit", sendPhone);
$("#phone-close").addEventListener("click", closePhone);
$("#fetch-tavily").addEventListener("click", fetchTavily);
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
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  window.addEventListener("focus", refresh);
}
