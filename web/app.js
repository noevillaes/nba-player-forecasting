"use strict";

/* ------------------------------------------------------------------ */
/* Reference data                                                      */
/* ------------------------------------------------------------------ */
const TEAM = {
  Hawks: "#C8102E", Celtics: "#007A33", Nets: "#1A1A1A", Hornets: "#1D1160", Bulls: "#CE1141",
  Cavaliers: "#860038", Mavericks: "#00538C", Nuggets: "#0E2240", Pistons: "#C8102E", Warriors: "#1D428A",
  Rockets: "#CE1141", Pacers: "#002D62", Clippers: "#C8102E", Lakers: "#552583", Grizzlies: "#5D76A9",
  Heat: "#98002E", Bucks: "#00471B", Timberwolves: "#0C2340", Pelicans: "#0C2340", Knicks: "#006BB6",
  Thunder: "#007AC1", Magic: "#0077C0", "76ers": "#006BB6", Suns: "#1D1160", "Trail Blazers": "#E03A3E",
  Kings: "#5A2D81", Spurs: "#2B2B2B", Raptors: "#CE1141", Jazz: "#002B5C", Wizards: "#002B5C",
};
// secondary colour, used when both teams share almost the same primary
const TEAM_ALT = {
  Hawks: "#26282A", Celtics: "#963821", Nets: "#707271", Hornets: "#00788C", Bulls: "#1A1A1A",
  Cavaliers: "#041E42", Mavericks: "#002B5E", Nuggets: "#8B6F2E", Pistons: "#1D42BA", Warriors: "#A47A00",
  Rockets: "#5A5F63", Pacers: "#A07800", Clippers: "#1D428A", Lakers: "#9A7000", Grizzlies: "#12173F",
  Heat: "#41454A", Bucks: "#7A6A4F", Timberwolves: "#236192", Pelicans: "#85714D", Knicks: "#D5520F",
  Thunder: "#EF3B24", Magic: "#5F6A72", "76ers": "#ED174C", Suns: "#E56020", "Trail Blazers": "#1A1A1A",
  Kings: "#63727A", Spurs: "#6F787E", Raptors: "#1A1A1A", Jazz: "#6B5B00", Wizards: "#E31837",
};
const STAT_NAME = {
  MIN: "Minutes", PTS: "Points", REB: "Rebounds", OREB: "Off. rebounds", DREB: "Def. rebounds",
  AST: "Assists", STL: "Steals", BLK: "Blocks", TO: "Turnovers", PF: "Fouls", FGM: "FG made",
  FGA: "FG attempted", "3PM": "3P made", "3PA": "3P attempted", FTM: "FT made", FTA: "FT attempted",
};
const BOX = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "FGM", "FGA", "3PM", "FTM"];
const DETAIL_ORDER = ["PTS", "MIN", "REB", "AST", "STL", "BLK", "TO", "FGM", "FGA", "3PM", "3PA",
  "FTM", "FTA", "OREB", "DREB", "PF"];
const PERF_ORDER = ["PTS", "REB", "AST", "MIN", "STL", "BLK", "TO", "3PM", "3PA", "FGM", "FGA",
  "FTM", "FTA", "OREB", "DREB", "PF"];
const VIEWS = ["games", "performance", "method"];
const TITLES = { games: "NBA Forecasts", performance: "Track record | NBA Forecasts", method: "How it works | NBA Forecasts" };

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (x) => typeof x === "number" && !Number.isNaN(x);
const NONE = "-";
/** 12 -> "12", 12.34 -> "12.3" */
const fmt = (x, d = 1) => (!isNum(x) ? NONE : Number.isInteger(x) ? String(x) : x.toFixed(d));
/** always one decimal: 17 -> "17.0" */
const f1 = (x) => (!isNum(x) ? NONE : x.toFixed(1));
const round = (x) => (!isNum(x) ? NONE : String(Math.round(x)));
const pct = (x) => `${Math.round(x * 100)}%`;
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const dateOf = (d) => new Date(`${d}T12:00:00`);
const longDate = (d, withYear) => new Intl.DateTimeFormat("en-US",
  { weekday: "long", month: "long", day: "numeric", ...(withYear ? { year: "numeric" } : {}) }).format(dateOf(d));
