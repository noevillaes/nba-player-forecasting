// The Games view: the day's slate, the selected matchup and its player forecasts.
// Controls are created once and updated in place, so keyboard focus survives every change.

import { state, loadDay, isReadyDay } from "./store.js";
import { STAT_NAME, BOX, DETAIL_ORDER, unpack } from "./stats.js";
import { matchupColors, dot } from "./teams.js";
import {
  $, $$, esc, isNum, NONE, fmt, f1, round, pct, longDate, todayISO, clock, published, byMargin,
} from "./format.js";

const built = { slate: "", seg: "", box: "" };   // what each region currently shows

export function resetGames() { built.slate = built.seg = built.box = ""; }

/* ------------------------------------------------------------------ */
/* Entry point                                                         */
/* ------------------------------------------------------------------ */
export async function renderGames(m, isCurrent) {
  const d = state.date;
  const games = m.byDate.get(d) || [];
  if (!games.some((g) => g.id === state.game)) {
    state.game = games[0]?.id ?? null;
    state.team = "away";
    state.open = null;
    state.mode = null;
  }
  renderHead(m, d, games);
  renderSlate(games);
  const g = m.byId.get(state.game);
  renderMatchup(g);
  document.title = g ? `${g.away} at ${g.home}, ${longDate(g.date)} | NBA Forecasts` : "NBA Forecasts";

  if (d && !isReadyDay(state.set, d)) skeletonBox();
  const day = d ? await loadDay(state.set, d) : { players: [] };
  if (!isCurrent()) return;
  renderBox(g, day);
}

/* ------------------------------------------------------------------ */
/* The band: date and the day in three numbers                         */
/* ------------------------------------------------------------------ */
function renderHead(m, d, games) {
  const i = m.dates.indexOf(d);
  $("#date-label").textContent = d ? longDate(d, state.set !== "live") : "No forecasts yet";
  $("#prev-day").disabled = i < 0 || i >= m.dates.length - 1;
  $("#next-day").disabled = i <= 0;

  const finals = games.filter((g) => g.played);
  const hits = finals.filter((g) => g.hit === 1).length;
  const made = games.find((g) => g.made)?.made;
  const fact = (label, value, note = "") =>
    `<div><dt>${label}</dt><dd>${value}${note ? ` <small>${note}</small>` : ""}</dd></div>`;
  const facts = [];
  if (!games.length) {
    facts.push(fact("Games", "0", "Forecasts appear the morning of each game day."));
  } else if (!finals.length) {
    const close = games.reduce((a, b) => (Math.abs((b.prob ?? .5) - .5) < Math.abs((a.prob ?? .5) - .5) ? b : a));
    facts.push(fact("Games", games.length));
    facts.push(fact("Closest call", `${esc(close.away)} at ${esc(close.home)}`,
      `${pct(Math.max(close.prob, 1 - close.prob))} for ${esc(close.prob >= .5 ? close.home : close.away)}`));
    if (made) facts.push(fact("Published", clock(made), "before tip-off"));
  } else {
    const miss = finals.map((g) => g.err_total).filter(isNum);
    facts.push(fact("Games", games.length, finals.length < games.length ? `${finals.length} final` : "all final"));
    facts.push(fact("Winners picked", `${hits} of ${finals.length}`));
    if (miss.length) facts.push(fact("Average miss on totals", `${(miss.reduce((s, x) => s + x, 0) / miss.length).toFixed(1)}`, "points"));
  }
  $("#day-facts").innerHTML = facts.join("");

  // label the points columns by what they hold
  const label = finals.length ? "Points" : "Projected";
  $("#pts-label-a").textContent = label;
  $("#pts-label-h").textContent = label;
  $("#slate-cap").textContent = !games.length ? "" : !finals.length ? "Projected points and win probability."
    : finals.length === games.length ? "Final scores, with the projection under each one."
      : "Final scores where games are over, projections for the rest.";
}

/* ------------------------------------------------------------------ */
/* Slate                                                               */
/* ------------------------------------------------------------------ */
export function skeletonSlate() {
  built.slate = "";
  $("#game-list").setAttribute("aria-busy", "true");
  $("#game-list").innerHTML = Array.from({ length: 5 }, () =>
    '<li class="sk-row" aria-hidden="true"><span class="sk"></span><span class="sk"></span><span class="sk"></span></li>').join("");
}

function renderSlate(games) {
  const list = $("#game-list");
  const key = `${state.set}/${state.date}`;
  if (built.slate !== key) {
    built.slate = key;
    list.removeAttribute("aria-busy");
    list.innerHTML = games.length ? games.map(slateRow).join("")
      : '<li class="empty">No games on this day. Use the day buttons above to see another date.</li>';
  }
  for (const b of $$(".row", list)) b.setAttribute("aria-current", b.dataset.id === state.game ? "true" : "false");
}

