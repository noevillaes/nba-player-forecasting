// The Players view: search any player, then see his season for one stat — the 80% range,
// the forecast and what happened, game by game.

import { state, loadPlayers, loadPlayer, isReadyPlayer } from "./store.js";
import { STAT_NAME, DETAIL_ORDER } from "./stats.js";
import { $, $$, esc, isNum, NONE, fmt, f1, round, pct, shortDate } from "./format.js";

let navigate = () => {};
/** main.js hands over its navigation, so picks go through the same URL state and transitions. */
export function setNavigator(fn) { navigate = fn; }

const norm = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/* ------------------------------------------------------------------ */
/* Entry point                                                         */
/* ------------------------------------------------------------------ */
let index = [];
export async function renderPlayers(isCurrent) {
  bindSearch();
  index = await loadPlayers(state.set).catch(() => []);
  if (!isCurrent()) return;
  if (!state.player) { renderEmpty(); return; }
  if (!isReadyPlayer(state.set, state.player)) skeleton();
  let p;
  try {
    p = await loadPlayer(state.set, state.player);
  } catch {
    if (!isCurrent()) return;
    renderEmpty(`There are no forecasts for that player in this set.`);
    return;
  }
  if (!isCurrent()) return;
  renderPlayer(p);
}

/* ------------------------------------------------------------------ */
/* No player picked: the search box and the top projected scorers      */
/* ------------------------------------------------------------------ */
function renderEmpty(msg) {
  $("#player-back").hidden = true;
  $("#player-title").textContent = "Players";
  $("#player-lede").hidden = false;
  $("#player-lede").textContent = msg ||
    "Every player with a forecast this season: what the model expected, game by game, against what happened.";
  $("#player-facts").innerHTML = "";
  $("#player-empty").hidden = false;
  $("#player-main").hidden = true;
  $("#log-block").hidden = true;
  document.title = "Players | NBA Forecasts";
  const top = [...index].filter((p) => p.k >= 3).sort((a, b) => b.fp - a.fp).slice(0, 12);
  $("#top-players").innerHTML = top.map((p, i) => `
    <li style="--i:${i}"><a href="#view=players&player=${esc(p.id)}" data-player="${esc(p.id)}">
      <span class="tp-rank">${String(i + 1).padStart(2, "0")}</span>
      <span class="tp-name">${esc(p.n)}<small>${esc(p.t)}</small></span>
      <span class="tp-val num">${f1(p.fp)}<small>pts / game</small></span>
    </a></li>`).join("") || '<li class="empty">No player forecasts in this set yet.</li>';
}

function skeleton() {
  $("#player-empty").hidden = true;
  $("#player-main").hidden = false;
  $("#player-chart").innerHTML = '<span class="sk" style="height:260px"></span>';
}

/* ------------------------------------------------------------------ */
/* One player                                                          */
/* ------------------------------------------------------------------ */
let current = null;   // the player shown, kept for redrawing on resize
function renderPlayer(p) {
  current = p;
  const c = STAT_NAME[state.stat] ? state.stat : "PTS";
  const games = p.g;
  const played = games.filter((x) => x.st === "played");

  $("#player-back").hidden = false;
  $("#player-title").textContent = p.n;
  $("#player-lede").hidden = true;
  document.title = `${p.n} | NBA Forecasts`;

  // band: team, games, how often the actual landed in the range (all stats)
  let inN = 0, allN = 0;
  for (const x of played) for (const v of Object.values(x.s)) if (v[5] === 0 || v[5] === 1) { allN++; inN += v[5]; }
  const fact = (dt, dd, note = "") => `<div><dt>${dt}</dt><dd>${dd}${note ? ` <small>${note}</small>` : ""}</dd></div>`;
  $("#player-facts").innerHTML = [
    fact("Team", esc(p.t)),
    fact("Games forecast", games.length, `${played.length} played`),
    allN ? fact("In the 80% range", pct(inN / allN), "all 16 stats") : "",
  ].join("");

  $("#player-empty").hidden = true;
  $("#player-main").hidden = false;
  $("#log-block").hidden = false;

  // stat chips
  const chips = $("#stat-chips");
  const have = DETAIL_ORDER.filter((s) => games.some((x) => x.s[s]));
  if (chips.dataset.for !== p.id) {
    chips.dataset.for = p.id;
    chips.innerHTML = have.map((s) => `<button type="button" data-stat="${s}">${STAT_NAME[s]}</button>`).join("");
  }
  for (const b of $$("button", chips)) b.setAttribute("aria-pressed", String(b.dataset.stat === c));

  drawChart(games, c);
  renderSummary(played, c);
  renderLog(games, c);
}

