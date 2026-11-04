// Broadcast layer: the visual language of an NBA telecast and an arena.
//
//   score bug    the selected game as a TV score bug, wiped in with the teams' colours
//   LED scores   the big scores drawn on a dot-matrix arena board
//   bottom line  the day's scores as a TV bottom line, with the model's call on each game
//   shot clock   a countdown to the next tip-off
//
// Reads what the other modules render; never changes data.

import { state, loadMeta } from "./store.js";

const RM = matchMedia("(prefers-reduced-motion: reduce)");
const still = () => RM.matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const CODE = {
  Hawks: "ATL", Celtics: "BOS", Nets: "BKN", Hornets: "CHA", Bulls: "CHI", Cavaliers: "CLE", Mavericks: "DAL",
  Nuggets: "DEN", Pistons: "DET", Warriors: "GSW", Rockets: "HOU", Pacers: "IND", Clippers: "LAC", Lakers: "LAL",
  Grizzlies: "MEM", Heat: "MIA", Bucks: "MIL", Timberwolves: "MIN", Pelicans: "NOP", Knicks: "NYK", Thunder: "OKC",
  Magic: "ORL", "76ers": "PHI", Suns: "PHX", "Trail Blazers": "POR", Kings: "SAC", Spurs: "SAS", Raptors: "TOR",
  Jazz: "UTA", Wizards: "WAS",
};
const code = (team) => CODE[team] || String(team).slice(0, 3).toUpperCase();

/* ================================================================== */
/* Dot-matrix font (5 x 7) and an LED board renderer                  */
/* ================================================================== */
const FONT = {
  0: ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  1: ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  2: ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  3: ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  4: ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  5: ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  6: ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  7: ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  8: ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  9: ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
  ".": ["0", "0", "0", "0", "0", "0", "1"],
  ":": ["0", "1", "0", "0", "0", "1", "0"],
  "-": ["000", "000", "000", "111", "000", "000", "000"],
  " ": ["00", "00", "00", "00", "00", "00", "00"],
};
/** An SVG of `text` as lit dots on a dim grid of unlit ones. Its height is 1em, so it scales with font-size. */
function led(text, { on = "#F4F3F1", off = "rgba(244,243,241,.07)", gap = 1 } = {}) {
  const glyphs = [...String(text)].map((c) => FONT[c] || FONT[" "]);
  const cols = glyphs.reduce((s, g) => s + g[0].length, 0) + gap * (glyphs.length - 1);
  let x = 0, dim = "", lit = "";
  glyphs.forEach((g, gi) => {
    for (let r = 0; r < 7; r++) for (let c = 0; c < g[r].length; c++) {
      const dot = `cx="${x + c + 0.5}" cy="${r + 0.5}" r="0.38"`;
      dim += `<circle ${dot}/>`;
      if (g[r][c] === "1") lit += `<circle ${dot} style="--d:${(Math.random() * 0.4 + gi * 0.07).toFixed(2)}s"/>`;
    }
    x += g[0].length + gap;
  });
  return `<svg class="led" viewBox="0 0 ${cols} 7" style="width:${(cols / 7).toFixed(3)}em" aria-hidden="true" focusable="false">` +
    `<g fill="${off}">${dim}</g><g class="lit" fill="${on}">${lit}</g></svg>`;
}

/** LED odometer: every digit is a vertical strip of lit glyphs that rolls over a fixed grid of
 *  unlit dots to land on its value; the last two digits make a full extra turn. */
function ledRoll(text, { on = "#F4F3F1", off = "rgba(244,243,241,.07)" } = {}) {
  const chars = [...String(text)];
  const digits = chars.filter((c) => /\d/.test(c)).length;
  let idx = 0;
  const cell = (c) => {
    const g = FONT[c] || FONT[" "], w = g[0].length;
    let dim = "";
    for (let r = 0; r < 7; r++) for (let x = 0; x < w; x++) dim += `<circle cx="${x + 0.5}" cy="${r + 0.5}" r="0.38"/>`;
    const grid = `<svg class="led-grid" viewBox="0 0 ${w} 7" aria-hidden="true"><g fill="${off}">${dim}</g></svg>`;
    if (!/\d/.test(c)) {
      let lit = "";
      for (let r = 0; r < 7; r++) for (let x = 0; x < w; x++) if (g[r][x] === "1") lit += `<circle cx="${x + 0.5}" cy="${r + 0.5}" r="0.38"/>`;
      return `<span class="ledc" style="width:${(w / 7).toFixed(3)}em">${grid}<svg class="led-fix" viewBox="0 0 ${w} 7" aria-hidden="true"><g fill="${on}">${lit}</g></svg></span>`;
    }
    // strip: 0-9 twice, each glyph 7 rows plus one blank row
    let lit = "";
    for (let k = 0; k < 20; k++) {
      const gg = FONT[k % 10];
      for (let r = 0; r < 7; r++) for (let x = 0; x < 5; x++) if (gg[r][x] === "1") lit += `<circle cx="${x + 0.5}" cy="${k * 8 + r + 0.5}" r="0.38"/>`;
    }
    const k = +c + (idx >= digits - 2 ? 10 : 0);
    const delay = idx * 0.09, dur = 1.1 + idx * 0.18;
    idx++;
    return `<span class="ledc" style="width:${(5 / 7).toFixed(3)}em">${grid}<span class="led-win">` +
      `<svg class="led-strip" viewBox="0 0 5 159" style="height:${(159 / 7).toFixed(3)}em;--to:${(-(k * 8) / 7).toFixed(3)}em;--dl:${delay}s;--du:${dur}s" aria-hidden="true">` +
      `<g fill="${on}">${lit}</g></svg></span></span>`;
  };
  return `<span class="ledb" aria-hidden="true">${chars.map(cell).join('<span class="led-gap"></span>')}</span>`;
}

