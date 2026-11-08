/* Shared DOM, shell and SVG helpers for the switch-world dashboard.

   Every module that touches the document imports from here; nothing in this
   file reaches back into a view module, so it stays safe to load first. */

import { state } from "../state.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const CAST = window.SWITCH_CAST;
export const SECRET_KEY = "user-leaving-city";
export const SVG_NS = "http://www.w3.org/2000/svg";
/* The guest deployment serves Mattermost under /mattermost on the same origin;
   local runs still point at the local port. */
export const MATTERMOST_BASE = ["localhost", "127.0.0.1", ""].includes(location.hostname)
  ? "http://127.0.0.1:8065"
  : `${location.origin}/mattermost`;
export function setTheme(theme) {
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

export function setMotion(on) {
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

export function makePetals() {
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

/* A small fallback chain keeps a planned art path honest: if the new CG has
   not shipped yet, the stage falls back to the existing character art. */
export function setArtWithFallback(img, candidates, alt) {
  if (!img) return;
  const list = [...new Set(candidates.filter((value) => typeof value === "string" && value))];
  if (!list.length) return;
  let index = 0;
  img.onerror = () => {
    index += 1;
    if (index < list.length) {
      img.src = list[index];
      return;
    }
    img.onerror = null;
  };
  img.src = list[0];
  if (alt !== undefined) img.alt = alt;
}
export const tooltip = $("#tooltip");

export function showTip(target, lines) {
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

export function hideTip() {
  tooltip.hidden = true;
}

export function bindTip(element, lines) {
  element.addEventListener("mouseenter", () => showTip(element, lines));
  element.addEventListener("focus", () => showTip(element, lines));
  element.addEventListener("mouseleave", hideTip);
  element.addEventListener("blur", hideTip);
}
export function svgEl(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value != null) node.setAttribute(key, String(value));
  });
  return node;
}

export function addText(parent, x, y, text, cls) {
  const node = svgEl("text", { x, y, class: cls });
  node.textContent = text;
  parent.appendChild(node);
  return node;
}
