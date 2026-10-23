// What the page is showing (mirrored in the URL so every view can be shared) and the data behind it.

import { STAT_NAME } from "./stats.js";

export const VIEWS = ["games", "performance", "method"];

export const state = {
  view: "games", set: "live", date: null, game: null, team: "away", mode: null, open: null, stat: "PTS",
};

export function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.view = VIEWS.includes(p.get("view")) ? p.get("view") : "games";
  state.set = p.get("set") || "live";
  state.date = p.get("date");
  state.game = p.get("game");
  state.team = p.get("team") === "home" ? "home" : "away";
  state.stat = STAT_NAME[p.get("stat")] ? p.get("stat") : "PTS";
  state.open = null;
  state.mode = null;
}

export function writeHash(push = false) {
  const p = new URLSearchParams();
  p.set("view", state.view);
  if (state.set !== "live") p.set("set", state.set);
  if (state.view === "games") {
    if (state.date) p.set("date", state.date);
    if (state.game) p.set("game", state.game);
    if (state.team === "home") p.set("team", "home");
  }
  if (state.view === "performance" && state.stat !== "PTS") p.set("stat", state.stat);
  const h = `#${p}`;
  if (h !== location.hash) history[push ? "pushState" : "replaceState"](null, "", h);
}

/* ---------- data ---------- */
// One promise per file. `ready` lists the files already in memory, so callers know
// whether showing them will be instant (no skeleton, safe to animate).
const files = new Map();
const ready = new Set();

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`the server answered ${r.status} for ${url}`);
  return r.json();
}

function once(url, prepare = (x) => x) {
  if (!files.has(url)) {
    files.set(url, getJSON(url).then((data) => { ready.add(url); return prepare(data); })
      .catch((e) => { files.delete(url); throw e; }));
  }
  return files.get(url);
}

const metaURL = (set) => `data/${set}/meta.json`;
const dayURL = (set, d) => `data/${set}/days/${d}.json`;

export const isReadyMeta = (set) => ready.has(metaURL(set));
export const isReadyDay = (set, d) => ready.has(dayURL(set, d));

export const loadSets = () => once("data/sets.json");

export const loadMeta = (set) => once(metaURL(set), (m) => {
  m.byDate = new Map();
  m.byId = new Map();
  for (const g of m.games) {
    if (!m.byDate.has(g.date)) m.byDate.set(g.date, []);
    m.byDate.get(g.date).push(g);
    m.byId.set(g.id, g);
  }
  return m;
});

/** A day with games but no player file (it happens before the first forecast run) is shown as empty. */
export const loadDay = (set, d) => once(dayURL(set, d)).catch(() => ({ date: d, players: [] }));