/** Plain-text odometer for small numbers (the score bug). */
function odo(el) {
  const v = el.textContent.trim();
  const digits = [...v].filter((c) => /\d/.test(c)).length;
  let i = 0;
  el.innerHTML = `<span class="sr-only">${v}</span><span class="odo-run" aria-hidden="true">${[...v].map((c) => {
    if (!/\d/.test(c)) return c;
    const k = +c + (i >= digits - 2 ? 10 : 0), d = i++;
    return `<span class="odo"><span class="odo-ph">${c}</span><span class="odo-strip" style="--to:${-k}em;--dl:${(0.5 + d * 0.08).toFixed(2)}s;--du:${(1 + d * 0.15).toFixed(2)}s"></span></span>`;
  }).join("")}</span>`;
}
const roll = (el) => { if (still()) { el.classList.add("go"); return; } el.classList.remove("go"); void el.offsetWidth; requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("go"))); };

/* ================================================================== */
/* Score bug + LED scores, rebuilt whenever the matchup changes       */
/* ================================================================== */
function matchup() {
  const line = $("#scoreline");
  if (!line) return;
  const build = () => {
    const sides = $$(".side", line);
    if (sides.length < 2 || sides[0].querySelector(".ledb")) return;
    const read = (s) => ({
      team: $(".name span", s)?.textContent || "",
      color: $(".name .dot", s)?.style.getPropertyValue("--c") || "#555",
      score: $(".big", s)?.textContent.trim() || "",
      proj: $(".big", s)?.classList.contains("proj"),
    });
    const [a, h] = sides.map(read);
    const played = !a.proj;
    const winner = played ? (+a.score > +h.score ? 0 : 1) : -1;

    // LED boards
    sides.forEach((s, i) => {
      const big = $(".big", s), v = big.textContent.trim();
      big.innerHTML = `<span class="sr-only">${v}</span>${ledRoll(v, { on: played ? (i === winner ? "#F7F1E3" : "rgba(247,241,227,.55)") : "#E0956A" })}`;
      big.classList.add("board");
      roll(big);
    });

    // score bug
    const verdict = $("#summary b");
    const call = played && verdict ? (verdict.classList.contains("hit") ? "hit" : "miss") : null;
    const when = $("#match-when")?.textContent || "";
    const status = played ? "FINAL" : /Tonight/.test(when) ? "TONIGHT" : "PREVIEW";
    // the same rounded percentages the page prints under the bar
    const pcts = $$("#prob-labels b").map((x) => parseInt(x.textContent, 10));
    const ph = pcts[1] ?? 50;
    let bug = $("#bug");
    if (!bug) {
      bug = document.createElement("div");
      bug.id = "bug";
      bug.className = "bug";
      bug.setAttribute("aria-hidden", "true");
      line.before(bug);
    }
    const team = (t, side) => `<div class="bug-team ${side}" style="--c:${t.color}">
        <span class="bug-code">${code(t.team)}</span><span class="bug-score">${t.score}</span></div>`;
    bug.innerHTML = `<div class="bug-bar">${team(a, "away")}${team(h, "home")}
        <div class="bug-status"><b>${status}</b>${call ? `<span class="bug-call ${call}"><span class="bc-l">MODEL </span>${call === "hit" ? "✓" : "✗"}</span>` : ""}</div></div>
      <div class="bug-sub">MODEL · ${code(ph >= 50 ? h.team : a.team)} ${Math.max(ph, pcts[0] ?? 100 - ph)}% TO WIN${played ? "" : " · PROJECTED SCORE"}</div>
      <i class="bug-wipe" style="--a:${a.color};--h:${h.color}"></i>`;
    $$(".bug-score", bug).forEach((el) => { odo(el); roll(el); });
    if (!still()) { bug.classList.remove("in"); void bug.offsetWidth; bug.classList.add("in"); }
    else bug.classList.add("in");
  };
  new MutationObserver(() => queueMicrotask(build)).observe(line, { childList: true });
  build();
}

