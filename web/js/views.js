/* View dispatch, navigation and the state poll.

   This is the seam actions use for refresh()/render()/setView() so the entry
   module stays wiring-only and render modules never import main.js. */

import { api } from "./api.js";
import { formatClock } from "./format.js";
import { state } from "./state.js";
import { $, $$, CAST } from "./render/dom.js";
import {
  loadScenarios,
  loadTakeCurrent,
  loadTakes,
  renderClockScale,
  renderSafety,
  renderStory,
  renderTakes,
  renderWorlds,
  syncSafety,
  syncTakeState,
} from "./render/stage.js";
import {
  closeProfile,
  openProfile,
  renderLedger,
  renderTree,
} from "./render/ledger.js";
import {
  closePhone,
  loadPhoneHistory,
  phoneTarget,
} from "./render/phone.js";
import {
  loadStudio,
  maybeLoadStudio,
  renderSettings,
} from "./render/studio.js";

export const VIEW_META = {
  story: { eyebrow: "Tonight at the café", title: "Story" },
  worlds: { eyebrow: "One reset, one seed", title: "Worlds" },
  tree: { eyebrow: "The shape of the secret", title: "World Tree" },
  ledger: { eyebrow: "The god view", title: "Secret Ledger" },
  studio: { eyebrow: "The control room", title: "Studio" },
  settings: { eyebrow: "The stage", title: "Settings" },
};

export function setView(view) {
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
  if (state.view === "worlds") {
    loadScenarios();
    loadTakes();
    loadTakeCurrent();
  }
  if (state.data) render(state.data);
  if (view === "story" && state.data) loadPhoneHistory(phoneTarget());
  if (view === "studio") loadStudio(true);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function setTreeLens(lens) {
  state.treeLens = lens === "cast" ? "cast" : "user";
  $$("[data-tree-lens]").forEach((button) => {
    const active = button.dataset.treeLens === state.treeLens;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  if (state.data) renderTree(state.data);
}

export function render(data) {
  const scale = renderClockScale(data);
  $("#rail-clock").textContent = formatClock(data.clock.now) + ` · ${scale}`;
  renderSafety();
  if (state.view === "story") renderStory(data);
  if (state.view === "worlds") renderWorlds();
  else renderTakes();
  if (state.view === "tree") renderTree(data);
  if (state.view === "ledger") renderLedger(data);
  if (state.view === "studio") maybeLoadStudio();
  if (state.view === "settings") renderSettings(data);
}

let initialProfileOpened = false;

let refreshInFlight = null;
let refreshQueued = null;

export function refresh() {
  if (refreshInFlight) {
    /* Don't drop the request: callers that await refresh() after a write
       (addFriend) need a fetch that starts after the current one finishes. */
    if (!refreshQueued) {
      refreshQueued = refreshInFlight
        .catch(() => {})
        .then(() => { refreshQueued = null; return refresh(); });
    }
    return refreshQueued;
  }
  refreshInFlight = (async () => {
    const main = $("#main");
    main.classList.add("refreshing");
    try {
      const data = await api("/api/state");
      state.data = data;
      if (data && Object.prototype.hasOwnProperty.call(data, "scenario")) {
        state.worlds.current = data.scenario || null;
      }
      syncSafety(data);
      syncTakeState(data);
      render(data);
      if (!state.takes.probed) loadTakeCurrent();
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
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export function showError(message) {
  const box = $("#error");
  if (!message) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.textContent = message;
}