function rowsFor(games, c) {
  return games.filter((x) => x.s[c]).map((x) => {
    const [fc, lo, hi, base, real, inside] = x.s[c];
    return { ...x, fc, lo, hi, base, real: x.st === "played" ? real : null, inside: x.st === "played" ? inside : null };
  });
}

function renderSummary(played, c) {
  const rows = rowsFor(played, c).filter((r) => isNum(r.real));
  const el = $("#player-sum");
  if (!rows.length) { el.innerHTML = `<div><dt>${STAT_NAME[c]}</dt><dd>No games scored yet</dd></div>`; return; }
  const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const mae = mean(rows.map((r) => Math.abs(r.fc - r.real)));
  const withBase = rows.filter((r) => isNum(r.base));
  const bmae = withBase.length ? mean(withBase.map((r) => Math.abs(r.base - r.real))) : null;
  const inside = rows.filter((r) => r.inside === 1).length;
  const less = bmae ? 1 - mae / bmae : null;
  const fact = (dt, dd, note = "") => `<div><dt>${dt}</dt><dd class="num">${dd}${note ? ` <small>${note}</small>` : ""}</dd></div>`;
  el.innerHTML = [
    fact("Average actual", f1(mean(rows.map((r) => r.real))), `forecast ${f1(mean(rows.map((r) => r.fc)))}`),
    fact("Model error", mae.toFixed(2), `per game`),
    bmae != null ? fact("10-game average error", bmae.toFixed(2),
      `<span class="${less >= 0 ? "good" : "bad"}">${pct(Math.abs(less))} ${less >= 0 ? "less" : "more"} for the model</span>`) : "",
    fact("In the 80% range", `${inside} of ${rows.length}`, pct(inside / rows.length)),
  ].join("");
}

function renderLog(games, c) {
  const rows = rowsFor(games, c).reverse();
  const t = $("#player-log");
  t.tHead.innerHTML = `<tr><th scope="col">Date</th><th scope="col">Opponent</th><th scope="col">Minutes</th>
    <th scope="col">Forecast</th><th scope="col">80% range</th><th scope="col">Actual</th><th scope="col">Actual − forecast</th></tr>`;
  t.tBodies[0].innerHTML = rows.map((r) => {
    const g = games.find((x) => x.g === r.g && x.d === r.d);
    const min = g?.s.MIN;
    const mins = r.st === "played" ? round(min?.[4]) : r.st === "dnp" ? "DNP" : NONE;
    const out = r.inside === 0;
    const diff = isNum(r.real) ? r.real - r.fc : null;
    return `<tr${r.st === "dnp" ? ' class="dnp"' : ""}>
      <td>${shortDate(r.d)}</td>
      <td>${r.h ? "vs" : "@"} ${esc(r.o || NONE)}</td>
      <td>${mins}</td>
      <td class="num">${f1(r.fc)}</td>
      <td>${fmt(r.lo)} to ${fmt(r.hi)}</td>
      <td class="num${out ? " out" : ""}">${isNum(r.real) ? fmt(r.real) : r.st === "dnp" ? "DNP" : NONE}</td>
      <td class="num${out ? " out" : ""}">${isNum(diff) ? `${diff > 0 ? "+" : diff < 0 ? "−" : ""}${fmt(Math.abs(diff))}` : ""}</td>
    </tr>`;
  }).join("");
}

/* ------------------------------------------------------------------ */
/* Season chart: 80% band, forecast line, actual dots                  */
/* ------------------------------------------------------------------ */
let chart = null;
export function redrawPlayer() { if (current && state.view === "players") drawChart(current.g, STAT_NAME[state.stat] ? state.stat : "PTS"); }