function slateRow(g, i) {
  const col = matchupColors(g.away, g.home);
  const p = isNum(g.prob) ? g.prob : 0.5;
  const fav = p >= 0.5 ? g.home : g.away;
  const lost = g.played ? (g.ra > g.rh ? " lost-home" : " lost-away") : "";
  const score = (real, proj) => (g.played ? `${round(real)}<small>proj. ${f1(proj)}</small>` : f1(proj));
  const res = g.played
    ? `<b>Final</b> <span class="${g.hit === 1 ? "hit" : "miss"}">${g.hit === 1 ? "Winner picked" : "Winner missed"}</span>`
    : `<b>${esc(fav)} ${pct(Math.max(p, 1 - p))}</b> Total ${f1(g.total)}`;
  const label = g.played
    ? `${g.away} ${g.ra}, ${g.home} ${g.rh}, final. ${g.hit === 1 ? "Winner picked" : "Winner missed"}.`
    : `${g.away} at ${g.home}. Projected ${f1(g.pa)} to ${f1(g.ph)}. ${fav} ${pct(Math.max(p, 1 - p))} to win.`;
  return `<li style="--i:${i}"><button type="button" class="row${lost}" data-id="${esc(g.id)}" aria-label="${esc(label)}">
    <span class="t away">${dot(col.away)}<span>${esc(g.away)}</span></span>
    <span class="s away num">${score(g.ra, g.pa)}</span>
    <span class="prob" aria-hidden="true">
      <span class="probbar"><span style="flex-basis:${((1 - p) * 100).toFixed(1)}%;--c:${col.away}"></span><span style="flex-basis:${(p * 100).toFixed(1)}%;--c:${col.home}"></span></span>
      <span class="pl"><span>${pct(1 - p)}</span><span>${pct(p)}</span></span>
    </span>
    <span class="s home num">${score(g.rh, g.ph)}</span>
    <span class="t home">${dot(col.home)}<span>${esc(g.home)}</span></span>
    <span class="res">${res}</span>
  </button></li>`;
}

/* ------------------------------------------------------------------ */
/* Matchup                                                             */
/* ------------------------------------------------------------------ */
function renderMatchup(g) {
  const art = $("#matchup");
  art.hidden = !g;
  if (!g) return;
  const col = matchupColors(g.away, g.home);
  const p = isNum(g.prob) ? g.prob : 0.5;
  const today = todayISO();
  const withYear = state.set !== "live";

  $("#match-title").textContent = `${g.away} at ${g.home}`;
  let when;
  if (g.played) when = `Final, ${longDate(g.date, withYear)}.`;
  else if (g.date === today) when = `Tonight. Forecast published at ${published(g.made, { day: false })}.`;
  else if (g.date > today) when = `${longDate(g.date)}. Forecast published at ${published(g.made)}.`;
  else when = `Result pending. Forecast published at ${published(g.made)}.`;
  $("#match-when").textContent = when;

  const side = (cls, team, color, real, proj, lo, hi) => `
    <div class="side ${cls}">
      <div class="name">${dot(color)}<span>${esc(team)}</span></div>
      <div class="big${g.played ? "" : " proj"}">${g.played ? round(real) : f1(proj)}</div>
      <p class="sub">${g.played ? `Projected ${f1(proj)}, 80% range ${f1(lo)} to ${f1(hi)}` : `80% range ${f1(lo)} to ${f1(hi)}`}</p>
    </div>`;
  $("#scoreline").innerHTML = side("away", g.away, col.away, g.ra, g.pa, g.pa10, g.pa90) +
    side("home", g.home, col.home, g.rh, g.ph, g.ph10, g.ph90);

  const [a, h] = $("#probbar").children;
  a.style.flexBasis = `${((1 - p) * 100).toFixed(1)}%`;
  h.style.flexBasis = `${(p * 100).toFixed(1)}%`;
  a.style.setProperty("--c", col.away);
  h.style.setProperty("--c", col.home);
  $("#prob-labels").innerHTML =
    `<span><b>${pct(1 - p)}</b> ${esc(g.away)} win probability</span><span>${esc(g.home)} <b>${pct(p)}</b></span>`;

  const fact = (dt, dd, note = "") => `<div><dt>${dt}</dt><dd class="num">${dd}${note ? ` <small>${note}</small>` : ""}</dd></div>`;
  let facts;
  if (g.played) {
    const margin = g.rh - g.ra;
    facts = [
      fact("Projected total", f1(g.total)),
      fact("Final total", g.rh + g.ra, `off by ${f1(g.err_total)}`),
      fact("Projected margin", esc(byMargin(g.home, g.away, g.spread))),
      fact("Final margin", `${esc(margin > 0 ? g.home : g.away)} by ${Math.abs(margin)}`, `off by ${f1(g.err_spread)}`),
    ];
  } else {
    facts = [
      fact("Projected total", f1(g.total)),
      fact("Projected margin", esc(byMargin(g.home, g.away, g.spread))),
      fact("Favorite", `${esc(p >= 0.5 ? g.home : g.away)} ${pct(Math.max(p, 1 - p))}`),
      fact("Published", clock(g.made), g.date === today ? "today" : ""),
    ];
  }
  $("#facts").innerHTML = facts.join("");
  $("#summary").innerHTML = g.played
    ? `<b class="${g.hit === 1 ? "hit" : "miss"}">${g.hit === 1 ? "The model picked the winner." : "The model picked the wrong winner."}</b>`
    : "";
}

