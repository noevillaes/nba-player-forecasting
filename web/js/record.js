// The Track record view: season figures, error by stat and the day-by-day chart.

import { state } from "./store.js";
import { STAT_NAME, RECORD_ORDER } from "./stats.js";
import { $, $$, esc, isNum, NONE, pct, count, shortDate } from "./format.js";

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
  rows.forEach((r, i) => {
    const t = `<title>${shortDate(r.d)}: model ${esc(r.m || "")} ${r.mae.toFixed(2)}, 10-game average ${r.base.toFixed(2)}, ${r.n} players</title>`;
    s += `<circle class="avg-dot" cx="${X(i)}" cy="${Y(r.base)}" r="3.5">${t}</circle><circle class="model-dot" cx="${X(i)}" cy="${Y(r.mae)}" r="4">${t}</circle>`;
  });
  const last = rows[rows.length - 1];
  let ym = Y(last.mae) + 4, yb = Y(last.base) + 4;
  if (Math.abs(ym - yb) < 15) { if (ym >= yb) ym = yb + 15; else yb = ym + 15; }
  const lx = X(rows.length - 1) + 12;
  s += `<text class="lbl model" x="${lx}" y="${ym}">Model ${last.mae.toFixed(2)}</text>`;
  s += `<text class="lbl avg" x="${lx}" y="${yb}">10-game avg ${last.base.toFixed(2)}</text>`;
  el.innerHTML = `${s}</svg>`;
}

function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}
