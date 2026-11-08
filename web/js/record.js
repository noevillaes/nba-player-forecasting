// The Track record view: season figures, error by stat and the day-by-day chart.

import { state } from "./store.js";
import { STAT_NAME, RECORD_ORDER } from "./stats.js";
import { $, $$, esc, isNum, NONE, pct, count, shortDate, fmt, f1, lineText } from "./format.js";

let builtFor = null;   // the meta object the table was built from
let lastRows = [];     // daily rows of the selected stat, kept for redrawing on resize

/** Error by stat over every scored day, weighted by players scored each day. */
function aggregate(score) {
  const agg = {};
  for (const r of score) {
    const a = (agg[r.s] ??= { n: 0, mae: 0, base: 0, cov: 0 });
    a.n += r.n;
    a.mae += r.n * (r.mae ?? 0);
    a.base += r.n * (r.base ?? 0);
    a.cov += r.n * (r.cov ?? 0);
  }
  return RECORD_ORDER.filter((s) => agg[s]?.n).map((s) => {
    const a = agg[s];
    const mae = a.mae / a.n, base = a.base / a.n;
    return { s, n: a.n, mae, base, cov: a.cov / a.n, imp: base ? (1 - mae / base) * 100 : 0 };
  });
}

export function renderRecord(m) {
  if (builtFor !== m) {
    builtFor = m;
    renderFigures(m);
    renderVsLine(m);
    renderWeek(m);
    renderCalibration(m);
    renderTable(m);
  }
  const rows = $$("#perf-table tbody tr[data-stat]");
  if (rows.length && !rows.some((r) => r.dataset.stat === state.stat)) state.stat = rows[0].dataset.stat;
  for (const tr of rows) {
    const on = tr.dataset.stat === state.stat;
    tr.classList.toggle("sel", on);
    tr.querySelector(".statbtn").setAttribute("aria-pressed", String(on));
  }
  $("#daily-title").textContent = `Day by day: ${STAT_NAME[state.stat] || state.stat}`;
  lastRows = m.score.filter((r) => r.s === state.stat).sort((a, b) => (a.d < b.d ? -1 : 1));
  drawDaily();
}