/* ================================================================== */
/* Bottom line                                                        */
/* ================================================================== */
function bottomLine() {
  const list = $("#game-list");
  if (!list) return;
  const bar = document.createElement("div");
  bar.className = "bline";
  bar.setAttribute("aria-hidden", "true");
  bar.innerHTML = '<div class="bline-tag"><b>SCORES</b><span></span></div><div class="bline-run"><div class="bline-track"></div></div>';
  $("#view-games > .wrap").after(bar);
  const build = () => {
    const rows = $$(".row", list);
    bar.hidden = !rows.length;
    if (!rows.length) return;
    const date = $("#date-label")?.textContent || "";
    $(".bline-tag span", bar).textContent = date.replace(/,.*$/, "").slice(0, 3).toUpperCase() + " " + (date.split(", ")[1] || "").toUpperCase();
    const txt = (el) => (el?.firstChild?.nodeType === 3 ? el.firstChild.data : el?.textContent || "").trim();
    const items = rows.map((b) => {
      const aw = $(".t.away span:last-child", b)?.textContent, hm = $(".t.home span:last-child", b)?.textContent;
      const ca = $(".t.away .dot", b)?.style.getPropertyValue("--c"), ch = $(".t.home .dot", b)?.style.getPropertyValue("--c");
      const final = !!$(".s small", b), hit = $(".res .hit", b), miss = $(".res .miss", b);
      const sa = txt($(".s.away", b)), sh = txt($(".s.home", b));
      const win = final ? (+sa > +sh ? "a" : "h") : "";
      return `<span class="bl-game">
        <span class="bl-team${win === "a" ? " w" : ""}"><i style="--c:${ca}"></i>${code(aw)} <b>${sa}</b></span>
        <span class="bl-team${win === "h" ? " w" : ""}"><i style="--c:${ch}"></i>${code(hm)} <b>${sh}</b></span>
        <span class="bl-st">${final ? "FINAL" : "PROJ"}</span>${hit ? '<span class="bl-call hit">MODEL ✓</span>' : miss ? '<span class="bl-call miss">MODEL ✗</span>' : ""}
      </span>`;
    }).join("");
    const track = $(".bline-track", bar);
    track.innerHTML = items + items;
    requestAnimationFrame(() => track.style.setProperty("--dur", `${Math.max(20, track.scrollWidth / 2 / 70).toFixed(1)}s`));
  };
  new MutationObserver(build).observe(list, { childList: true });
  build();
}

/* ================================================================== */
/* Shot clock to the next tip-off                                     */
/* ================================================================== */
async function shotClock() {
  const head = $('.head[data-for="games"]');
  if (!head) return;
  const m = await loadMeta("live").catch(() => null);
  const st = m?.status;
  if (!st) return;
  // tonight's first game if it hasn't started, otherwise the next slate's
  const slates = [
    st.today_time && { at: new Date(st.today_time), games: st.games, tonight: true },
    st.next_time && { at: new Date(st.next_time), games: st.next_games, tonight: false },
  ].filter(Boolean);
  const pick = () => slates.find((x) => x.at > Date.now());
  if (!pick()) return;
  const box = document.createElement("div");
  box.className = "shot";
  box.setAttribute("role", "timer");
  box.innerHTML = '<div class="shot-face"><span class="shot-label">NEXT TIP-OFF</span><span class="shot-digits"></span></div><p class="shot-sub"></p>';
  $("#date-label").before(box);
  const digits = $(".shot-digits", box), sub = $(".shot-sub", box);
  const dayFmt = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "America/New_York" });
  const etFmt = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
  let shown = null;
  const show = () => {
    const slate = pick();
    box.hidden = !slate || state.set !== "live" || state.view !== "games";
    if (!slate) return;
    if (shown !== slate) {
      shown = slate;
      sub.textContent = `${slate.tonight ? "TONIGHT" : dayFmt.format(slate.at).toUpperCase()} · ${etFmt.format(slate.at)} ET · ${slate.games} GAMES`;
    }
    const s = Math.max(0, Math.round((slate.at - Date.now()) / 1000));
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    const txt = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
    if (digits.dataset.t === txt) return;
    digits.dataset.t = txt;
    digits.innerHTML = led(txt, { on: "#F26A4B", off: "rgba(242,106,75,.1)" });
    digits.setAttribute("aria-label", `${hh} hours ${mm} minutes until the next tip-off`);
  };
  show();
  setInterval(show, 1000);
}

function init() {
  matchup();
  bottomLine();
  shotClock();
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
