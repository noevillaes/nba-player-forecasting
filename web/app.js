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
// three-letter codes for the team badges
const TRI = {
  Hawks: "ATL", Celtics: "BOS", Nets: "BKN", Hornets: "CHA", Bulls: "CHI", Cavaliers: "CLE",
  Mavericks: "DAL", Nuggets: "DEN", Pistons: "DET", Warriors: "GSW", Rockets: "HOU", Pacers: "IND",
  Clippers: "LAC", Lakers: "LAL", Grizzlies: "MEM", Heat: "MIA", Bucks: "MIL", Timberwolves: "MIN",
  Pelicans: "NOP", Knicks: "NYK", Thunder: "OKC", Magic: "ORL", "76ers": "PHI", Suns: "PHX",
  "Trail Blazers": "POR", Kings: "SAC", Spurs: "SAS", Raptors: "TOR", Jazz: "UTA", Wizards: "WAS",
};
const tri = (team) => TRI[team] || String(team).slice(0, 3).toUpperCase();
const badge = (team, color) => `<i class="med" style="--c:${color || TEAM[team] || "#3A4A5C"}" aria-hidden="true">${esc(tri(team))}</i>`;

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

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (x) => typeof x === "number" && !Number.isNaN(x);
/** 12 -> "12", 12.34 -> "12.3" */
const fmt = (x, d = 1) => (!isNum(x) ? "–" : Number.isInteger(x) ? String(x) : x.toFixed(d));
/** always one decimal: 17 -> "17.0" */
const f1 = (x) => (!isNum(x) ? "–" : x.toFixed(1));
const round = (x) => (!isNum(x) ? "–" : String(Math.round(x)));
const pct = (x) => `${Math.round(x * 100)}%`;

