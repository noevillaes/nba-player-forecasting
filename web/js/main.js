// Wires the views together: one render loop, URL state, transitions and events.

import { VIEWS, state, readHash, writeHash, loadSets, loadMeta, loadDay, isReadyMeta, isReadyDay } from "./store.js";
import { renderGames, resetGames, skeletonSlate, toggleDetail } from "./games.js";
import { renderRecord, drawDaily } from "./record.js";
import { renderVersions } from "./method.js";
import { darkScheme } from "./teams.js";
import { $, $$, esc, published, reduceMotion } from "./format.js";

const TITLES = { games: "NBA Forecasts", performance: "Track record | NBA Forecasts", method: "How it works | NBA Forecasts" };
let token = 0;

/* ------------------------------------------------------------------ */
/* Rendering                                                           */
/* ------------------------------------------------------------------ */
function showView() {
  for (const a of $$(".tabs a")) {
    if (a.dataset.view === state.view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  for (const v of VIEWS) $(`#view-${v}`).hidden = v !== state.view;
  for (const el of $$("#court [data-for]")) el.hidden = !el.dataset.for.split(" ").includes(state.view);
  $("#court").dataset.view = state.view;
  $("#sim-note").hidden = state.set === "live" || state.view === "method";
  document.title = TITLES[state.view];
}

async function render() {
  const my = ++token;
  const isCurrent = () => my === token;
  showView();
  if (state.view === "method") loadMeta("live").then(renderVersions).catch(() => {});
  if (state.view === "games" && !isReadyMeta(state.set)) skeletonSlate();

  let m;
  try {
    m = await loadMeta(state.set);
  } catch (e) {
    if (!isCurrent()) return;
    if (state.set !== "live") { state.set = "live"; return render(); }
    $("#load-error-text").textContent =
      `The forecasts didn't load because ${e.message}. Check your connection and try again.`;
    $("#load-error").hidden = false;
    $("#court").dataset.state = "error";
    $("#date-label").textContent = "Forecasts unavailable";
    $("#day-facts").innerHTML = "";
    $("#prev-day").disabled = $("#next-day").disabled = true;
    for (const v of VIEWS) if (v !== "method") $(`#view-${v}`).hidden = true;
    return;
  }
  if (!isCurrent()) return;
  $("#load-error").hidden = true;
  delete $("#court").dataset.state;
  $("#dataset").value = state.set;
  if (!m.dates.includes(state.date)) state.date = m.dates[0] ?? null;

  renderStatus(m);
  if (state.view === "games") {
    await renderGames(m, isCurrent);
    prefetchNeighbors(m);
  } else if (state.view === "performance") {
    renderRecord(m);
  }
  if (isCurrent()) writeHash();
}

function renderStatus(m) {
  const scored = m.games.filter((g) => g.played).length;
  const active = (m.versions || []).find((v) => v.active);
  $("#status").textContent = [
    m.latest ? `Latest forecasts published at ${published(m.latest)}.` : "",
    `${m.dates.length} days, ${m.games.length} games forecast, ${scored} scored.`,
    active && state.set === "live" ? `Player model ${active.v}.` : "",
  ].filter(Boolean).join(" ");
}

/** Keep the previous and next day in memory so switching days is instant (and can animate). */
function prefetchNeighbors(m) {
  const i = m.dates.indexOf(state.date);
  for (const j of [i - 1, i + 1]) if (m.dates[j]) loadDay(state.set, m.dates[j]);
}

/* ------------------------------------------------------------------ */
/* Transitions                                                         */
/* ------------------------------------------------------------------ */
// kind: "next" | "prev" (day changes slide), "game" | "swap" | "view" (cross-fades)
function transition(kind, update) {
  if (!kind || !document.startViewTransition || reduceMotion()) return update();
  const root = document.documentElement;
  root.dataset.vt = kind;
  const t = document.startViewTransition(update);
  t.finished.finally(() => { if (root.dataset.vt === kind) delete root.dataset.vt; });
  return t.updateCallbackDone.catch(() => {});
}

/** Animating is only safe when the target is already in memory; otherwise the page would freeze while loading. */
const inMemory = () => isReadyMeta(state.set) &&
  (state.view !== "games" || !state.date || isReadyDay(state.set, state.date));

function go(changes, { push = false, kind = null, toTop = false } = {}) {
  Object.assign(state, changes);
  writeHash(push);
  const update = async () => { await render(); if (toTop) scrollTo({ top: 0 }); };
  return transition(inMemory() ? kind : null, update);
}

function stepDay(dir) {
  loadMeta(state.set).then((m) => {
    const i = m.dates.indexOf(state.date) + dir;
    if (i >= 0 && i < m.dates.length) {
      go({ date: m.dates[i], game: null, open: null, mode: null }, { kind: dir > 0 ? "prev" : "next" });
    }
  }).catch(() => {});
}

function scrollToMatchup() {
  $("#matchup").scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
}

/* ------------------------------------------------------------------ */
/* Events                                                              */
/* ------------------------------------------------------------------ */
function bind() {
  for (const a of $$(".tabs a, .brand")) {
    a.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return; // new tab/window
      e.preventDefault();
      const view = a.dataset.view || "games";
      if (view !== state.view) go({ view }, { push: true, kind: "view", toTop: true });
    });
  }
  $("#dataset").addEventListener("change", (e) =>
    go({ set: e.target.value, date: null, game: null, open: null, mode: null }, { push: true, kind: "view" }));
  $("#prev-day").addEventListener("click", () => stepDay(+1));
  $("#next-day").addEventListener("click", () => stepDay(-1));
  $("#retry").addEventListener("click", () => render());

  $("#game-list").addEventListener("click", (e) => {
    const b = e.target.closest(".row");
    if (!b) return;
    if (b.dataset.id === state.game) { scrollToMatchup(); return; }
    go({ game: b.dataset.id, team: "away", open: null, mode: null }, { kind: "game" }).then(scrollToMatchup);
  });
  $("#team-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && b.dataset.team !== state.team) go({ team: b.dataset.team, open: null }, { kind: "swap" });
  });
  $("#mode-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && !b.disabled) go({ mode: b.dataset.mode }, { kind: "swap" });
  });
  // a click anywhere on a player's row opens it; the name button makes it reachable by keyboard
  $("#box").addEventListener("click", (e) => {
    const tr = e.target.closest("tr.p");
    if (tr) toggleDetail(tr.dataset.id);
  });
  $("#perf-table").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-stat]");
    if (tr && tr.dataset.stat !== state.stat) go({ stat: tr.dataset.stat });
  });

  document.addEventListener("keydown", (e) => {
    if (state.view !== "games" || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (e.target.closest("input, select, textarea, table")) return;
    if (e.key === "ArrowLeft") stepDay(+1);
    if (e.key === "ArrowRight") stepDay(-1);
  });

  // popstate covers back/forward and edits to the # part of the address
  addEventListener("popstate", () => { readHash(); transition(inMemory() ? "view" : null, render); });
  darkScheme.addEventListener("change", () => { resetGames(); render(); });

  let t;
  addEventListener("resize", () => {
    clearTimeout(t);
    t = setTimeout(() => { if (state.view === "performance") drawDaily(); }, 150);
  });
}

async function init() {
  readHash();
  bind();
  render();   // draw right away; the list of sets fills in when it arrives
  try {
    const sets = await loadSets();
    $("#dataset").innerHTML = sets.sets.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("");
  } catch {
    $("#dataset").innerHTML = '<option value="live">Live 2026-27</option>';
  }
  $("#dataset").value = state.set;
}

init();