/* ------------------------------------------------------------------ */
/* Player forecasts                                                    */
/* ------------------------------------------------------------------ */
function head() {
  return `<tr><th scope="col">Player</th>${BOX.map((c) => `<th scope="col"><abbr title="${STAT_NAME[c]}">${c}</abbr></th>`).join("")}</tr>`;
}

function skeletonBox() {
  built.box = "";
  const table = $("#box");
  table.tHead.innerHTML = head();
  table.tBodies[0].innerHTML = Array.from({ length: 8 }, () =>
    `<tr aria-hidden="true"><td><span class="sk sk-name"></span></td>${BOX.map(() => '<td><span class="sk sk-num"></span></td>').join("")}</tr>`).join("");
  $("#team-note").textContent = "Loading player forecasts…";
}

function renderBox(g, day) {
  const seg = $("#team-seg");
  const table = $("#box");
  if (!g) {
    seg.innerHTML = "";
    $("#team-note").textContent = "";
    table.tHead.innerHTML = table.tBodies[0].innerHTML = "";
    built.seg = built.box = "";
    return;
  }
  const col = matchupColors(g.away, g.home);

  // team buttons: rebuilt only when the game changes
  if (built.seg !== g.id) {
    built.seg = g.id;
    seg.innerHTML = ["away", "home"].map((side) => {
      const t = side === "home" ? g.home : g.away;
      return `<button type="button" data-team="${side}">${dot(col[side])}${esc(t)}</button>`;
    }).join("");
  }
  for (const b of $$("button", seg)) b.setAttribute("aria-pressed", String(b.dataset.team === state.team));

  const mode = g.played ? (state.mode || "both") : "proj";
  for (const b of $$("#mode-seg button")) {
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
    b.disabled = !g.played && b.dataset.mode !== "proj";
    b.title = b.disabled ? "Available once the game is played" : "";
  }

  const team = state.team === "home" ? g.home : g.away;
  const key = `${state.set}/${state.date}/${g.id}/${state.team}/${mode}`;
  if (built.box === key) { syncDetail(day, g, team); return; }
  built.box = key;

  const players = day.players.filter((p) => p.g === g.id && p.t === team);
  players.sort((x, y) => (x.st === "dnp") - (y.st === "dnp") || (y.s.MIN?.[0] ?? 0) - (x.s.MIN?.[0] ?? 0));
  const pts = players.reduce((s, p) => s + (p.s.PTS?.[0] ?? 0), 0);
  const adj = players[0]?.adj;
  $("#team-note").textContent = players.length
    ? `${players.length} players, ${Math.round(pts)} projected points between them` +
      (isNum(adj) ? `, scaled ×${adj.toFixed(3)} toward the team-score forecast.` : ".")
    : "";

  table.tHead.innerHTML = head();
  table.tBodies[0].innerHTML = players.length ? players.map((p) => `
    <tr class="p${p.st === "dnp" ? " dnp" : ""}" data-id="${esc(p.id)}">
      <td><button type="button" class="pname" aria-expanded="false" aria-controls="d-${esc(p.id)}">${esc(p.n)}</button>${p.st === "dnp" ? "<small>did not play</small>" : ""}</td>
      ${BOX.map((c) => cell(p, c, mode)).join("")}
    </tr>`).join("")
    : `<tr><td colspan="${BOX.length + 1}" class="empty">There are no player forecasts for ${esc(team)} in this game. Players without NBA games have no history to forecast from.</td></tr>`;
  syncDetail(day, g, team);
}