const shortDate = (d) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(dateOf(d));
const todayISO = () => { const t = new Date(); return new Date(t - t.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
/** "2026-10-23 10:43" -> "10:43 a.m. (UTC−6) on Friday, Oct 23" */
function madeAt(s, withDay = true) {
  if (!s) return "";
  const [d, t] = s.split(" ");
  const [h, mi] = (t || "0:0").split(":").map(Number);
  const time = `${((h + 11) % 12) + 1}:${String(mi).padStart(2, "0")} ${h < 12 ? "a.m." : "p.m."}`;
  const day = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric" }).format(dateOf(d));
  return withDay ? `${time} (UTC−6) on ${day}` : `${time} (UTC−6)`;
}

const hexRGB = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const darkScheme = matchMedia("(prefers-color-scheme: dark)");
/** Team colours are data, so they must stay visible: on the dark theme, near-black
    colours (Nets, Spurs, Raptors' alternate) are lifted toward white. */
function onPage(hex) {
  if (!darkScheme.matches) return hex;
  const rgb = hexRGB(hex);
  const lin = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  const L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  if (L >= 0.05) return hex;
  const mix = rgb.map((v) => Math.round(v + (255 - v) * 0.45));
  return `#${mix.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
function matchupColors(away, home) {
  const a = TEAM[away] || "#5F646C";
  let h = TEAM[home] || "#5F646C";
  const [x, y] = [hexRGB(a), hexRGB(h)];
  if (x.reduce((s, v, i) => s + (v - y[i]) ** 2, 0) < 60 ** 2) h = TEAM_ALT[home] || "#5F646C";
  return { away: onPage(a), home: onPage(h) };
}
const dot = (color) => `<i class="dot" style="--c:${color}" aria-hidden="true"></i>`;

function byMargin(home, away, m) {
  if (!isNum(m)) return NONE;
  if (Math.abs(m) < 0.05) return "Even";
  return `${m > 0 ? home : away} by ${fmt(Math.abs(m))}`;
}

/* ------------------------------------------------------------------ */
/* State (mirrored in the URL so any view can be shared as a link)     */
/* ------------------------------------------------------------------ */
const state = { view: "games", set: "live", date: null, game: null, team: "away", mode: null, open: null, stat: "PTS" };
let scrollToMatch = false;

function readHash() {
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

function writeHash(push = false) {
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

/* ------------------------------------------------------------------ */
/* Data                                                                */
/* ------------------------------------------------------------------ */
const cache = { meta: new Map(), days: new Map(), ready: new Set() };

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`the server answered ${r.status} for ${url}`);
  return r.json();
}
function memo(map, key, load) {
  if (!map.has(key)) {
    map.set(key, load().then((v) => { cache.ready.add(key); return v; })
      .catch((e) => { map.delete(key); throw e; }));
  }
  return map.get(key);
}
const loadMeta = (set) => memo(cache.meta, `meta/${set}`, async () => {
  const m = await getJSON(`data/${set}/meta.json`);
  m.byDate = new Map();
  m.byId = new Map();
  for (const g of m.games) {
    if (!m.byDate.has(g.date)) m.byDate.set(g.date, []);
    m.byDate.get(g.date).push(g);
    m.byId.set(g.id, g);
  }
  return m;
});
const loadDay = (set, d) => memo(cache.days, `day/${set}/${d}`, () =>
  getJSON(`data/${set}/days/${d}.json`).catch(() => ({ date: d, players: [] })));

/* ------------------------------------------------------------------ */
/* Rendering                                                           */
/* ------------------------------------------------------------------ */
let token = 0;
let slateKey = "";

async function render() {
  const my = ++token;
  for (const a of $$(".tabs a")) {
    if (a.dataset.view === state.view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  for (const v of VIEWS) $(`#view-${v}`).hidden = v !== state.view;
  document.title = TITLES[state.view];
  $("#sim-note").hidden = state.set === "live" || state.view === "method";
  if (state.view === "method") renderVersions();

  if (!cache.ready.has(`meta/${state.set}`)) skeletonSlate();
  let m;
  try {
    m = await loadMeta(state.set);
  } catch (e) {
    if (my !== token) return;
    if (state.set !== "live") { state.set = "live"; return render(); }
    $("#load-error-text").textContent =
      `The forecasts didn't load because ${e.message}. Check your connection and try again.`;
    $("#load-error").hidden = false;
    for (const v of VIEWS) if (v !== "method") $(`#view-${v}`).hidden = true;
    return;
  }
  if (my !== token) return;
  $("#load-error").hidden = true;
  $("#dataset").value = state.set;
  if (!m.dates.includes(state.date)) state.date = m.dates[0] ?? null;

  renderStatus(m);
  if (state.view === "games") await renderGames(m, my);
  else if (state.view === "performance") renderPerf(m);
  if (my === token) writeHash();
}

function renderStatus(m) {
  const scored = m.games.filter((g) => g.played).length;
  const parts = [];
  if (m.latest) parts.push(`Latest forecasts published at ${madeAt(m.latest)}.`);
  parts.push(`${m.dates.length} days, ${m.games.length} games forecast, ${scored} scored.`);
  const active = (m.versions || []).find((v) => v.active);
  if (active && state.set === "live") parts.push(`Player model ${active.v}.`);
  $("#status").textContent = parts.join(" ");
}

function skeletonSlate() {
  slateKey = "";
  $("#game-list").innerHTML = Array.from({ length: 5 }, () =>
    `<li class="sk-row" aria-hidden="true"><span class="sk"></span><span class="sk"></span><span class="sk"></span></li>`).join("");
}

/* ------------------------- Model versions ------------------------- */
async function renderVersions() {
  let m;
  try { m = await loadMeta("live"); } catch { return; }
  const vs = m.versions || [];
  $("#versions").innerHTML = vs.map((v) => {
    let when = "not used yet";
    if (v.from) when = v.active ? `in use since ${shortDate(v.from)}` : `${shortDate(v.from)} to ${shortDate(v.to)}`;
    return `<li><b>${esc(v.v)}</b>, ${when}${v.active ? " (current)" : ""}. ${esc(v.text)}</li>`;
  }).join("");
  $("#recal-note").textContent = m.recal
    ? `The current version's ranges were last recalibrated on ${shortDate(m.recal.from)}, with ${m.recal.rows.toLocaleString("en-US")} player-games.`
    : "The current version's ranges haven't been recalibrated yet. That starts once 1,000 player-games are scored.";
}

/* ----------------------------- Games ------------------------------ */
async function renderGames(m, my) {
  const d = state.date;
  const i = m.dates.indexOf(d);
  $("#date-label").textContent = d ? longDate(d, state.set !== "live") : "No forecasts yet";
  $("#prev-day").disabled = i < 0 || i >= m.dates.length - 1;
  $("#next-day").disabled = i <= 0;

  const games = m.byDate.get(d) || [];
  const finals = games.filter((g) => g.played);
  const hits = finals.filter((g) => g.hit === 1).length;
  let lede;
  if (!games.length) lede = "There are no forecasts in this set yet. They appear here the morning of each game day.";
  else if (finals.length === games.length) lede = `${games.length} games, all final. The model picked the winner in ${hits} of ${finals.length}.`;
  else if (finals.length) lede = `${games.length} games, ${finals.length} final. The model picked the winner in ${hits} of ${finals.length} so far.`;
  else {
    const made = games.find((g) => g.made)?.made;
    lede = `${games.length} game${games.length > 1 ? "s" : ""}.` + (made ? ` Forecasts published at ${madeAt(made, false)}, before tip-off.` : "");
  }
  $("#date-sub").textContent = lede;

  if (!games.some((g) => g.id === state.game)) {
    state.game = games[0]?.id ?? null;
    state.team = "away";
    state.open = null;
    state.mode = null;
  }
  renderSlate(games, `${state.set}/${d}`);
  const g = m.byId.get(state.game);
  renderMatchup(g, state.set !== "live");
  if (g) document.title = `${g.away} at ${g.home}, ${shortDate(g.date)} | NBA Forecasts`;
  if (scrollToMatch && g) {
    scrollToMatch = false;
    $("#matchup").scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
  }

  const key = `day/${state.set}/${d}`;
  if (d && !cache.ready.has(key)) skeletonBox();
  const day = d ? await loadDay(state.set, d) : { players: [] };
  if (my !== token) return;
  renderBox(g, day);
}

function renderSlate(games, key) {
  const list = $("#game-list");
  if (key !== slateKey) {
    slateKey = key;
    list.innerHTML = games.length ? games.map(slateRow).join("") :
      `<li class="empty">No games on this day.</li>`;
  }
  for (const b of $$(".row", list)) b.setAttribute("aria-current", b.dataset.id === state.game ? "true" : "false");
}

function slateRow(g) {
  const col = matchupColors(g.away, g.home);
  const p = isNum(g.prob) ? g.prob : 0.5;
  const lost = g.played ? (g.ra > g.rh ? " lost-home" : " lost-away") : "";
  const score = (real, proj) => g.played
    ? `${round(real)}<small>proj. ${f1(proj)}</small>`
    : `${f1(proj)}<small>proj.</small>`;
  const fav = p >= 0.5 ? g.home : g.away;
  const res = g.played
    ? `<b>Final</b> <span class="${g.hit === 1 ? "hit" : "miss"}">${g.hit === 1 ? "Winner picked" : "Winner missed"}</span>`
    : `<b>${esc(fav)} ${pct(Math.max(p, 1 - p))}</b> Total ${f1(g.total)}`;
  const label = g.played
    ? `${g.away} ${g.ra}, ${g.home} ${g.rh}, final. ${g.hit === 1 ? "Winner picked" : "Winner missed"}.`
    : `${g.away} at ${g.home}. Projected ${f1(g.pa)} to ${f1(g.ph)}. ${fav} ${pct(Math.max(p, 1 - p))} to win.`;
  return `<li><button class="row${lost}" data-id="${esc(g.id)}" aria-label="${esc(label)}">
    <span class="t away">${dot(col.away)}<span>${esc(g.away)}</span></span>
    <span class="s away num">${score(g.ra, g.pa)}</span>
    <span class="probbar-wrap" aria-hidden="true">
      <span class="probbar"><span style="flex-basis:${((1 - p) * 100).toFixed(1)}%;--c:${col.away}"></span><span style="flex-basis:${(p * 100).toFixed(1)}%;--c:${col.home}"></span></span>
      <span class="pl"><span>${pct(1 - p)}</span><span>${pct(p)}</span></span>
    </span>
    <span class="s home num">${score(g.rh, g.ph)}</span>
    <span class="t home">${dot(col.home)}<span>${esc(g.home)}</span></span>
    <span class="res">${res}</span>
  </button></li>`;
}

function renderMatchup(g, simulated) {
  const art = $("#matchup");
  art.hidden = !g;
  if (!g) return;
  const col = matchupColors(g.away, g.home);
  const p = isNum(g.prob) ? g.prob : 0.5;
  const today = todayISO();
  $("#match-title").textContent = `${g.away} at ${g.home}`;
  let when;
  if (g.played) when = `Final, ${longDate(g.date, simulated)}.`;
  else if (g.date === today) when = `Tonight. Forecast published at ${madeAt(g.made, false)}.`;
  else if (g.date > today) when = `Upcoming, ${longDate(g.date)}. Forecast published at ${madeAt(g.made)}.`;
  else when = `Result pending. Forecast published at ${madeAt(g.made)}.`;
  $("#match-when").textContent = when;

  const side = (cls, team, color, real, proj, lo, hi) => `
    <div class="side ${cls}">
      <div class="name">${cls === "home" ? "" : dot(color)}<span>${esc(team)}</span>${cls === "home" ? dot(color) : ""}</div>
      <div class="big${g.played ? "" : " proj"}">${g.played ? round(real) : f1(proj)}</div>
      <p class="sub">${g.played ? `Projected ${f1(proj)}, 80% range ${f1(lo)} to ${f1(hi)}` : `Projected. 80% range ${f1(lo)} to ${f1(hi)}`}</p>
    </div>`;
  $("#scoreline").innerHTML = side("away", g.away, col.away, g.ra, g.pa, g.pa10, g.pa90) +
    side("home", g.home, col.home, g.rh, g.ph, g.ph10, g.ph90);

  const bar = $("#probbar");
  if (!bar.children.length) bar.innerHTML = "<span></span><span></span>";
  const [a, h] = bar.children;
  a.style.flexBasis = `${((1 - p) * 100).toFixed(1)}%`;
  h.style.flexBasis = `${(p * 100).toFixed(1)}%`;
  a.style.setProperty("--c", col.away);
  h.style.setProperty("--c", col.home);
  let labels = $("#prob-labels");
  if (!labels) {
    labels = document.createElement("p");
    labels.id = "prob-labels";
    labels.className = "prob-labels";
    bar.after(labels);
  }
  labels.innerHTML = `<span><b>${pct(1 - p)}</b> ${esc(g.away)} win probability</span><span>${esc(g.home)} <b>${pct(p)}</b></span>`;

  const fact = (dt, dd) => `<div><dt>${dt}</dt><dd class="num">${dd}</dd></div>`;
  let facts;
  if (g.played) {
    const margin = g.rh - g.ra;
    facts = [
      fact("Projected total", f1(g.total)),
      fact("Final total", `${g.rh + g.ra} <small class="muted">off by ${f1(g.err_total)}</small>`),
      fact("Projected margin", esc(byMargin(g.home, g.away, g.spread))),
      fact("Final margin", `${esc(margin > 0 ? g.home : g.away)} by ${Math.abs(margin)} <small class="muted">off by ${f1(g.err_spread)}</small>`),
    ];
  } else {
    facts = [
      fact("Projected total", f1(g.total)),
      fact("Projected margin", esc(byMargin(g.home, g.away, g.spread))),
      fact("Favorite", `${esc(p >= 0.5 ? g.home : g.away)} ${pct(Math.max(p, 1 - p))}`),
      fact("Published", madeAt(g.made, false).replace(" (UTC−6)", "")),
    ];
  }
  $("#facts").innerHTML = facts.join("");
  $("#summary").innerHTML = g.played
    ? `<b class="${g.hit === 1 ? "hit" : "miss"}">${g.hit === 1 ? "The model picked the winner." : "The model picked the wrong winner."}</b>`
    : "";
}

function skeletonBox() {
  const table = $("#box");
  table.tHead.innerHTML = `<tr><th scope="col">Player</th>${BOX.map((c) => `<th scope="col">${c}</th>`).join("")}</tr>`;
  table.tBodies[0].innerHTML = Array.from({ length: 8 }, () =>
    `<tr aria-hidden="true"><td class="sk-cell"><span class="sk" style="width:70%"></span></td>${BOX.map(() =>
      `<td class="sk-cell"><span class="sk" style="width:60%;margin:auto"></span></td>`).join("")}</tr>`).join("");
  $("#team-note").textContent = "Loading player forecasts…";
}

function renderBox(g, day) {
  const seg = $("#team-seg");
  const table = $("#box");
  if (!g) {
    seg.innerHTML = "";
    $("#team-note").textContent = "";
    table.tHead.innerHTML = "";
    table.tBodies[0].innerHTML = "";
    return;
  }
  const col = matchupColors(g.away, g.home);
  const team = state.team === "home" ? g.home : g.away;
  seg.innerHTML = ["away", "home"].map((side) => {
    const t = side === "home" ? g.home : g.away;
    return `<button data-team="${side}" aria-pressed="${state.team === side}">${dot(col[side])}${esc(t)}</button>`;
  }).join("");

  const mode = g.played ? (state.mode || "both") : "proj";
  for (const b of $$("#mode-seg button")) {
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
    b.disabled = !g.played && b.dataset.mode !== "proj";
    b.title = b.disabled ? "Available once the game is played" : "";
  }

  const players = day.players.filter((p) => p.g === g.id && p.t === team);
  players.sort((x, y) => (x.st === "dnp") - (y.st === "dnp") || (y.s.MIN?.[0] ?? 0) - (x.s.MIN?.[0] ?? 0));
  const pts = players.reduce((s, p) => s + (p.s.PTS?.[0] ?? 0), 0);
  const adj = players[0]?.adj;
  $("#team-note").textContent = players.length
    ? `${players.length} players, ${Math.round(pts)} projected points between them` +
      (isNum(adj) ? `, scaled ×${adj.toFixed(3)} toward the team-score forecast.` : ".")
    : "";

  table.tHead.innerHTML = `<tr><th scope="col">Player</th>${BOX.map((c) =>
    `<th scope="col"><abbr title="${STAT_NAME[c]}">${c}</abbr></th>`).join("")}</tr>`;
  if (!players.length) {
    table.tBodies[0].innerHTML = `<tr><td colspan="${BOX.length + 1}" class="empty">There are no player forecasts for ${esc(team)} in this game. Players without NBA games have no history to forecast from.</td></tr>`;
    return;
  }
  table.tBodies[0].innerHTML = players.map((p) => {
    const open = state.open === p.id;
    const sub = p.st === "dnp" ? "did not play" : "";
    let html = `<tr class="p${p.st === "dnp" ? " dnp" : ""}" data-id="${esc(p.id)}" tabindex="0" aria-expanded="${open}">
      <td><b>${esc(p.n)}</b>${sub ? `<small>${sub}</small>` : ""}</td>${BOX.map((c) => cell(p, c, mode)).join("")}</tr>`;
    if (open) html += `<tr class="detail"><td colspan="${BOX.length + 1}">${detail(p, team)}</td></tr>`;
    return html;
  }).join("");
}

function cell(p, c, mode) {
  const v = p.s[c];
  if (!v) return `<td>${NONE}</td>`;
  const [fc, lo, hi, , real, , inside] = v;
  const tip = `${STAT_NAME[c]}: forecast ${f1(fc)}, 80% range ${fmt(lo)} to ${fmt(hi)}` +
    (p.st === "played" && isNum(real) ? `, actual ${fmt(real)}` + (inside === 0 ? ", outside the range" : "") : "");
  if (mode === "proj") return `<td title="${tip}"><b>${f1(fc)}</b><small>${fmt(lo)} to ${fmt(hi)}</small></td>`;
  if (p.st === "dnp") return c === "MIN" ? "<td><b>DNP</b></td>" : "<td></td>";
  if (p.st !== "played" || !isNum(real)) return `<td title="${tip}"><b>${NONE}</b></td>`;
  const cls = inside === 0 ? ' class="out"' : "";
  if (mode === "real") return `<td${cls} title="${tip}"><b>${round(real)}</b></td>`;
  return `<td${cls} title="${tip}"><b>${round(real)}</b><small>${f1(fc)}</small></td>`;
}

function detail(p, team) {
  const mins = p.s.MIN?.[4];
  const who = p.st === "played" ? `${team}, played ${round(mins)} minutes`
    : p.st === "dnp" ? `${team}, did not play` : `${team}, game not played yet`;
  const strips = DETAIL_ORDER.filter((c) => p.s[c]).map((c) => strip(c, p.s[c], p.st)).join("");
  return `<div class="detail-inner">
    <div class="detail-head">
      <div><strong>${esc(p.n)}</strong> <span class="who">${esc(who)}</span></div>
      <div class="strip-legend">
        <span><i class="lg-range"></i>80% range</span><span><i class="lg-fc"></i>forecast</span>
        <span><i class="lg-act"></i>actual</span><span><i class="lg-act out"></i>actual outside the range</span>
        <span><i class="lg-avg"></i>last-10 average</span>
      </div>
    </div>
    <div class="strips">${strips}</div></div>`;
}

function strip(c, v, status) {
  const [fc, lo, hi, base, real, err, inside] = v;
  const has = status === "played" && isNum(real);
  const vals = [0, lo, hi, fc, base, has ? real : null].filter(isNum);
  const min = Math.min(...vals);
  let max = Math.max(...vals) * 1.08;
  if (max <= min) max = min + 1;
  const X = (x) => (((x - min) / (max - min)) * 100).toFixed(2);
  const out = has && inside === 0;
  const avg = isNum(base) ? `, last 10: ${fmt(base)}` : "";
  let sub;
  if (has) sub = `forecast ${f1(fc)}${avg}, <em>off by ${fmt(err)}</em>`;
  else if (status === "dnp") sub = `forecast ${f1(fc)}${avg}, did not play`;
  else sub = `forecast${avg}`;
  // range labels sit under the ends of the band (or once, centred, when the band is narrow)
  const xl = +X(lo), xh = +X(hi);
  const lab = (x, text) => {
    const shift = x < 7 ? "0" : x > 93 ? "-100%" : "-50%";
    return `<span style="left:${x}%;transform:translateX(${shift})">${text}</span>`;
  };
  const foot = xh - xl < 26 ? lab((xl + xh) / 2, `${fmt(lo)} to ${fmt(hi)}`) : lab(xl, fmt(lo)) + lab(xh, fmt(hi));
  return `<div class="strip${out ? " out" : ""}">
    <div class="strip-top"><span class="strip-name">${STAT_NAME[c]}</span>
      <span class="strip-val">${has ? fmt(real) : status === "dnp" ? NONE : f1(fc)}</span></div>
    <div class="strip-sub">${sub}</div>
    <div class="track" aria-hidden="true">
      <span class="rng" style="left:${X(lo)}%;width:${(X(hi) - X(lo)).toFixed(2)}%"></span>
      ${isNum(base) ? `<span class="avg" style="left:${X(base)}%"></span>` : ""}
      <span class="fc" style="left:${X(fc)}%"></span>
      ${has ? `<span class="act" style="left:${X(real)}%"></span>` : ""}
    </div>
    <div class="strip-foot" aria-label="80% range ${fmt(lo)} to ${fmt(hi)}">${foot}</div>
  </div>`;
}

/* -------------------------- Track record --------------------------- */
function aggregate(score) {
  const agg = {};
  for (const r of score) {
    const a = (agg[r.s] ??= { n: 0, mae: 0, base: 0, cov: 0 });
    a.n += r.n;
    a.mae += r.n * (r.mae ?? 0);
    a.base += r.n * (r.base ?? 0);
    a.cov += r.n * (r.cov ?? 0);
  }
  return PERF_ORDER.filter((s) => agg[s]?.n).map((s) => {
    const a = agg[s];
    const mae = a.mae / a.n, base = a.base / a.n;
    return { s, n: a.n, mae, base, cov: a.cov / a.n, imp: base ? (1 - mae / base) * 100 : 0 };
  });
}

function renderPerf(m) {
  const played = m.games.filter((g) => g.played);
  const n = played.length;
  const mean = (k) => {
    const v = played.map((g) => g[k]).filter(isNum);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };
  const acc = mean("hit"), brier = mean("brier"), et = mean("err_total"), es = mean("err_spread");
  const cov = n ? played.reduce((s, g) => s + (g.in_h ?? 0) + (g.in_a ?? 0), 0) / (2 * n) : null;
  const fig = (v, l, s) => `<div class="figure"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`;
  $("#figures").innerHTML = n ? [
    fig(isNum(acc) ? pct(acc) : NONE, "Winners picked", `${Math.round(acc * n)} of ${n} scored games.`),
    fig(isNum(brier) ? brier.toFixed(3) : NONE, "Brier score", "Win probability accuracy. A coin flip scores 0.250; lower is better."),
    fig(isNum(cov) ? pct(cov) : NONE, "Team scores in the 80% range", "A well-calibrated range lands near 80%."),
    fig(isNum(et) ? et.toFixed(1) : NONE, "Points off on the total", "Average miss on the combined score."),
    fig(isNum(es) ? es.toFixed(1) : NONE, "Points off on the margin", "Average miss on the final margin."),
    fig(n, "Games scored", "Every played game with a published forecast."),
  ].join("") : `<p class="empty">No games have been scored yet. The first numbers appear the morning after the first game day.</p>`;

  const rows = aggregate(m.score);
  if (!rows.some((r) => r.s === state.stat) && rows.length) state.stat = rows[0].s;
  const top = Math.max(1, ...rows.map((r) => Math.abs(r.imp)));
  $("#perf-table tbody").innerHTML = rows.map((r) => {
    const w = Math.round((Math.abs(r.imp) / top) * 160);
    const txt = r.imp >= 0 ? `${r.imp.toFixed(1)}% less` : `${Math.abs(r.imp).toFixed(1)}% more`;
    return `<tr data-stat="${r.s}" tabindex="0" aria-selected="${r.s === state.stat}">
      <td>${STAT_NAME[r.s]}<small class="muted" style="display:block;font-size:12px">${r.n.toLocaleString("en-US")} player-games</small></td>
      <td class="num">${r.mae.toFixed(2)}</td><td class="num">${r.base.toFixed(2)}</td>
      <td><span class="ibar"><span class="b${r.imp < 0 ? " neg" : ""}" style="width:${w}px"></span><span class="${r.imp < 0 ? "neg" : ""}">${txt}</span></span></td>
      <td class="num">${pct(r.cov)}</td></tr>`;
  }).join("") || `<tr><td colspan="5" class="empty">No scored days yet.</td></tr>`;

  $("#daily-title").textContent = `Day by day: ${STAT_NAME[state.stat] || state.stat}`;
  drawDaily(m.score.filter((r) => r.s === state.stat).sort((a, b) => (a.d < b.d ? -1 : 1)));
}

function drawDaily(rows) {
  const el = $("#daily-chart");
  if (!rows.length) { el.innerHTML = `<p class="empty">No scored days yet.</p>`; return; }
  const W = Math.max(320, el.clientWidth || 800);
  const H = 260;
  const pad = { l: 40, r: 132, t: 16, b: 30 };
  const ys = rows.flatMap((r) => [r.mae, r.base]).filter(isNum);
  const top = Math.max(...ys) * 1.15 || 1;
  const step = niceStep(top / 4);
  const yMax = Math.ceil(top / step) * step;
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const X = (i) => pad.l + (rows.length === 1 ? iw / 2 : (i * iw) / (rows.length - 1));
  const Y = (v) => pad.t + ih - (v / yMax) * ih;

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Average error per day for the model and the 10-game average">`;
  for (let v = 0; v <= yMax + 1e-9; v += step) {
    s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:var(--rule)"/>`;
    s += `<text x="${pad.l - 8}" y="${Y(v) + 4}" text-anchor="end">${+v.toFixed(2)}</text>`;
  }
  const every = Math.ceil(rows.length / Math.max(2, Math.floor(iw / 70)));
  rows.forEach((r, i) => {
    if (i % every === 0 || i === rows.length - 1) s += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle">${shortDate(r.d)}</text>`;
  });
  // a dashed line where a new model version starts
  rows.forEach((r, i) => {
    if (i === 0 || r.m === rows[i - 1].m) return;
    const x = (X(i) + X(i - 1)) / 2;
    s += `<line x1="${x}" x2="${x}" y1="${pad.t}" y2="${pad.t + ih}" style="stroke:var(--ink-2)" stroke-dasharray="2 3"/>`;
    s += `<text x="${x + 5}" y="${pad.t + 10}" style="fill:var(--ink-2)">${esc(r.m)}</text>`;
  });
  const path = (k) => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r[k]).toFixed(1)}`).join("");
  s += `<path d="${path("base")}" fill="none" style="stroke:var(--ink-3)" stroke-width="2" stroke-dasharray="5 4"/>`;
  s += `<path d="${path("mae")}" fill="none" style="stroke:var(--accent)" stroke-width="2.5"/>`;
  rows.forEach((r, i) => {
    const t = `<title>${shortDate(r.d)}: model ${r.m || ""} ${r.mae.toFixed(2)}, 10-game average ${r.base.toFixed(2)}, ${r.n} players</title>`;
    s += `<circle cx="${X(i)}" cy="${Y(r.base)}" r="3.5" style="fill:var(--paper);stroke:var(--ink-3)" stroke-width="1.5">${t}</circle>`;
    s += `<circle cx="${X(i)}" cy="${Y(r.mae)}" r="4" style="fill:var(--accent)">${t}</circle>`;
  });
  const last = rows[rows.length - 1];
  let ym = Y(last.mae) + 4, yb = Y(last.base) + 4;
  if (Math.abs(ym - yb) < 15) { if (ym >= yb) ym = yb + 15; else yb = ym + 15; }
  const lx = X(rows.length - 1) + 12;
  s += `<text class="lbl" x="${lx}" y="${ym}" style="fill:var(--accent)">Model ${last.mae.toFixed(2)}</text>`;
  s += `<text class="lbl" x="${lx}" y="${yb}" style="fill:var(--ink-2)">10-game avg ${last.base.toFixed(2)}</text>`;
  el.innerHTML = s + "</svg>";
}

function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}

/* ------------------------------------------------------------------ */
/* Events                                                              */
/* ------------------------------------------------------------------ */
function go(changes, push = false) {
  Object.assign(state, changes);
  writeHash(push);
  render();
}

function stepDay(dir) {
  const m = cache.meta.get(`meta/${state.set}`);
  if (!m) return;
  m.then((meta) => {
    const i = meta.dates.indexOf(state.date) + dir;
    if (i >= 0 && i < meta.dates.length) go({ date: meta.dates[i], game: null, open: null, mode: null });
  });
}

function bind() {
  for (const a of $$(".tabs a, .brand")) {
    a.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return; // let new-tab clicks through
      e.preventDefault();
      const view = a.dataset.view || "games";
      if (view !== state.view) { go({ view }, true); scrollTo({ top: 0 }); }
    });
  }
  $("#dataset").addEventListener("change", (e) =>
    go({ set: e.target.value, date: null, game: null, open: null, mode: null }, true));
  $("#prev-day").addEventListener("click", () => stepDay(+1));
  $("#next-day").addEventListener("click", () => stepDay(-1));
  $("#retry").addEventListener("click", () => render());

  $("#game-list").addEventListener("click", (e) => {
    const b = e.target.closest(".row");
    if (!b) return;
    scrollToMatch = true;
    if (b.dataset.id !== state.game) go({ game: b.dataset.id, team: "away", open: null, mode: null });
    else render();
  });
  $("#team-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) go({ team: b.dataset.team, open: null });
  });
  $("#mode-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && !b.disabled) go({ mode: b.dataset.mode });
  });
  const togglePlayer = (tr) => go({ open: state.open === tr.dataset.id ? null : tr.dataset.id });
  $("#box").addEventListener("click", (e) => {
    const tr = e.target.closest("tr.p");
    if (tr) togglePlayer(tr);
  });
  $("#box").addEventListener("keydown", (e) => {
    const tr = e.target.closest("tr.p");
    if (tr && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      const id = tr.dataset.id;
      togglePlayer(tr);
      requestAnimationFrame(() => $(`#box tr.p[data-id="${CSS.escape(id)}"]`)?.focus());
    }
  });

  const pickStat = (e) => {
    const el = e.target.closest("[data-stat]");
    if (el) go({ stat: el.dataset.stat });
  };
  $("#perf-table").addEventListener("click", pickStat);
  $("#perf-table").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickStat(e); }
  });

  document.addEventListener("keydown", (e) => {
    if (state.view !== "games" || e.altKey || e.ctrlKey || e.metaKey) return;
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "ArrowLeft") stepDay(+1);
    if (e.key === "ArrowRight") stepDay(-1);
  });

  darkScheme.addEventListener("change", () => { slateKey = ""; render(); });
  window.addEventListener("popstate", () => { readHash(); render(); });
  window.addEventListener("hashchange", () => { readHash(); render(); });

  let t;
  window.addEventListener("resize", () => {
    clearTimeout(t);
    t = setTimeout(() => { if (state.view === "performance") render(); }, 150);
  });
}

async function init() {
  readHash();
  bind();
  render();   // draw right away; the set list fills in when it arrives
  try {
    const sets = await getJSON("data/sets.json");
    $("#dataset").innerHTML = sets.sets.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("");
  } catch {
    $("#dataset").innerHTML = `<option value="live">Live 2026-27</option>`;
  }
  $("#dataset").value = state.set;
}

init();