function drawChart(games, c) {
  const el = $("#player-chart");
  const rows = rowsFor(games, c);
  if (!rows.length) { el.innerHTML = '<p class="empty">No forecasts for this stat.</p>'; chart = null; return; }
  const W = Math.max(320, el.clientWidth || 800), H = W < 560 ? 240 : 300;
  const pad = { l: 36, r: 16, t: 18, b: 30 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const top = Math.max(1, ...rows.flatMap((r) => [r.hi, r.real, r.fc, r.base].filter(isNum))) * 1.08;
  const step = niceStep(top / 4), yMax = Math.ceil(top / step) * step;
  const n = rows.length;
  const X = (i) => pad.l + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
  const Y = (v) => pad.t + ih - (v / yMax) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(STAT_NAME[c])} per game: forecast, 80% range and actual">`;
  for (let v = 0; v <= yMax + 1e-9; v += step) {
    s += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}"/>`;
    s += `<text x="${pad.l - 8}" y="${Y(v) + 4}" text-anchor="end">${+v.toFixed(2)}</text>`;
  }
  const every = Math.ceil(n / Math.max(2, Math.floor(iw / 64)));
  rows.forEach((r, i) => { if (i % every === 0 || i === n - 1) s += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle">${shortDate(r.d)}</text>`; });
  // the band: q90 left to right, then q10 back
  const band = rows.map((r, i) => `${X(i).toFixed(1)},${Y(r.hi).toFixed(1)}`).join(" ") + " " +
    rows.map((r, i) => `${X(i).toFixed(1)},${Y(r.lo).toFixed(1)}`).reverse().join(" ");
  s += `<polygon class="band" points="${band}"/>`;
  const line = (k) => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r[k]).toFixed(1)}`).join("");
  if (rows.every((r) => isNum(r.base))) s += `<path class="base-line" d="${line("base")}"/>`;
  s += `<path class="fc-line" d="${line("fc")}" pathLength="1"/>`;
  s += `<line class="guide" x1="0" x2="0" y1="${pad.t}" y2="${pad.t + ih}" visibility="hidden"/>`;
  rows.forEach((r, i) => {
    s += `<circle class="fc-dot" data-i="${i}" cx="${X(i)}" cy="${Y(r.fc)}" r="2.5"/>`;
    if (isNum(r.real)) s += `<circle class="act-dot${r.inside === 0 ? " out" : ""}" data-i="${i}" cx="${X(i)}" cy="${Y(r.real)}" r="5" style="--i:${i}"/>`;
    else if (r.st === "dnp") s += `<text class="dnp-mark" x="${X(i)}" y="${pad.t + ih - 6}" text-anchor="middle">DNP</text>`;
  });
  el.innerHTML = `${s}</svg>
    <p class="chart-legend"><span><i class="lg-band"></i>80% range</span><span><i class="lg-fcl"></i>forecast</span>
      <span><i class="lg-act"></i>actual</span><span><i class="lg-act out"></i>outside the range</span>
      <span><i class="lg-basel"></i>last-10 average</span></p>
    <div class="chart-tip" role="status" aria-live="polite" hidden></div>`;
  chart = { rows, X, Y, W, pad, i: null, c };
  bindTip(el);
}

function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}

function showTip(el, i) {
  const tip = $(".chart-tip", el), svg = $("svg", el), guide = $(".guide", el);
  if (!chart || !tip || !svg) return;
  if (i == null) {
    tip.hidden = true; guide?.setAttribute("visibility", "hidden");
    $$(".on", svg).forEach((x) => x.classList.remove("on")); chart.i = null; return;
  }
  const { rows, X, Y, W } = chart, r = rows[i];
  chart.i = i;
  guide.setAttribute("x1", X(i)); guide.setAttribute("x2", X(i)); guide.setAttribute("visibility", "visible");
  $$("circle", svg).forEach((x) => x.classList.toggle("on", +x.dataset.i === i));
  const actual = isNum(r.real) ? fmt(r.real) : r.st === "dnp" ? "DNP" : "not played";
  tip.innerHTML = `<p class="tt-d">${shortDate(r.d)} · ${r.h ? "vs" : "@"} ${esc(r.o || "")}</p>
    <p class="tt-row"><i class="tt-act${r.inside === 0 ? " out" : ""}"></i>Actual <b>${actual}</b></p>
    <p class="tt-row"><i class="tt-fc"></i>Forecast <b>${f1(r.fc)}</b></p>
    <p class="tt-f">80% range ${fmt(r.lo)} to ${fmt(r.hi)}${isNum(r.base) ? ` · last 10 ${f1(r.base)}` : ""}</p>`;
  tip.hidden = false;
  const scale = svg.getBoundingClientRect().width / W;
  const px = X(i) * scale, py = Y(isNum(r.real) ? Math.max(r.real, r.hi) : r.hi) * scale;
  const tw = tip.offsetWidth, th = tip.offsetHeight, box = el.clientWidth;
  const left = px + 14 + tw > box - 8 ? px - 14 - tw : px + 14;
  tip.style.transform = `translate(${Math.max(4, left).toFixed(0)}px, ${Math.max(4, py - th / 2).toFixed(0)}px)`;
}

function bindTip(el) {
  if (el.dataset.tip) return;
  el.dataset.tip = "1";
  el.tabIndex = 0;
  el.setAttribute("aria-label", "Season chart. Use the left and right arrow keys to read each game.");
  const nearest = (e) => {
    const svg = $("svg", el);
    if (!svg || !chart) return null;
    const b = svg.getBoundingClientRect();
    const x = (e.clientX - b.left) * (chart.W / b.width);
    let best = 0;
    chart.rows.forEach((_, i) => { if (Math.abs(chart.X(i) - x) < Math.abs(chart.X(best) - x)) best = i; });
    return best;
  };
  el.addEventListener("pointermove", (e) => { const i = nearest(e); if (i !== chart?.i) showTip(el, i); });
  el.addEventListener("pointerdown", (e) => showTip(el, nearest(e)));
  el.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") showTip(el, null); });
  el.addEventListener("keydown", (e) => {
    if (!chart || !["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(e.key)) return;
    e.preventDefault(); e.stopPropagation();
    const n = chart.rows.length - 1, cur = chart.i ?? n;
    const i = e.key === "Escape" ? null : e.key === "Home" ? 0 : e.key === "End" ? n
      : Math.max(0, Math.min(n, cur + (e.key === "ArrowLeft" ? -1 : 1) * (chart.i == null ? 0 : 1)));
    showTip(el, i);
  });
  el.addEventListener("blur", () => showTip(el, null));
}

/* ------------------------------------------------------------------ */
/* Search box (combobox with a listbox of matches)                     */
/* ------------------------------------------------------------------ */
let active = -1, matches = [];
function search(q) {
  const t = norm(q).trim().split(/\s+/).filter(Boolean);
  if (!t.length) return [];
  const scored = [];
  for (const p of index) {
    const n = norm(p.n), words = n.split(/[\s.'-]+/);
    if (!t.every((w) => n.includes(w))) continue;
    const starts = t.every((w) => words.some((x) => x.startsWith(w)));
    scored.push([starts ? 0 : 1, -p.k, p]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].n.localeCompare(b[2].n));
  return scored.slice(0, 8).map((x) => x[2]);
}
function drawList() {
  const list = $("#player-list"), input = $("#player-q");
  const open = matches.length > 0 || input.value.trim().length > 1;
  list.hidden = !open;
  input.setAttribute("aria-expanded", String(open));
  if (!open) { input.removeAttribute("aria-activedescendant"); return; }
  list.innerHTML = matches.length ? matches.map((p, i) => `
    <li id="pq-${esc(p.id)}" role="option" data-player="${esc(p.id)}" aria-selected="${i === active}">
      <span>${esc(p.n)}</span><small>${esc(p.t)} · ${p.k} games</small></li>`).join("")
    : '<li class="none" role="option" aria-disabled="true">No player with that name has a forecast yet.</li>';
  if (active >= 0 && matches[active]) input.setAttribute("aria-activedescendant", `pq-${matches[active].id}`);
  else input.removeAttribute("aria-activedescendant");
}
function pick(id) {
  const input = $("#player-q");
  input.value = ""; matches = []; active = -1; drawList(); input.blur();
  navigate({ player: id });
}
function bindSearch() {
  const input = $("#player-q"), list = $("#player-list");
  if (input.dataset.bound) return;
  input.dataset.bound = "1";
  input.addEventListener("input", () => { matches = search(input.value); active = matches.length ? 0 : -1; drawList(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!matches.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length;
      drawList();
      $(`#pq-${matches[active].id}`)?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      if (matches[active]) { e.preventDefault(); pick(matches[active].id); }
    } else if (e.key === "Escape") {
      input.value = ""; matches = []; active = -1; drawList();
    }
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; input.setAttribute("aria-expanded", "false"); }, 120));
  input.addEventListener("focus", () => { if (matches.length) drawList(); });
  // pointerdown so the pick lands before the input loses focus
  list.addEventListener("pointerdown", (e) => {
    const li = e.target.closest("li[data-player]");
    if (li) { e.preventDefault(); pick(li.dataset.player); }
  });
  $("#stat-chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-stat]");
    if (b && b.dataset.stat !== state.stat) navigate({ stat: b.dataset.stat }, { replace: true });
  });
}

