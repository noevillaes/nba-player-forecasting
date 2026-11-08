// Teams: every club's games with the forecast next to the final, and how the model has done with it.

import { state, loadPlayers } from "./store.js";
import { $, esc, isNum, NONE, f1, pct, shortDate, tipTime } from "./format.js";
import { dot, colorOf } from "./teams.js";

const href = (club) => `#view=teams&club=${encodeURIComponent(club)}${state.set !== "live" ? `&set=${esc(state.set)}` : ""}`;

/** One team's side of a game: its forecast and final, and the opponent's. */
function side(g, club) {
  const home = g.home === club;
  return {
    home, opp: home ? g.away : g.home,
    fc: home ? g.ph : g.pa, fcOpp: home ? g.pa : g.ph,
    real: home ? g.rh : g.ra, realOpp: home ? g.ra : g.rh,
    p: isNum(g.prob) ? (home ? g.prob : 1 - g.prob) : null,
  };
}

function record(games, club) {
  const played = games.filter((g) => g.played && isNum(g.rh));
  const won = played.filter((g) => { const s = side(g, club); return s.real > s.realOpp; }).length;
  const hit = played.filter((g) => g.hit === 1).length;
  const err = played.map((g) => g.err_spread).filter(isNum);
  return { n: played.length, won, hit, err: err.length ? err.reduce((a, b) => a + b, 0) / err.length : null };
}

export async function renderTeams(m, isCurrent) {
  const clubs = [...new Set(m.games.flatMap((g) => [g.home, g.away]))].sort();
  const club = clubs.includes(state.club) ? state.club : null;
  $("#team-title").textContent = club || "Teams";
  $("#team-lede").hidden = !!club;
  $("#team-back").hidden = !club;
  document.title = `${club || "Teams"} | NBA Forecasts`;
  $("#team-grid").hidden = !!club;
  $("#team-main").hidden = !club;
  if (!club) {
    $("#team-facts").innerHTML = "";
    $("#team-grid").innerHTML = clubs.map((c) => {
      const r = record(m.games.filter((g) => g.home === c || g.away === c), c);
      return `<li><a href="${href(c)}">${dot(colorOf(c))}<span class="tg-name">${esc(c)}</span>
        <span class="tg-rec">${r.n ? `${r.won}–${r.n - r.won} · model ${r.hit} of ${r.n}` : "no games yet"}</span></a></li>`;
    }).join("");
    return;
  }

  const games = m.games.filter((g) => g.home === club || g.away === club).sort((a, b) => (a.date < b.date ? -1 : 1));
  const r = record(games, club);
  $("#team-facts").innerHTML = [
    ["Record", r.n ? `${r.won}–${r.n - r.won}` : NONE],
    ["Winners picked", r.n ? `${r.hit} of ${r.n} (${pct(r.hit / r.n)})` : NONE],
    ["Average miss on the margin", isNum(r.err) ? `${r.err.toFixed(1)} points` : NONE],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

  const next = games.filter((g) => !g.played).slice(0, 3);
  $("#team-next").innerHTML = next.length ? next.map((g) => {
    const s = side(g, club);
    return `<li><a href="#view=games&date=${esc(g.date)}&game=${esc(g.id)}">
      <span class="tn-when">${shortDate(g.date)}${g.time ? ` · ${tipTime(g.time)}` : ""}</span>
      <span class="tn-opp">${s.home ? "vs" : "@"} ${esc(s.opp)}</span>
      <span class="tn-fc">${f1(s.fc)}–${f1(s.fcOpp)}</span>
      <span class="tn-p">${isNum(s.p) ? `${pct(s.p)} to win` : NONE}</span></a></li>`;
  }).join("") : '<li class="empty">No upcoming games with a forecast yet. Forecasts come out the morning of each game.</li>';

  const past = games.filter((g) => g.played).reverse();
  $("#team-log tbody").innerHTML = past.map((g) => {
    const s = side(g, club);
    const won = s.real > s.realOpp;
    return `<tr>
      <td><a href="#view=games&date=${esc(g.date)}&game=${esc(g.id)}">${shortDate(g.date)}</a></td>
      <td>${s.home ? "vs" : "@"} ${esc(s.opp)}</td>
      <td>${f1(s.fc)}–${f1(s.fcOpp)}</td>
      <td><b>${won ? "W" : "L"}</b> ${s.real}–${s.realOpp}</td>
      <td>${isNum(s.p) ? pct(s.p) : NONE}</td>
      <td class="${g.hit === 1 ? "hit" : "miss"}">${g.hit === 1 ? "✓" : "✗"}<span class="sr-only">${g.hit === 1 ? "winner picked" : "winner missed"}</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="6" class="empty">No games scored yet.</td></tr>`;
  $("#team-log-block").hidden = !past.length;

  const players = await loadPlayers(state.set).catch(() => []);
  if (!isCurrent()) return;
  const roster = players.filter((p) => p.t === club).sort((a, b) => (b.fp ?? 0) - (a.fp ?? 0));
  $("#team-players").innerHTML = roster.map((p) =>
    `<li><a href="#view=players&player=${esc(p.id)}" data-player="${esc(p.id)}">${esc(p.n)}<span>${isNum(p.fp) && p.fp ? `${f1(p.fp)} pts a game` : ""}</span></a></li>`).join("")
    || '<li class="empty">No players with a forecast yet.</li>';
}