/** The model against a betting benchmark: a side-by-side table plus the betting records. */
const BENCH = {
  mkt: ["Market", "the median line across every recorded sportsbook, before tip-off"],
  pin: ["Pinnacle", "Pinnacle, the book professional bettors use as the reference price, before tip-off"],
  close: ["DraftKings at tip-off", "DraftKings' closing line, which already includes late injury news"],
};
let bench = null;
function renderVsLine(m) {
  const el = $("#vs-block");
  const all = m.vs || {};
  const have = Object.keys(BENCH).filter((k) => all[k]);
  if (!have.length) {
    el.innerHTML = '<p class="empty">No game with a recorded betting line has been scored yet. Lines are saved every morning, and this comparison fills in as those games finish.</p>';
    return;
  }
  if (!have.includes(bench)) bench = have[0];
  const v = all[bench];
  const [name, about] = BENCH[bench];
  const solo = v.solo;
  // forecast, model alone (once the forecast blends in the market), benchmark; bold the best
  const row = (h, note, key, lineKey, show, lowWins) => {
    const vals = [v[key], ...(solo ? [solo[key]] : []), v[lineKey]];
    const ok = vals.filter(isNum);
    const top = lowWins ? Math.min(...ok) : Math.max(...ok);
    const one = ok.filter((x) => x === top).length === 1;
    return `<tr><th scope="row">${h}<small>${note}</small></th>${vals.map((x) =>
      `<td${one && x === top ? ' class="near"' : ""}>${show(x)}</td>`).join("")}</tr>`;
  };
  const p = (x) => (isNum(x) ? pct(x) : NONE);
  const d1 = (x) => (isNum(x) ? x.toFixed(1) : NONE);
  const d3 = (x) => (isNum(x) ? x.toFixed(3) : NONE);
  const rec = ([w, l]) => (w + l ? `${w}–${l}` : NONE);
  const share = ([w, l]) => (w + l ? pct(w / (w + l)) : "");
  const span = v.from === v.to ? shortDate(v.from) : `${shortDate(v.from)} to ${shortDate(v.to)}`;
  el.innerHTML = `
    ${have.length > 1 ? `<div class="seg bench-seg" role="group" aria-label="Compare against">${have.map((k) =>
      `<button type="button" data-bench="${k}" aria-pressed="${k === bench}">${BENCH[k][0]}</button>`).join("")}</div>` : ""}
    <div class="table-wrap"><table class="vs-table vs-season">
      <caption>Against ${about}. ${count(v.n)} ${v.n === 1 ? "game" : "games"}, ${span}. Bold marks the best.</caption>
      <thead><tr><th scope="col"><span class="sr-only">Measure</span></th><th scope="col">${solo ? "Forecast" : "Model"}</th>${solo ? '<th scope="col">Model alone</th>' : ""}<th scope="col">${name}</th></tr></thead>
      <tbody>
        ${row("Winners picked", "share of games", "hit", "line_hit", p, false)}
        ${row("Points off on the margin", "average miss", "err_margin", "line_err_margin", d1, true)}
        ${row("Points off on the total", "average miss", "err_total", "line_err_total", d1, true)}
        ${row("Brier score", "win probability; lower is better", "brier", "line_brier", d3, true)}
      </tbody></table></div>
    ${blendNote(m.blend)}
    <div class="figures vs-figures">
      <div class="figure"><p class="v">${rec(v.ats)}</p><p class="l">Against the spread</p>
        <p class="s">Taking the model's side of every line${share(v.ats) ? `: ${share(v.ats)} right` : ""}. At standard odds, 52.4% breaks even.</p></div>
      <div class="figure"><p class="v">${rec(v.ou)}</p><p class="l">Over or under</p>
        <p class="s">Taking the model's side of every posted total${share(v.ou) ? `: ${share(v.ou)} right` : ""}.</p></div>
      <div class="figure"><p class="v">${v.disagree ? `${v.disagree_won} of ${v.disagree}` : NONE}</p><p class="l">When they picked different winners</p>
        <p class="s">${v.disagree ? "Games the model's pick won when it went against the betting favorite." : "The model and the line haven't disagreed on a winner yet."}</p></div>
    </div>`;
}
/** How the published forecast mixes the model with the market, in one sentence. */
function blendNote(b) {
  if (!b) return "";
  const w = (x) => pct(x);
  return `<p class="note blend-note">${b.from ? `Since ${shortDate(b.from)} the published forecast blends the model with the betting market. ` : ""}` +
    `The current weights, fitted on ${count(b.n)} games against ${b.lines} lines, give the model ${w(b.w.spread)} of the margin, ` +
    `${w(b.w.total)} of the total and ${w(b.w.prob)} of the win probability; the rest is the market. ` +
    `Player points follow their team's blended score. "Model alone" is what the model would have said by itself.</p>`;
}

$("#vs-block")?.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-bench]");
  if (!b || b.dataset.bench === bench) return;
  bench = b.dataset.bench;
  if (builtFor) renderVsLine(builtFor);
  $(`#vs-block button[data-bench="${bench}"]`)?.focus();
});

/** The week's closest forecasts among correct picks, and its most confident misses. */
function renderWeek(m) {
  const el = $("#week-calls");
  const played = m.games.filter((g) => g.played && isNum(g.rh));
  // the seven calendar days ending on the last scored day
  const last = played.reduce((a, g) => (g.date > a ? g.date : a), "");
  const from = new Date(`${last}T12:00:00Z`);
  from.setUTCDate(from.getUTCDate() - 6);
  const start = from.toISOString().slice(0, 10);
  const week = played.filter((g) => g.date >= start);
  if (!week.length) { el.innerHTML = '<p class="empty">No games scored yet.</p>'; return; }
  const conf = (g) => Math.max(g.prob, 1 - g.prob);
  const best = week.filter((g) => g.hit === 1 && isNum(g.err_total) && isNum(g.err_spread))
    .sort((a, b) => a.err_total + a.err_spread - (b.err_total + b.err_spread)).slice(0, 3);
  const worst = week.filter((g) => g.hit === 0).sort((a, b) => conf(b) - conf(a)).slice(0, 3);
  const score = (g) => `${esc(g.away)} ${g.ra}, ${esc(g.home)} ${g.rh}`;
  const pick = (g) => (g.prob >= 0.5 ? g.home : g.away);
  const item = (g, why) => `<li><p class="wc-d">${shortDate(g.date)}</p><p class="wc-s">${score(g)}</p><p class="wc-w">${why}</p></li>`;
  const list = (title, cls, rows, why, empty) => `<div class="wc ${cls}"><h3 class="title-sm">${title}</h3>
    ${rows.length ? `<ol>${rows.map((g) => item(g, why(g))).join("")}</ol>` : `<p class="note">${empty}</p>`}</div>`;
  el.innerHTML =
    list("Closest calls", "good", best, (g) =>
      `Projected ${fmt(g.pa)} to ${fmt(g.ph)}: off by ${f1(g.err_spread)} on the margin and ${f1(g.err_total)} on the total.`,
      "No correct picks this week.") +
    list("Most confident misses", "bad", worst, (g) =>
      `The model gave the ${esc(pick(g))} ${pct(conf(g))}${(g.mkt || g.line) && isNum((g.mkt || g.line).sp) ? `; the ${g.mkt ? "market" : "line"} had ${esc(lineText(g.home, g.away, (g.mkt || g.line).sp))}` : ""}.`,
      "The model picked every winner this week.");
}