/** Open or close the expanded player without rebuilding the table. */
export function toggleDetail(id) {
  state.open = state.open === id ? null : id;
  syncDetail(lastDay, lastGame, lastTeam);
}

let lastDay, lastGame, lastTeam;
function syncDetail(day, g, team) {
  [lastDay, lastGame, lastTeam] = [day, g, team];
  for (const tr of $$("#box tr.detail")) {
    if (tr.dataset.for !== state.open) {
      tr.previousElementSibling?.querySelector(".pname")?.setAttribute("aria-expanded", "false");
      tr.remove();
    }
  }
  if (!state.open || $(`#box tr.detail[data-for="${CSS.escape(state.open)}"]`)) return;
  const row = $(`#box tr.p[data-id="${CSS.escape(state.open)}"]`);
  const p = day?.players.find((x) => x.id === state.open && x.g === g?.id);
  if (!row || !p) { state.open = null; return; }
  row.querySelector(".pname").setAttribute("aria-expanded", "true");
  row.insertAdjacentHTML("afterend",
    `<tr class="detail" id="d-${esc(p.id)}" data-for="${esc(p.id)}"><td colspan="${BOX.length + 1}">${detail(p, team)}</td></tr>`);
}

function cell(p, c, mode) {
  if (!p.s[c]) return `<td>${NONE}</td>`;
  const { fc, lo, hi, real, inside } = unpack(p.s[c]);
  const tip = `${STAT_NAME[c]}: forecast ${f1(fc)}, 80% range ${fmt(lo)} to ${fmt(hi)}` +
    (p.st === "played" && isNum(real) ? `, actual ${fmt(real)}${inside === 0 ? ", outside the range" : ""}` : "");
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
  return `<div class="detail-inner">
    <div class="detail-head">
      <p><strong>${esc(p.n)}</strong> <span class="who">${esc(who)}</span></p>
      <p class="strip-legend">
        <span><i class="lg-range"></i>80% range</span><span><i class="lg-fc"></i>forecast</span>
        <span><i class="lg-act"></i>actual</span><span><i class="lg-act out"></i>actual outside the range</span>
        <span><i class="lg-avg"></i>last-10 average</span>
      </p>
    </div>
    <div class="strips">${DETAIL_ORDER.filter((c) => p.s[c]).map((c) => strip(c, unpack(p.s[c]), p.st)).join("")}</div>
  </div>`;
}

function strip(c, v, status) {
  const { fc, lo, hi, base, real, err, inside } = v;
  const has = status === "played" && isNum(real);
  const vals = [0, lo, hi, fc, base, has ? real : null].filter(isNum);
  const min = Math.min(...vals);
  let max = Math.max(...vals) * 1.08;
  if (max <= min) max = min + 1;
  const X = (x) => +(((x - min) / (max - min)) * 100).toFixed(2);
  const out = has && inside === 0;
  const avg = isNum(base) ? `, last 10: ${fmt(base)}` : "";
  let sub;
  if (has) sub = `forecast ${f1(fc)}${avg}, <em>off by ${fmt(err)}</em>`;
  else if (status === "dnp") sub = `forecast ${f1(fc)}${avg}, did not play`;
  else sub = `forecast${avg}`;
  // range labels sit under the ends of the band, or once in the middle when the band is narrow
  const lab = (x, text) => `<span class="${x < 7 ? "start" : x > 93 ? "end" : "mid"}" style="left:${x}%">${text}</span>`;
  const [xl, xh] = [X(lo), X(hi)];
  const foot = xh - xl < 26 ? lab((xl + xh) / 2, `${fmt(lo)} to ${fmt(hi)}`) : lab(xl, fmt(lo)) + lab(xh, fmt(hi));
  return `<div class="strip${out ? " out" : ""}">
    <div class="strip-top"><span class="strip-name">${STAT_NAME[c]}</span>
      <span class="strip-val">${has ? fmt(real) : status === "dnp" ? NONE : f1(fc)}</span></div>
    <div class="strip-sub">${sub}</div>
    <div class="track" aria-hidden="true">
      <span class="rng" style="left:${xl}%;width:${(xh - xl).toFixed(2)}%"></span>
      ${isNum(base) ? `<span class="avg" style="left:${X(base)}%"></span>` : ""}
      <span class="fc" style="left:${X(fc)}%"></span>
      ${has ? `<span class="act" style="left:${X(real)}%"></span>` : ""}
    </div>
    <div class="strip-foot" aria-label="80% range ${fmt(lo)} to ${fmt(hi)}">${foot}</div>
  </div>`;
}