function niceDate(d, withYear) {
  const dt = new Date(`${d}T12:00:00`);
  const s = dt.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
  return withYear ? `${s}, ${dt.getFullYear()}` : s;
}
/** "Sat, Oct 24" (with the year for older sets) */
function slateDate(d, withYear) {
  const dt = new Date(`${d}T12:00:00`);
  const s = dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return withYear ? `${s}, ${dt.getFullYear()}` : s;
}
/** today in the viewer's calendar, as YYYY-MM-DD */
const todayISO = () => { const t = new Date(); return new Date(t - t.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
const shortDate = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** "2026-10-23 10:43" -> "Friday, Oct 23 at 10:43 (UTC−6)" */
function madeAt(s) {
  if (!s) return "";
  const [d, t] = s.split(" ");
  return `${niceDate(d)}${t ? ` at ${t}` : ""} (UTC−6)`;
}

const hexRGB = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
function matchupColors(away, home) {
  const a = TEAM[away] || "#3A4A5C";
  let h = TEAM[home] || "#3A4A5C";
  const [x, y] = [hexRGB(a), hexRGB(h)];
  if (x.reduce((s, v, i) => s + (v - y[i]) ** 2, 0) < 60 ** 2) h = TEAM_ALT[home] || "#3A4A5C";
  return { away: a, home: h };
}

function byMargin(home, away, m) {
  if (!isNum(m)) return "";
  if (Math.abs(m) < 0.05) return "a pick'em";
  return `${m > 0 ? home : away} by ${fmt(Math.abs(m))}`;
}

/* ------------------------------------------------------------------ */
/* State (mirrored in the URL so any view can be shared as a link)     */
/* ------------------------------------------------------------------ */
const state = { view: "games", set: "live", date: null, game: null, team: "away", mode: null, open: null, stat: "PTS" };

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
const cache = { meta: new Map(), days: new Map() };

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${r.status} on ${url}`);
  return r.json();
}
function memo(map, key, load) {
  if (!map.has(key)) map.set(key, load().catch((e) => { map.delete(key); throw e; }));
  return map.get(key);
}
const loadMeta = (set) => memo(cache.meta, set, async () => {
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
const loadDay = (set, d) => memo(cache.days, `${set}/${d}`, () =>
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
  if (state.view === "method") { document.title = "How it works | NBA Forecasts"; renderVersions(); }

  let m;
  try {
    m = await loadMeta(state.set);
  } catch (e) {
    if (my !== token) return;
    if (state.set !== "live") { state.set = "live"; return render(); }
    const err = $("#load-error");
    err.textContent = `Couldn't load the forecasts (${e.message}). Reload the page to try again.`;
    err.hidden = false;
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
  if (m.latest) parts.push(`Latest forecasts made ${madeAt(m.latest)}.`);
  parts.push(`${m.dates.length} days, ${m.games.length} games forecast, ${scored} already scored.`);
  const active = (m.versions || []).find((v) => v.active);
  if (active && state.set === "live") parts.push(`Player model ${active.v}.`);
  $("#status").textContent = parts.join(" ");
}

/* ------------------------- Model versions ------------------------- */
async function renderVersions() {
  let m;
  try { m = await loadMeta("live"); } catch { return; }
  const list = $("#versions");
  const vs = m.versions || [];
  list.innerHTML = vs.map((v) => {
    let when = "not used yet";
    if (v.from) when = v.active ? `in use since ${shortDate(v.from)}` : `${shortDate(v.from)} to ${shortDate(v.to)}`;
    return `<li><b>${esc(v.v)}</b>, ${when}${v.active ? " (current)" : ""}. ${esc(v.text)}</li>`;
  }).join("");
  $("#recal-note").textContent = m.recal
    ? `The current version's ranges were last recalibrated on ${shortDate(m.recal.from)}, with ${m.recal.rows.toLocaleString("en-US")} player-games.`
    : "The current version's ranges haven't been recalibrated yet: that waits for at least 1,000 scored player-games.";
}

/* ----------------------------- Games ------------------------------ */
async function renderGames(m, my) {
  const d = state.date;
  const i = m.dates.indexOf(d);
  $("#date-label").textContent = d ? slateDate(d, state.set !== "live") : "No games yet";
  $("#prev-day").disabled = i < 0 || i >= m.dates.length - 1;
  $("#next-day").disabled = i <= 0;

  const games = m.byDate.get(d) || [];
  const finals = games.filter((g) => g.played);
  const hits = finals.filter((g) => g.hit === 1).length;
  $("#date-sub").textContent = !games.length ? "" : finals.length
    ? `${games.length} games, winner picked in ${hits} of ${finals.length}`
    : `${games.length} game${games.length > 1 ? "s" : ""}, forecasts published`;
  if (!games.some((g) => g.id === state.game)) {
    state.game = games[0]?.id ?? null;
    state.team = "away";
    state.open = null;
    state.mode = null;
  }
  renderSlate(games, `${state.set}/${d}`);
  const g = m.byId.get(state.game);
  renderBand(g);
  renderSummary(g);
  document.title = g ? `${g.away} at ${g.home}, ${shortDate(g.date)} | NBA Forecasts` : "NBA Forecasts";

  const day = d ? await loadDay(state.set, d) : { players: [] };
  if (my !== token) return;
  renderBox(g, day);
}

function renderSlate(games, key) {
  const list = $("#game-list");
  if (key !== slateKey) {
    slateKey = key;
    list.innerHTML = games.length ? games.map(slateItem).join("") :
      `<li class="empty">No games on this day.</li>`;
    list.scrollTop = 0;
    list.scrollLeft = 0;
  }
  for (const b of $$(".chip", list)) {
    const on = b.dataset.id === state.game;
    b.setAttribute("aria-current", on ? "true" : "false");
    if (on) b.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

function slateItem(g) {
  const cls = g.played ? (g.hit === 1 ? "hit" : "miss") : "pending";
  const winner = g.played ? (g.ra > g.rh ? "away" : "home") : null;
  const col = matchupColors(g.away, g.home);
  const row = (side, team, proj, real) => `
    <span class="r${winner && winner !== side ? " lose" : ""}">
      ${badge(team, col[side])}<span class="tm">${esc(team)}</span>
      <span class="pj">${g.played ? f1(proj) : ""}</span>
      <span class="sc">${g.played ? round(real) : round(proj)}</span>
    </span>`;
  const line = g.played
    ? `Final, <b>${g.hit === 1 ? "winner picked" : "winner missed"}</b>`
    : `Projected, ${pct(isNum(g.prob) ? Math.max(g.prob, 1 - g.prob) : 0.5)} ${tri(g.prob >= 0.5 ? g.home : g.away)}`;
  const label = g.played
    ? `${g.away} ${g.ra}, ${g.home} ${g.rh}, final`
    : `${g.away} at ${g.home}, projected ${f1(g.pa)} to ${f1(g.ph)}`;
  return `<li><button class="chip ${cls}" data-id="${esc(g.id)}" aria-label="${esc(label)}">
    ${row("away", g.away, g.pa, g.ra)}${row("home", g.home, g.ph, g.rh)}
    <span class="st">${line}</span></button></li>`;
}

function renderBand(g) {
  const hero = $("#band");
  if (!g) {
    hero.innerHTML = "";
    hero.hidden = true;
    $("#info-away").textContent = "";
    $("#info-home").textContent = "";
    return;
  }
  hero.hidden = false;
  if (!hero.children.length) {
    const side = (cls) => `<div class="side ${cls}"><span class="code"></span>
      <div class="who"><span class="tn"></span><span class="where"></span><span class="big"></span></div></div>`;
    hero.innerHTML = side("away") + side("home") +
      `<span class="circle" aria-hidden="true"></span><span class="state"></span><span class="odds"></span>`;
  }
  const col = matchupColors(g.away, g.home);
  const p = isNum(g.prob) ? g.prob : 0.5;
  // the split sits at the away team's win probability (kept off the edges so names fit)
  const x = Math.min(78, Math.max(22, (1 - p) * 100));
  hero.style.setProperty("--x", `${x.toFixed(1)}%`);
  const a = $(".away", hero), h = $(".home", hero);
  a.style.backgroundColor = col.away;
  h.style.backgroundColor = col.home;
  for (const [el, team, real, proj, prob, where] of
    [[a, g.away, g.ra, g.pa, 1 - p, "Away"], [h, g.home, g.rh, g.ph, p, "Home"]]) {
    $(".code", el).textContent = tri(team);
    $(".tn", el).textContent = team;
    $(".where", el).textContent = `${where}, ${pct(prob)} to win`;
    const big = $(".big", el);
    big.classList.toggle("proj", !g.played);
    big.innerHTML = g.played ? round(real) : `${f1(proj)}<small>proj.</small>`;
  }
  const today = todayISO();
  $(".state", hero).textContent = g.played ? "Final"
    : g.date === today ? "Tonight" : g.date > today ? "Upcoming" : "Result pending";
  $(".odds", hero).textContent = `${tri(g.away)} ${pct(1 - p)} | ${pct(p)} ${tri(g.home)}`;
  const info = (team, pts, lo, hi) =>
    `<strong>${esc(team)}</strong> projected ${f1(pts)}, 80% range ${f1(lo)} to ${f1(hi)}`;
  $("#info-away").innerHTML = info(g.away, g.pa, g.pa10, g.pa90);
  $("#info-home").innerHTML = info(g.home, g.ph, g.ph10, g.ph90);
}

function renderSummary(g) {
  const el = $("#summary");
  if (!g) { el.textContent = ""; return; }
  let s = esc(`Projected total ${f1(g.total)}, ${byMargin(g.home, g.away, g.spread)}. `);
  if (g.played) {
    const margin = g.rh - g.ra;
    s += esc(`Final total ${g.rh + g.ra} (off by ${f1(g.err_total)}); ${margin > 0 ? g.home : g.away} won by ` +
      `${Math.abs(margin)} (margin off by ${f1(g.err_spread)}). `) +
      `<span class="verdict ${g.hit === 1 ? "hit" : "miss"}">` +
      (g.hit === 1 ? "The model picked the winner." : "The model picked the wrong winner.") + "</span>";
  } else {
    s += esc(g.made ? `Not played yet. Forecast made ${madeAt(g.made)}.` : "Not played yet.");
  }
  el.innerHTML = s;
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
    return `<button data-team="${side}" aria-pressed="${state.team === side}" style="--accent:${col[side]}">` +
      `${badge(t, col[side])}${esc(t)}</button>`;
  }).join("");
  table.style.setProperty("--accent", col[state.team]);

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
    : "No player forecasts for this game.";

  table.tHead.innerHTML = `<tr><th scope="col">Player</th>${BOX.map((c) =>
    `<th scope="col" title="${STAT_NAME[c]}">${c}</th>`).join("")}</tr>`;
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
  if (!v) return "<td>–</td>";
  const [fc, lo, hi, , real, , inside] = v;
  const tip = `${STAT_NAME[c]}: forecast ${f1(fc)}, 80% range ${fmt(lo)} to ${fmt(hi)}` +
    (p.st === "played" && isNum(real) ? `, actual ${fmt(real)}` : "");
  if (mode === "proj") return `<td title="${tip}"><b>${f1(fc)}</b><small>${fmt(lo)}–${fmt(hi)}</small></td>`;
  if (p.st === "dnp") return c === "MIN" ? "<td><b>DNP</b></td>" : "<td></td>";
  if (p.st !== "played" || !isNum(real)) return `<td title="${tip}"><b>–</b></td>`;
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
  const foot = xh - xl < 22 ? lab((xl + xh) / 2, `${fmt(lo)}–${fmt(hi)}`) : lab(xl, fmt(lo)) + lab(xh, fmt(hi));
  return `<div class="strip${out ? " out" : ""}">
    <div class="strip-top"><span class="strip-name">${STAT_NAME[c]}</span>
      <span class="strip-val">${has ? fmt(real) : status === "dnp" ? "–" : f1(fc)}</span></div>
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

/* -------------------------- Performance --------------------------- */
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
  document.title = "Model performance | NBA Forecasts";
  const played = m.games.filter((g) => g.played);
  const n = played.length;
  const mean = (k) => {
    const v = played.map((g) => g[k]).filter(isNum);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };
  const acc = mean("hit"), brier = mean("brier"), et = mean("err_total"), es = mean("err_spread");
  const cov = n ? played.reduce((s, g) => s + (g.in_h ?? 0) + (g.in_a ?? 0), 0) / (2 * n) : null;
  const fig = (v, l, s, key) => `<div class="figure${key ? " key" : ""}"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`;
  $("#figures").innerHTML = [
    fig(n, "Games scored", "played games with a forecast"),
    fig(isNum(acc) ? pct(acc) : "–", "Winners picked", isNum(acc) ? `${Math.round(acc * n)} of ${n}` : "", true),
    fig(isNum(brier) ? brier.toFixed(3) : "–", "Brier score", "0.250 is a coin flip"),
    fig(isNum(et) ? et.toFixed(1) : "–", "Total points error", "average, in points"),
    fig(isNum(es) ? es.toFixed(1) : "–", "Margin error", "average, in points"),
    fig(isNum(cov) ? pct(cov) : "–", "Team scores in 80% range", "should land near 80%"),
  ].join("");

  const rows = aggregate(m.score);
  if (!rows.some((r) => r.s === state.stat) && rows.length) state.stat = rows[0].s;
  $("#perf-table tbody").innerHTML = rows.map((r) => `
    <tr data-stat="${r.s}" tabindex="0" aria-selected="${r.s === state.stat}">
      <td>${STAT_NAME[r.s]}</td><td>${r.n}</td><td>${r.mae.toFixed(2)}</td><td>${r.base.toFixed(2)}</td>
      <td class="imp${r.imp < 0 ? " neg" : ""}">${r.imp >= 0 ? "+" : "−"}${Math.abs(r.imp).toFixed(1)}%</td>
      <td>${pct(r.cov)}</td></tr>`).join("") ||
    `<tr><td colspan="6" class="empty">No scored days yet.</td></tr>`;

  // improvement bars
  const lo = Math.min(0, ...rows.map((r) => r.imp));
  const hi = Math.max(5, ...rows.map((r) => r.imp)) * 1.18;
  const X = (v) => ((v - lo) / (hi - lo)) * 100;
  $("#bars").innerHTML = rows.map((r) => {
    const x0 = X(0), xv = X(r.imp), sel = r.s === state.stat ? " sel" : "";
    return `<div class="bl${sel}" data-stat="${r.s}">${STAT_NAME[r.s]}</div>
      <div class="bt${sel}" data-stat="${r.s}" title="${STAT_NAME[r.s]}: ${r.imp.toFixed(1)}% less error">
        <span class="zero" style="left:${x0}%"></span>
        <span class="b${r.imp < 0 ? " neg" : ""}" style="left:${Math.min(x0, xv)}%;width:${Math.abs(xv - x0)}%"></span>
        <span class="bv" style="${r.imp >= 0 ? `left:calc(${xv}% + 6px)` : `right:calc(${100 - xv}% + 6px)`}">${r.imp.toFixed(1)}</span>
      </div>`;
  }).join("");

  $("#daily-title").textContent = `Day by day: ${STAT_NAME[state.stat] || state.stat}`;
  drawDaily(m.score.filter((r) => r.s === state.stat).sort((a, b) => (a.d < b.d ? -1 : 1)));
}

function drawDaily(rows) {
  const el = $("#daily-chart");
  if (!rows.length) { el.innerHTML = `<p class="empty">No scored days yet.</p>`; return; }
  const W = Math.max(320, el.clientWidth || 800);
  const H = 240;
  const pad = { l: 44, r: 128, t: 14, b: 30 };
  const ys = rows.flatMap((r) => [r.mae, r.base]).filter(isNum);
  const top = Math.max(...ys) * 1.15 || 1;
  const step = niceStep(top / 4);
  const yMax = Math.ceil(top / step) * step;
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const X = (i) => pad.l + (rows.length === 1 ? iw / 2 : (i * iw) / (rows.length - 1));
  const Y = (v) => pad.t + ih - (v / yMax) * ih;

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Average error per day, model against last-10 average">`;
  for (let v = 0; v <= yMax + 1e-9; v += step) {
    s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:var(--rule)"/>`;
    s += `<text x="${pad.l - 8}" y="${Y(v) + 4}" text-anchor="end">${+v.toFixed(2)}</text>`;
  }
  const every = Math.ceil(rows.length / Math.max(2, Math.floor(iw / 70)));
  rows.forEach((r, i) => {
    if (i % every === 0 || i === rows.length - 1) {
      s += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle">${shortDate(r.d)}</text>`;
    }
  });
  // a dashed line where a new model version starts
  rows.forEach((r, i) => {
    if (i === 0 || r.m === rows[i - 1].m) return;
    const x = rows.length === 1 ? X(i) : (X(i) + X(i - 1)) / 2;
    s += `<line x1="${x}" x2="${x}" y1="${pad.t}" y2="${pad.t + ih}" style="stroke:var(--ink-2)" stroke-dasharray="2 3"/>`;
    s += `<text x="${x + 5}" y="${pad.t + 10}" style="fill:var(--ink-2)">${esc(r.m)}</text>`;
  });
  const path = (k) => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r[k]).toFixed(1)}`).join("");
  s += `<path d="${path("base")}" fill="none" style="stroke:var(--ink-3)" stroke-width="2" stroke-dasharray="5 4"/>`;
  s += `<path d="${path("mae")}" fill="none" style="stroke:var(--bar)" stroke-width="2.5"/>`;
  rows.forEach((r, i) => {
    const t = `<title>${shortDate(r.d)}: model ${r.m || ""} ${r.mae.toFixed(2)}, last-10 average ${r.base.toFixed(2)}, ${r.n} players</title>`;
    s += `<circle cx="${X(i)}" cy="${Y(r.base)}" r="3.5" style="fill:var(--surface);stroke:var(--ink-3)" stroke-width="1.5">${t}</circle>`;
    s += `<circle cx="${X(i)}" cy="${Y(r.mae)}" r="4" style="fill:var(--bar)">${t}</circle>`;
  });
  const last = rows[rows.length - 1];
  let ym = Y(last.mae) + 4, yb = Y(last.base) + 4;
  if (Math.abs(ym - yb) < 15) { if (ym >= yb) { ym = yb + 15; } else { yb = ym + 15; } }
  const lx = X(rows.length - 1) + 12;
  s += `<text class="lbl" x="${lx}" y="${ym}" style="fill:var(--bar)">Model ${last.mae.toFixed(2)}</text>`;
  s += `<text class="lbl" x="${lx}" y="${yb}" style="fill:var(--ink-2)">Last-10 avg ${last.base.toFixed(2)}</text>`;
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
  const m = cache.meta.get(state.set);
  if (!m) return;
  m.then((meta) => {
    const i = meta.dates.indexOf(state.date) + dir;
    if (i >= 0 && i < meta.dates.length) go({ date: meta.dates[i], game: null, open: null, mode: null });
  });
}

function bind() {
  for (const a of $$(".tabs a, .brand")) {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const view = a.dataset.view || "games";
      if (view !== state.view) go({ view }, true);
    });
  }
  $("#dataset").addEventListener("change", (e) =>
    go({ set: e.target.value, date: null, game: null, open: null, mode: null }, true));
  $("#prev-day").addEventListener("click", () => stepDay(+1));
  $("#next-day").addEventListener("click", () => stepDay(-1));

  $("#game-list").addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (b && b.dataset.id !== state.game) go({ game: b.dataset.id, team: "away", open: null, mode: null });
  });
  // a mouse wheel scrolls the ticker sideways
  $("#game-list").addEventListener("wheel", (e) => {
    const el = e.currentTarget;
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && el.scrollWidth > el.clientWidth) {
      el.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }, { passive: false });
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
  $("#perf-table").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickStat(e); } });
  $("#bars").addEventListener("click", pickStat);

  document.addEventListener("keydown", (e) => {
    if (state.view !== "games" || e.altKey || e.ctrlKey || e.metaKey) return;
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "ArrowLeft") stepDay(+1);
    if (e.key === "ArrowRight") stepDay(-1);
  });

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
  try {
    const sets = await getJSON("data/sets.json");
    $("#dataset").innerHTML = sets.sets.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("");
  } catch {
    $("#dataset").innerHTML = `<option value="live">Live 2026-27</option>`;
  }
  render();
}

init();