function renderFigures(m) {
  const played = m.games.filter((g) => g.played);
  const n = played.length;
  if (!n) {
    $("#figures").innerHTML = '<p class="empty">No games have been scored yet. The first numbers appear the morning after the first game day.</p>';
    return;
  }
  const mean = (k) => {
    const v = played.map((g) => g[k]).filter(isNum);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };
  const acc = mean("hit"), brier = mean("brier"), et = mean("err_total"), es = mean("err_spread");
  const cov = played.reduce((s, g) => s + (g.in_h ?? 0) + (g.in_a ?? 0), 0) / (2 * n);
  const show = (x, digits) => (isNum(x) ? x.toFixed(digits) : NONE);
  const fig = (v, l, s) => `<div class="figure"><p class="v">${v}</p><p class="l">${l}</p><p class="s">${s}</p></div>`;
  $("#figures").innerHTML = [
    fig(isNum(acc) ? pct(acc) : NONE, "Winners picked", `${Math.round(acc * n)} of ${n} scored games.`),
    fig(show(brier, 3), "Brier score", "Win probability accuracy. A coin flip scores 0.250; lower is better."),
    fig(pct(cov), "Team scores in the 80% range", "A well-calibrated range lands near 80%."),
    fig(show(et, 1), "Points off on the total", "Average miss on the combined score."),
    fig(show(es, 1), "Points off on the margin", "Average miss on the final margin."),
    fig(n, "Games scored", "Every played game with a published forecast."),
  ].join("");
}

function renderTable(m) {
  const rows = aggregate(m.score);
  const top = Math.max(1, ...rows.map((r) => Math.abs(r.imp)));
  $("#perf-table tbody").innerHTML = rows.map((r) => {
    const txt = r.imp >= 0 ? `${r.imp.toFixed(1)}% less` : `${Math.abs(r.imp).toFixed(1)}% more`;
    return `<tr data-stat="${r.s}">
      <td><button type="button" class="statbtn" aria-pressed="false">${STAT_NAME[r.s]}</button><small>${count(r.n)} player-games</small></td>
      <td class="num">${r.mae.toFixed(2)}</td><td class="num">${r.base.toFixed(2)}</td>
      <td><span class="ibar${r.imp < 0 ? " neg" : ""}"><span class="b" style="--w:${(Math.abs(r.imp) / top).toFixed(3)}"></span><span>${txt}</span></span></td>
      <td class="num">${pct(r.cov)}</td></tr>`;
  }).join("") || '<tr><td colspan="5" class="empty">No scored days yet.</td></tr>';
}

