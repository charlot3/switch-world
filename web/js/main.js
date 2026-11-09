/* switch-world dashboard entry — wiring and bootstrap only.

   The store lives in state.js, the fetch layer in api.js, pure helpers in
   format.js and the generated vocabulary in vocab.js. View dispatch and the
   poll live in views.js; each render surface is in web/js/render/. */

import { state } from "./state.js";
import { $, $$, CAST, MATTERMOST_BASE, hideTip, setMotion, setTheme } from "./render/dom.js";
import {
  advanceTake,
  closeEnding,
  closeOutfit,
  evaluateEnding,
  loadScenarios,
  loadTakes,
  loadTake,
  nextBeat,
  renderStory,
  resetCurrentScenario,
  sendScene,
  setSafety,
} from "./render/stage.js";
import {
  addFriend,
  closePhone,
  isFriend,
  openPhone,
  phoneTarget,
  sendPhone,
} from "./render/phone.js";
import { closeProfile, renderRelationships } from "./render/ledger.js";
import {
  advanceClock,
  copyLiveCommand,
  fetchTavily,
  loadBriefingStatus,
  loadSceneCard,
  loadStudio,
  prepareBriefing,
  resetWorld,
  runArc,
  runBifrost,
  runLocalBeat,
  setClockMode,
  studioAdvance,
  tellAlice,
} from "./render/studio.js";
import { refresh, setTreeLens, setView } from "./views.js";

export function shellMode() {
  const visual = window.visualViewport ? window.visualViewport.width : window.innerWidth;
  const width = Math.min(window.innerWidth, visual || window.innerWidth);
  document.documentElement.dataset.shell = width <= 760 ? "phone" : width <= 1180 ? "compact" : "wide";
  if (width > 760) closePhone();
}

/* ---- wiring ----------------------------------------------------------- */

setTheme(state.theme);
setMotion(state.motion);
shellMode();
window.addEventListener("resize", shellMode);
if (window.visualViewport) window.visualViewport.addEventListener("resize", shellMode);
setView(state.view);
setTreeLens(state.treeLens);

$$(".rail-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
$$("[data-tree-lens]").forEach((button) => {
  button.addEventListener("click", () => setTreeLens(button.dataset.treeLens));
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
  link.href = `${MATTERMOST_BASE}/switch/channels/world`;
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
$("#ending-close").addEventListener("click", closeEnding);
$("#ending-close-2").addEventListener("click", closeEnding);
$("#ending-story").addEventListener("click", closeEnding);
$("#ending-worlds").addEventListener("click", () => {
  closeEnding();
  setView("worlds");
});
$("#ending-modal").addEventListener("click", (event) => {
  if (event.target.matches("[data-close-ending]")) closeEnding();
});
$("#outfit-close").addEventListener("click", closeOutfit);
$("#outfit-close-2").addEventListener("click", closeOutfit);
$("#outfit-modal").addEventListener("click", (event) => {
  if (event.target.matches("[data-close-outfit]")) closeOutfit();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const ending = $("#ending-modal");
  if (ending && !ending.hidden) {
    closeEnding();
    return;
  }
  const outfit = $("#outfit-modal");
  if (outfit && !outfit.hidden) {
    closeOutfit();
    return;
  }
  if ($(".story-phone")?.classList.contains("is-open")) {
    closePhone();
    return;
  }
  closeProfile();
});
$("#scene-next").addEventListener("click", nextBeat);
$("#scene-say-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#scene-say-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendScene(text, {
    whisper: Boolean($("#whisper-toggle") && $("#whisper-toggle").checked),
    to: $("#whisper-target") ? $("#whisper-target").value : null,
  });
});
$("#whisper-toggle").addEventListener("change", (event) => {
  state.whisper = event.target.checked;
  if (state.data) renderStory(state.data);
});
$("#whisper-target").addEventListener("change", (event) => {
  state.whisperTarget = event.target.value || null;
  if (state.data) renderStory(state.data);
});
$("#studio-refresh").addEventListener("click", () => loadStudio(true));
$("#studio-advance").addEventListener("click", studioAdvance);
$("#safety-toggle").addEventListener("click", () => setSafety(!state.safety.paused));
$("#worlds-refresh").addEventListener("click", () => loadScenarios(true));
$("#worlds-reset").addEventListener("click", resetCurrentScenario);
$("#worlds-evaluate").addEventListener("click", evaluateEnding);
$("#takes-refresh").addEventListener("click", () => loadTakes(true));
$("#takes-next").addEventListener("click", advanceTake);
$("#scene-ending").addEventListener("click", evaluateEnding);
$("#scene-dm").addEventListener("click", () => {
  const target = phoneTarget();
  const cast = CAST[target];
  if (cast && !isFriend(state.data, cast.id)) {
    addFriend(cast.id);
    return;
  }
  openPhone(target);
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
$("#prepare-briefing").addEventListener("click", prepareBriefing);
$("#reset").addEventListener("click", resetWorld);
$("#load-card").addEventListener("click", loadSceneCard);
$("#copy-command").addEventListener("click", copyLiveCommand);

window.addEventListener("scroll", hideTip, { passive: true });
window.addEventListener("resize", hideTip);

if (state.data == null) {
  refresh();
  loadBriefingStatus();
  setInterval(() => {
    if (!document.hidden) refresh();
  }, 2500);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  window.addEventListener("focus", refresh);
}
