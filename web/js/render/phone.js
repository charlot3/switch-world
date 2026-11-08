/* Phone DM surface: the lock card, the thread, Add friend and the send path.

   `isFriend` and `phoneTarget` live here because both the story stage and the
   Studio need them; stage.js imports them back, which is a cycle of function
   declarations only (no top-level call reaches across). */

import { api } from "../api.js";
import { asCastId, firstName } from "../format.js";
import { state } from "../state.js";
import { CAST_ORDER as ORDER } from "../vocab.js";
import { $, CAST, MATTERMOST_BASE } from "./dom.js";
import { currentScenario, renderSafety, renderStory } from "./stage.js";
import { refresh } from "../views.js";

export function isFriend(data, id) {
  if (data && (data.friends || []).includes(id)) return true;
  const scenario = currentScenario(data);
  if (!scenario || !Array.isArray(scenario.friends)) return false;
  return scenario.friends.map((friend) => asCastId(friend)).includes(id);
}

export function phoneTarget() {
  return state.phone.character || state.selected || ORDER[0];
}

export function resetPhoneFor(id) {
  /* The phone follows the selected cast member. Without this it keeps the
     character it was last opened for, so picking Mia still shows Alice's
     lock card and the Add friend button acts on the wrong person. */
  if (state.phone.character && state.phone.character !== id) {
    state.phone.character = id;
    state.phone.loadedFor = null;
    state.phone.loadingFor = null;
    state.phone.messages = [];
    state.phone.hasMore = false;
    state.phone.oldestId = null;
    state.phone.error = "";
  }
}

export function selectCast(id) {
  if (!CAST[id]) return;
  state.selected = id;
  resetPhoneFor(id);
  if (state.data) {
    renderStory(state.data);
    renderPhone(state.data);
  }
}
/* ---- phone DM --------------------------------------------------------- */

export function renderPhone(data) {
  if (state.phone.sending) return;
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
    input.disabled = !friend || state.phone.sending || state.safety.paused;
    input.placeholder = state.safety.paused
      ? "Scene paused"
      : (friend ? `Message ${firstName(cast.name)}…` : "Add as a friend to chat");
  }
  if (send) send.disabled = !friend || state.phone.sending || state.safety.paused;
  const avatar = $("#phone-avatar");
  avatar.onerror = () => {
    avatar.onerror = null;
    avatar.src = `/static/assets/portraits/${cast.id}-avatar.svg`;
  };
  avatar.src = cast.avatar;
  avatar.alt = `${cast.name} avatar`;
  $("#phone-name").textContent = cast.name;
  $("#phone-mood").textContent = cast.mood;
  $("#phone-open").href = `${MATTERMOST_BASE}/switch/channels/world`;
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

export function paintPhone(cast) {
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

export async function addFriend(character) {
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

export function openPhone(character) {
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

export function closePhone() {
  const phone = $(".story-phone");
  if (phone) phone.classList.remove("is-open");
}

let phoneHistorySeq = 0;

export function resetPhoneHistorySeq() {
  phoneHistorySeq += 1;
}

export async function loadPhoneHistory(character, beforeId = null, prepend = false) {
  if (!character || state.phone.sending) return;
  if (state.phone.loading && state.phone.loadingFor === character) return;
  if (state.phone.character && state.phone.character !== character) return;
  if (!isFriend(state.data, character)) return;
  const seq = ++phoneHistorySeq;
  state.phone.loading = true;
  state.phone.loadingFor = character;
  const thread = $("#phone-thread");
  const previousHeight = thread ? thread.scrollHeight : 0;
  const cast = CAST[character];
  if (cast) paintPhone(cast);
  try {
    const query = `/api/dm/${encodeURIComponent(character)}?limit=100${beforeId ? `&before_id=${beforeId}` : ""}`;
    const result = await api(query);
    if (seq !== phoneHistorySeq || state.phone.character !== character) return;
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
    if (seq !== phoneHistorySeq || state.phone.character !== character) return;
    state.phone.error = `History unavailable: ${error.message}`;
    state.phone.loadedFor = character;
  } finally {
    if (seq === phoneHistorySeq) {
      state.phone.loading = false;
      state.phone.loadingFor = null;
      if (state.phone.character === character && cast) paintPhone(cast);
      if (state.phone.character === character && prepend && thread) {
        thread.scrollTop = thread.scrollHeight - previousHeight;
      }
    }
  }
}

export async function sendPhone(event) {
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
    if (phoneTarget() === character) await loadPhoneHistory(character);
    await refresh();
  } catch (error) {
    state.phone.sending = false;
    const paused = error.status === 423;
    if (paused) {
      state.safety.paused = true;
      state.safety.ready = true;
      state.safety.status = "Paused. New scene and DM lines are on hold until you resume.";
      renderSafety();
    }
    /* The optimistic bubble never entered state.phone.messages, so remove it
       instead of leaving it in a thread the next repaint will clear. */
    bubble.remove();
    if (phoneTarget() === character) {
      if (!paused) input.value = message;
      const failed = document.createElement("div");
      failed.className = "phone-bubble character";
      const label = document.createElement("span");
      label.className = "phone-who";
      label.textContent = "System";
      failed.appendChild(label);
      failed.appendChild(document.createTextNode(paused
        ? "The scene is paused. This message is on hold — resume in Studio when you choose."
        : `The line went quiet: ${error.message}`));
      thread.appendChild(failed);
      thread.scrollTop = thread.scrollHeight;
    } else {
      const status = $("#scene-status");
      if (status) status.textContent = paused
        ? "A DM is on hold because the scene is paused."
        : `The line to ${cast ? firstName(cast.name) : "her"} went quiet: ${error.message}`;
    }
  } finally {
    state.phone.sending = false;
    typing.hidden = true;
    const current = phoneTarget();
    const friend = isFriend(state.data, current);
    input.disabled = !friend || state.safety.paused;
    send.disabled = !friend || state.safety.paused;
    if (friend && !state.safety.paused) input.focus();
    if (!CAST[current]) input.placeholder = "Message…";
  }
}