export function drawDaily() {
  const el = $("#daily-chart");
  const rows = lastRows;
  if (!rows.length) { el.innerHTML = '<p class="empty">No scored days yet.</p>'; return; }
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
    s += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}"/>`;
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
    s += `<line class="version" x1="${x}" x2="${x}" y1="${pad.t}" y2="${pad.t + ih}"/><text class="version" x="${x + 5}" y="${pad.t + 10}">${esc(r.m)}</text>`;
  });
  const path = (k) => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r[k]).toFixed(1)}`).join("");
  s += `<path class="avg-line" d="${path("base")}"/><path class="model-line" d="${path("mae")}" pathLength="1"/>`;
  // hover guide (moved by the tooltip code below)
  s += `<line class="guide" x1="0" x2="0" y1="${pad.t}" y2="${pad.t + ih}" visibility="hidden"/>`;
  rows.forEach((r, i) => {
    s += `<circle class="avg-dot" data-i="${i}" cx="${X(i)}" cy="${Y(r.base)}" r="3.5"/><circle class="model-dot" data-i="${i}" cx="${X(i)}" cy="${Y(r.mae)}" r="4"/>`;
  });
  const last = rows[rows.length - 1];
  let ym = Y(last.mae) + 4, yb = Y(last.base) + 4;
  if (Math.abs(ym - yb) < 15) { if (ym >= yb) ym = yb + 15; else yb = ym + 15; }
  const lx = X(rows.length - 1) + 12;
  s += `<text class="lbl model" x="${lx}" y="${ym}">Model ${last.mae.toFixed(2)}</text>`;
  s += `<text class="lbl avg" x="${lx}" y="${yb}">10-game avg ${last.base.toFixed(2)}</text>`;
  el.innerHTML = `${s}</svg><div class="chart-tip" role="status" aria-live="polite" hidden></div>`;
  chart = { rows, X, Y, W, pad, i: null };
  bindTip(el);
}

/* ------------------------------------------------------------------ */
/* Tooltip: hover, touch or arrow keys pick a day                      */
/* ------------------------------------------------------------------ */
let chart = null;
function showTip(el, i) {
  const tip = $(".chart-tip", el), svg = $("svg", el), guide = $(".guide", el);
  if (!chart || !tip || !svg) return;
  if (i == null) {
    tip.hidden = true;
    guide?.setAttribute("visibility", "hidden");
    $$(".on", svg).forEach((c) => c.classList.remove("on"));
    chart.i = null;
    return;
  }
  const { rows, X, Y, W } = chart;
  const r = rows[i];
  chart.i = i;
  guide.setAttribute("x1", X(i)); guide.setAttribute("x2", X(i));
  guide.setAttribute("visibility", "visible");
  $$("circle", svg).forEach((c) => c.classList.toggle("on", +c.dataset.i === i));
  const less = r.base ? (1 - r.mae / r.base) : 0;
  tip.innerHTML = `<p class="tt-d">${shortDate(r.d)}${r.m ? ` · ${esc(r.m)}` : ""}</p>
    <p class="tt-row"><i class="tt-model"></i>Model <b>${r.mae.toFixed(2)}</b></p>
    <p class="tt-row"><i class="tt-avg"></i>10-game avg <b>${r.base.toFixed(2)}</b></p>
    <p class="tt-f ${less >= 0 ? "good" : "bad"}">${pct(Math.abs(less))} ${less >= 0 ? "less" : "more"} error · ${count(r.n)} players</p>`;
  tip.hidden = false;
  const scale = svg.getBoundingClientRect().width / W;
  const px = X(i) * scale, py = Math.min(Y(r.mae), Y(r.base)) * scale;
  const tw = tip.offsetWidth, th = tip.offsetHeight, box = el.clientWidth;
  const left = px + 14 + tw > Math.min(box - 8, (W - chart.pad.r) * scale) ? px - 14 - tw : px + 14;   // keep clear of the end labels
  tip.style.transform = `translate(${Math.max(4, left).toFixed(0)}px, ${Math.max(4, py - th / 2).toFixed(0)}px)`;
}
function bindTip(el) {
  if (el.dataset.tip) return;
  el.dataset.tip = "1";
  el.tabIndex = 0;
  el.setAttribute("aria-label", "Day by day chart. Use the left and right arrow keys to read each day.");
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
    e.preventDefault();
    e.stopPropagation();   // don't change the day on the Games view's arrow keys
    const n = chart.rows.length - 1, cur = chart.i ?? n;
    const i = e.key === "Escape" ? null : e.key === "Home" ? 0 : e.key === "End" ? n
      : Math.max(0, Math.min(n, cur + (e.key === "ArrowLeft" ? -1 : 1) * (chart.i == null ? 0 : 1)));
    showTip(el, i);
  });
  el.addEventListener("blur", () => showTip(el, null));
}

/* ------------------------------------------------------------------ */
/* Calibration: did favorites win as often as the model said?          */
/* ------------------------------------------------------------------ */
const BINS = [[0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 1.0001]];
let calibBins = [];
function renderCalibration(m) {
  const games = m.games.filter((g) => g.played && isNum(g.prob) && isNum(g.rh) && isNum(g.ra) && g.rh !== g.ra);
  calibBins = BINS.map(([a, b]) => {
    const inBin = games.filter((g) => { const f = Math.max(g.prob, 1 - g.prob); return f >= a && f < b; });
    const said = inBin.length ? inBin.reduce((s, g) => s + Math.max(g.prob, 1 - g.prob), 0) / inBin.length : null;
    const won = inBin.filter((g) => (g.prob >= 0.5 ? g.rh > g.ra : g.ra > g.rh)).length;
    return { a, b: Math.min(1, b), n: inBin.length, said, won, rate: inBin.length ? won / inBin.length : null };
  });
  const tb = $("#calib-table tbody");
  if (!games.length) {
    tb.innerHTML = '<tr><td colspan="4" class="empty">No games scored yet.</td></tr>';
    $("#calib-chart").innerHTML = "";
    $("#calib-note").textContent = "";
    return;
  }
  tb.innerHTML = calibBins.map((r) => `<tr>
    <td>${Math.round(r.a * 100)}–${Math.round(r.b * 100)}%</td>
    <td class="num">${r.n}</td>
    <td class="num">${r.n ? pct(r.said) : NONE}</td>
    <td class="num">${r.n ? `${pct(r.rate)}<small>${r.won} of ${r.n}</small>` : NONE}</td></tr>`).join("");
  const expected = games.reduce((s, g) => s + Math.max(g.prob, 1 - g.prob), 0);
  const won = calibBins.reduce((s, r) => s + r.won, 0);
  $("#calib-note").textContent = `Across ${count(games.length)} games the model expected its favorites to win ` +
    `${expected.toFixed(1)}; they won ${won}. With this few games per group, a gap of 10 points or more can still be luck.`;
  drawCalibration();
}

export function drawCalibration() {
  const el = $("#calib-chart");
  if (!el || !calibBins.length) return;
  const S = 320, pad = { l: 40, r: 14, t: 14, b: 34 };
  const iw = S - pad.l - pad.r, ih = S - pad.t - pad.b;
  const X = (v) => pad.l + ((v - 0.5) / 0.5) * iw;
  const Y = (v) => pad.t + ih - (Math.max(0, v - 0) / 1) * ih;   // actual win rate runs 0 to 100%
  let s = `<svg viewBox="0 0 ${S} ${S}" role="img" aria-label="Calibration: the win probability given to favorites against how often they won">`;
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    s += `<line class="grid" x1="${pad.l}" x2="${S - pad.r}" y1="${Y(v)}" y2="${Y(v)}"/>`;
    s += `<text x="${pad.l - 7}" y="${Y(v) + 4}" text-anchor="end">${v * 100}%</text>`;
  }
  for (const v of [0.5, 0.6, 0.7, 0.8, 0.9, 1]) s += `<text x="${X(v)}" y="${S - 16}" text-anchor="middle">${Math.round(v * 100)}%</text>`;
  s += `<text class="axis" x="${pad.l + iw / 2}" y="${S - 2}" text-anchor="middle">Model said the favorite would win</text>`;
  s += `<text class="axis" transform="translate(11 ${pad.t + ih / 2}) rotate(-90)" text-anchor="middle">Favorites actually won</text>`;
  s += `<line class="diag" x1="${X(0.5)}" y1="${Y(0.5)}" x2="${X(1)}" y2="${Y(1)}" pathLength="1"/>`;
  const maxN = Math.max(...calibBins.map((r) => r.n), 1);
  calibBins.forEach((r, i) => {
    if (!r.n) return;
    const rad = 5 + 13 * Math.sqrt(r.n / maxN);
    s += `<line class="gap" x1="${X(r.said)}" x2="${X(r.said)}" y1="${Y(r.said)}" y2="${Y(r.rate)}"/>`;
    s += `<circle class="cal-dot" style="--i:${i}" cx="${X(r.said)}" cy="${Y(r.rate)}" r="${rad.toFixed(1)}"><title>${Math.round(r.a * 100)}–${Math.round(r.b * 100)}%: said ${pct(r.said)}, won ${pct(r.rate)} (${r.won} of ${r.n})</title></circle>`;
    s += `<text class="cal-n" x="${X(r.said)}" y="${Y(r.rate) + 4}" text-anchor="middle">${r.n}</text>`;
  });
  el.innerHTML = `${s}</svg>`;
}

function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}
