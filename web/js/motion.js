// Motion layer. Reads the page the other modules render and animates it; it never changes data.
//
//   ascii ball    a basketball drawn in ASCII on the band, with a wake that follows the cursor
//                 (after stackedlol/ascii-sharks)
//   lens          the topographic lines turn orange under the cursor (Lando Norris' cursor reveal)
//   block reveal  titles are uncovered word by word by solid blocks (Lando Norris)
//   word paint    long text darkens word by word as it scrolls through (Spade)
//   count up      the numbers that matter count up when they change (Spade)
//   (the day's scores run along the bottom line: see bcast.js)
//   floating nav  the nav turns into a glass pill once the page scrolls (HorizonX)
//   decode        mono labels decode on hover (HorizonX, affectUI)
//   live run      the "Every morning" steps check off in order (affectUI)
//   footer        the footer opens from a card to the full width (Spade, Lando Norris)
//
// Everything stops for prefers-reduced-motion and pauses while off screen.

const RM = matchMedia("(prefers-reduced-motion: reduce)");
const still = () => RM.matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOut = (t) => 1 - Math.pow(1 - t, 4);

const pointer = { x: -1e4, y: -1e4, px: -1e4, py: -1e4, vx: 0, active: false, t: 0 };
addEventListener("pointermove", (e) => {
  pointer.vx = e.clientX - pointer.x;
  pointer.x = e.clientX; pointer.y = e.clientY; pointer.active = true; pointer.t = performance.now();
}, { passive: true });
document.documentElement.addEventListener("pointerleave", () => { pointer.active = false; });

/* ================================================================== */
/* ASCII basketball + cursor wake + lens                              */
/* ================================================================== */
// leather: deep burnt orange in shadow up to bright orange in the light
const BALL_TONES = ["#6A2C10", "#93401A", "#BC5421", "#DB6A2B", "#F08944"];
const BODY = ".:;t%SX8#@";   // sparse in shadow, dense in light (lit glyphs on a dark band), after ascii-sharks
const WAKE = " .·:+*";
const NOISE = "!#$%&*+-:;=?@^~01";

function asciiBand(court) {
  if (court.dataset.ascii) return;
  court.dataset.ascii = "1";
  const svg = $(".court-lines", court);
  if (svg) {                       // lens: a second copy of the lines, shown only around the cursor
    const lens = svg.cloneNode(true);
    lens.classList.add("lens");
    svg.after(lens);
  }
  const cv = document.createElement("canvas");
  cv.className = "ascii";
  cv.setAttribute("aria-hidden", "true");
  // out of the flow even if the stylesheet is missing or stale: never let it size the band
  cv.style.cssText = "position:absolute;left:0;top:0;z-index:-1;pointer-events:none;display:block";
  court.prepend(cv);
  const ctx = cv.getContext("2d");

  let W = 0, H = 0, dpr = 1, cw = 7, ch = 12, cols = 0, rows = 0, wake = new Float32Array(0), next = new Float32Array(0);
  let visible = true, raf = 0, last = 0, born = 0;
  let yaw = 0.6, spin = 0.45, tilt = 0.32, tiltTo = 0.32;
  const lensPos = { x: -999, y: -999, o: 0 };
  const font = '500 11px "Plex Mono", ui-monospace, monospace';

  function size() {
    const r = court.getBoundingClientRect();
    if (Math.round(r.width) === W && Math.round(r.height) === H && cv.width) return;
    W = Math.round(r.width); H = Math.round(r.height);
    if (W < 2 || H < 2) return;
    dpr = Math.min(devicePixelRatio || 1, 2);
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.width = `${W}px`; cv.style.height = `${H}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = font; ctx.textBaseline = "middle"; ctx.textAlign = "center";
    cw = ctx.measureText("M").width || 6.6; ch = 12;
    cols = Math.ceil(W / cw); rows = Math.ceil(H / ch);
    wake = new Float32Array(cols * rows); next = new Float32Array(cols * rows);
    if (still()) draw(0);
  }

  // the part of the band that isn't covered by a sheet
  function open() {
    const flat = court.dataset.view === "method" || court.dataset.state === "error" || court.classList.contains("legal-head");
    const ov = flat ? 0 : parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--overlap")) || 0;
    return H - ov;
  }
  function ball() {
    const h = open();
    if (W <= 680) {
      // phones: only the Games band has a free corner (beside the day's numbers)
      if (court.dataset.view !== "games" || court.dataset.state === "error") return { cx: -999, cy: -999, r: 0, a: 0 };
      const r = Math.min(W * 0.2, 74);
      return { cx: W - r - 14, cy: h - r - 22, r, a: 0.6 };
    }
    // between the controls row and the sheet, right of the title
    const tools = $(".court-tools", court);
    const top = tools && tools.offsetHeight ? tools.getBoundingClientRect().bottom - court.getBoundingClientRect().top + 18 : 24;
    const r = Math.max(60, Math.min((h - top - 18) / 2, W * 0.15, 200));
    return { cx: W * 0.79, cy: top + r, r, a: 1 };
  }

  function stepWake(dt) {
    const r = court.getBoundingClientRect();
    const lx = pointer.x - r.left, ly = pointer.y - r.top;
    const inside = pointer.active && lx >= 0 && ly >= 0 && lx < W && ly < open();
    if (inside && performance.now() - pointer.t < 120) {
      const c0 = Math.floor(lx / cw), r0 = Math.floor(ly / ch);
      for (let y = -3; y <= 3; y++) for (let x = -5; x <= 5; x++) {
        const c = c0 + x, rr = r0 + y;
        if (c < 0 || rr < 0 || c >= cols || rr >= rows) continue;
        const d = Math.hypot(x * 0.66, y);
        wake[rr * cols + c] = Math.min(1, wake[rr * cols + c] + Math.max(0, 0.95 - d * 0.22));
      }
    }
    const k = Math.pow(0.955, dt * 60);
    for (let y = 1; y < rows - 1; y++) for (let x = 1; x < cols - 1; x++) {
      const i = y * cols + x;
      const n = (wake[i - 1] + wake[i + 1] + wake[i - cols] + wake[i + cols]) * 0.25;
      next[i] = (wake[i] * 0.7 + n * 0.3) * k;
    }
    [wake, next] = [next, wake];
    // lens follows the cursor with a little lag
    lensPos.x = lerp(lensPos.x === -999 ? lx : lensPos.x, lx, 0.14);
    lensPos.y = lerp(lensPos.y === -999 ? ly : lensPos.y, ly, 0.14);
    lensPos.o = lerp(lensPos.o, inside ? 1 : 0, 0.08);
    court.style.setProperty("--mx", `${lensPos.x.toFixed(1)}px`);
    court.style.setProperty("--my", `${lensPos.y.toFixed(1)}px`);
    court.style.setProperty("--lens", lensPos.o.toFixed(3));
  }

  function draw(dt) {
    ctx.clearRect(0, 0, W, H);
    const b = ball();
    const age = (performance.now() - born) / 1000;

    // wake
    ctx.fillStyle = "#F4F3F1";
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const v = wake[y * cols + x];
      if (v < 0.04) continue;
      const px = (x + 0.5) * cw, py = (y + 0.5) * ch;
      if (Math.hypot(px - b.cx, py - b.cy) < b.r + 4) continue;
      ctx.globalAlpha = Math.min(0.9, v * 1.5);
      ctx.fillStyle = v > 0.55 ? "#E0956A" : "#F4F3F1";
      ctx.fillText(WAKE[Math.min(WAKE.length - 1, 1 + Math.floor(v * (WAKE.length - 1)))], px, py);
    }

    // the ball: each cell samples a rotating sphere
    const pr = court.getBoundingClientRect();
    const near = pointer.active ? clamp(1 - Math.hypot(pointer.x - pr.left - b.cx, pointer.y - pr.top - b.cy) / (b.r * 2.2)) : 0;
    tiltTo = 0.32 + (pointer.active ? clamp((pointer.y - pr.top - b.cy) / b.r, -1, 1) * 0.35 * near : 0);
    tilt = lerp(tilt, tiltTo, 0.06);
    if (near > 0.3 && Math.abs(pointer.vx) > 0 && performance.now() - pointer.t < 80) spin += pointer.vx * 0.012 * near;
    spin = lerp(spin, 0.45, 0.02);
    yaw += spin * dt;

    const cb = Math.cos(tilt), sb = Math.sin(tilt), ca = Math.cos(yaw), sa = Math.sin(yaw);
    const L = [-0.48, -0.58, 0.66];
    const seam = Math.max(0.085, 0.95 * ch / b.r);   // wide enough to read as grooves at any size
    if (!b.r) { ctx.globalAlpha = 1; return; }
    const c0 = Math.floor((b.cx - b.r) / cw), c1 = Math.ceil((b.cx + b.r) / cw);
    const r0 = Math.floor((b.cy - b.r) / ch), r1 = Math.ceil((b.cy + b.r) / ch);
    const scramble = clamp(1 - age / 1.6);
    for (let y = r0; y <= r1; y++) {
      for (let x = c0; x <= c1; x++) {
        const px = (x + 0.5) * cw, py = (y + 0.5) * ch;
        const nx = (px - b.cx) / b.r, ny = (py - b.cy) / b.r, d2 = nx * nx + ny * ny;
        if (d2 > 1) continue;
        const nz = Math.sqrt(1 - d2);
        // undo tilt (around x), then yaw (around y): object-space point on the ball
        const y1 = ny * cb - nz * sb, z1 = ny * sb + nz * cb;
        const qx = nx * ca + z1 * sa, qz = -nx * sa + z1 * ca, qy = y1;
        // a real 8-panel ball: two great circles (vertical and horizontal) and the two side
        // curves "( )" that bow out at the equator and pull in toward the poles
        const isSeam = Math.abs(qx) < seam || Math.abs(qy) < seam ||
          Math.abs(Math.abs(qx) - (0.72 - 0.3 * qy * qy)) < seam * 0.9;
        const light = clamp(nx * L[0] + ny * L[1] + nz * L[2]);
        const shade = clamp(0.18 + light * 0.9);
        let g, a;
        if (isSeam) continue;
        {
          const j = ((x * 73856093) ^ (y * 19349663)) & 3;            // fixed per-cell jitter: texture, not noise
          g = BODY[clamp(Math.round(shade * (BODY.length - 1)) + (j === 3 ? -1 : j === 2 ? 1 : 0), 0, BODY.length - 1)];
          a = (0.55 + shade * 0.45) * b.a;
          ctx.fillStyle = BALL_TONES[Math.min(BALL_TONES.length - 1, Math.floor(shade * BALL_TONES.length))];
        }
        if (d2 > 0.9) { g = ":"; a *= 0.75; }
        if (scramble > 0 && Math.random() < scramble) { g = NOISE[(Math.random() * NOISE.length) | 0]; ctx.fillStyle = "#F4F3F1"; a *= 0.6; }
        ctx.globalAlpha = a;
        ctx.fillText(g, px, py);
      }
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
    last = now;
    stepWake(dt);
    draw(dt);
    raf = requestAnimationFrame(frame);
  }
  function run() {
    cancelAnimationFrame(raf);
    if (still()) { born = -1e6; draw(0); return; }
    if (!visible || document.hidden) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  new ResizeObserver(size).observe(court);
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; run(); }).observe(court);
  document.addEventListener("visibilitychange", run);
  RM.addEventListener("change", run);
  born = performance.now();
  size();
  (document.fonts ? document.fonts.load(font) : Promise.resolve()).finally(() => { size(); run(); });
}

/* ================================================================== */
/* Block reveal (titles)                                              */
/* ================================================================== */
function splitWords(el) {
  const frag = document.createDocumentFragment();
  let i = 0;
  const word = (node) => {
    const w = document.createElement("span");
    w.className = "w";
    w.style.setProperty("--wi", i++);
    const inner = document.createElement("span");
    inner.className = "wi";
    inner.append(node);
    w.append(inner);
    return w;
  };
  for (const n of [...el.childNodes]) {
    if (n.nodeType === 3) {
      for (const part of n.data.split(/(\s+)/)) {
        if (!part) continue;
        frag.append(/^\s+$/.test(part) ? document.createTextNode(part) : word(document.createTextNode(part)));
      }
    } else if (n.nodeType === 1) frag.append(word(n));
  }
  el.replaceChildren(frag);
  el.dataset.split = el.textContent;
}

function play(el) {
  el.classList.remove("rv-play", "rv-wait");
  void el.offsetWidth;   // restart the animation
  el.classList.add("rv-play");
}

const titleIO = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { titleIO.unobserve(e.target); play(e.target); }
}, { rootMargin: "0px 0px -12% 0px" });

/** Split a title and reveal it now (on the band) or when it scrolls in (on the paper). */
function reveal(el, { now = false } = {}) {
  el.classList.add("rv");
  splitWords(el);
  if (still()) return;
  if (now) { play(el); return; }
  el.classList.add("rv-wait");
  titleIO.observe(el);
}

/** Titles whose text other modules rewrite: reveal again only when the words really change. */
function watchTitle(el, opts) {
  let shown = el.textContent;
  reveal(el, opts);
  new MutationObserver(() => {
    if (el.dataset.split === el.textContent && el.querySelector(".w")) return;   // our own split
    const changed = el.textContent !== shown;
    shown = el.textContent;
    el.classList.add("rv");
    splitWords(el);
    if (!changed || still()) { el.classList.remove("rv-wait"); return; }
    const r = el.getBoundingClientRect();
    if (opts?.now || (r.top < innerHeight && r.bottom > 0)) play(el);
    else { el.classList.add("rv-wait"); titleIO.observe(el); }
  }).observe(el, { childList: true, characterData: true, subtree: true });
}

/* ================================================================== */
/* Word paint (scroll-linked)                                         */
/* ================================================================== */
const painted = [];
function paintWords(el) {
  if (el.dataset.paint) return;
  el.dataset.paint = "1";
  const words = [];
  const walk = (node) => {
    for (const n of [...node.childNodes]) {
      if (n.nodeType === 1) { walk(n); continue; }
      if (n.nodeType !== 3 || !n.data.trim()) continue;
      const frag = document.createDocumentFragment();
      for (const part of n.data.split(/(\s+)/)) {
        if (!part) continue;
        if (/^\s+$/.test(part)) { frag.append(part); continue; }
        const s = document.createElement("span");
        s.className = "pw";
        s.textContent = part;
        words.push(s);
        frag.append(s);
      }
      n.replaceWith(frag);
    }
  };
  walk(el);
  el.classList.add("paint");
  painted.push({ el, words, lit: -1 });
}
function paintTick() {
  const vh = innerHeight;
  for (const p of painted) {
    const r = p.el.getBoundingClientRect();
    if (r.bottom < -50 || r.top > vh + 50 || !r.height) continue;
    const t = clamp((vh * 0.95 - r.top) / (r.height + vh * 0.2));
    const lit = Math.round(t * p.words.length);
    if (lit === p.lit) continue;
    p.words.forEach((w, i) => w.classList.toggle("on", i < lit));
    p.lit = lit;
  }
}

/* ================================================================== */
/* Count up                                                           */
/* ================================================================== */
// a number on its own: never the digits inside a word, so "76ers" or "3PM" stay as they are
const NUM = /(?<![A-Za-z\d.])\d[\d,]*(?:\.\d+)?(?![A-Za-z\d])/g;
const toNum = (m) => parseFloat(m.replace(/,/g, ""));
/** Count the numbers in `sel` up to their values. When `from` holds the numbers the region showed
 *  before (same count), they roll from those instead of from zero, so a new day reads as a change.
 *  Returns the final numbers, for the next call. */
function countUp(root, sel, dur = 1000, from = null) {
  const nodes = [];
  for (const el of $$(sel, root)) {
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) {
      const n = tw.currentNode;
      if (n.parentElement.closest("small") || n.data.includes(":") || !/\d/.test(n.data)) continue;
      nodes.push({ n, orig: n.data });
    }
  }
  const finals = nodes.flatMap(({ orig }) => [...orig.matchAll(NUM)].map((m) => toNum(m[0])));
  const start = from && from.length === finals.length ? from : null;
  if (still() || !finals.length || (start && start.every((v, k) => v === finals[k]))) return finals;
  const t0 = performance.now();
  const tick = (now) => {
    const t = clamp((now - t0) / dur), e = easeOut(t);
    let k = 0;
    for (const { n, orig } of nodes) {
      n.data = t >= 1 ? orig : orig.replace(NUM, (m) => {
        const dec = (m.split(".")[1] || "").length;
        const to = finals[k], fr = start ? start[k] : 0;
        k++;
        const v = fr + (to - fr) * e;
        return m.includes(",") ? v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : v.toFixed(dec);
      });
    }
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return finals;
}
/** Count whenever a region is re-rendered with different content. */
function watchCount(container, sel, dur) {
  if (!container) return;
  let seen = "", prev = null;
  const run = () => { prev = countUp(container, sel, dur, prev); };
  const go = () => {
    const html = container.innerHTML;
    if (!html || html === seen) return;
    seen = html;
    const r = container.getBoundingClientRect();
    if (r.top < innerHeight && r.bottom > 0) run();
    else {
      const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); run(); } });
      io.observe(container);
    }
  };
  new MutationObserver(go).observe(container, { childList: true });
  go();
}

/* ================================================================== */
/* Decode (hover)                                                     */
/* ================================================================== */
const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=/<>";
function decode(el) {
  if (still() || el.dataset.decoding) return;
  const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let node = null;
  while (tw.nextNode()) if (tw.currentNode.data.trim()) node = tw.currentNode;
  if (!node) return;
  const orig = node.data;
  // screen readers keep the real name while the letters scramble
  if (!el.hasAttribute("aria-label")) el.setAttribute("aria-label", el.textContent.trim());
  el.dataset.decoding = "1";
  const t0 = performance.now(), dur = 420;
  const tick = (now) => {
    const t = clamp((now - t0) / dur);
    const fixed = Math.floor(t * orig.length);
    node.data = [...orig].map((c, i) => (i < fixed || c === " " ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join("");
    if (t < 1) requestAnimationFrame(tick);
    else { node.data = orig; delete el.dataset.decoding; }
  };
  requestAnimationFrame(tick);
}

/* ================================================================== */
/* Nav, footer, pipeline                                              */
/* ================================================================== */
function navTick() {
  const nav = $(".nav");
  if (nav) nav.classList.toggle("float", scrollY > 90 && innerWidth > 680);
}
function footTick() {
  const f = $(".foot");
  if (!f) return;
  const r = f.getBoundingClientRect();
  const t = still() ? 1 : clamp((innerHeight - r.top) / (Math.min(r.height, innerHeight) * 0.9));
  f.style.setProperty("--open", t.toFixed(3));
}
function footerWord() {
  const w = $(".foot-word");
  if (!w || w.dataset.split) return;
  w.dataset.split = "1";
  let i = 0;
  const wrap = (n) => {
    const frag = document.createDocumentFragment();
    for (const ch of n.textContent) {
      const s = document.createElement("span");
      s.className = "ch";
      s.style.setProperty("--ci", i++);
      s.textContent = ch === " " ? " " : ch;
      frag.append(s);
    }
    n.replaceChildren(frag);
  };
  $$("b, i", w).forEach(wrap);
  if (still()) { w.classList.add("in"); return; }
  const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); w.classList.add("in"); } }, { threshold: 0.4 });
  io.observe(w);
}
// inverse of cubic-bezier(.5, 0, .5, 1): the time at which the beam reaches a fraction of the rail
function beamTime(f) {
  const bez = (t, a, b) => 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3;
  let lo = 0, hi = 1;
  for (let k = 0; k < 30; k++) { const m = (lo + hi) / 2; if (bez(m, 0, 1) < f) lo = m; else hi = m; }
  return bez((lo + hi) / 2, 0.5, 0.5);   // y(t) = f solved for t; the time is x(t)
}
function pipeline() {
  const p = $(".pipeline");
  if (!p) return;
  const steps = $(".steps", p);
  $$(".steps li", p).forEach((li, i) => li.style.setProperty("--i", i));
  if (steps && !$(".beam", steps)) {
    const beam = document.createElement("span");
    beam.className = "beam";
    beam.setAttribute("aria-hidden", "true");
    steps.append(beam);
    const time = () => {
      const rail = steps.offsetHeight - 24 - 30;
      steps.style.setProperty("--rail", `${rail}px`);
      // light each badge as the beam's head (60px into the beam) passes its centre
      $$("li", steps).forEach((li) => {
        const y = li.offsetTop + 11 + 11 - 24;               // badge centre, measured from the rail top
        const f = clamp((y + 40 - 60) / (rail + 40));
        li.style.setProperty("--gd", `${(3.4 + beamTime(f) * 0.8 * 3.6).toFixed(2)}s`);
      });
    };
    time();
    new ResizeObserver(time).observe(steps);
  }
  if (still()) { p.classList.add("run"); return; }
  const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); p.classList.add("run"); } }, { threshold: 0.25 });
  io.observe(p);
}

/* ================================================================== */
/* Spotlight on the track-record cards                                */
/* ================================================================== */
function spotlight() {
  const f = $("#figures");
  if (!f || !matchMedia("(hover: hover)").matches) return;
  f.addEventListener("pointermove", (e) => {
    for (const c of $$(".figure", f)) {
      const r = c.getBoundingClientRect();
      c.style.setProperty("--sx", `${(e.clientX - r.left).toFixed(0)}px`);
      c.style.setProperty("--sy", `${(e.clientY - r.top).toFixed(0)}px`);
    }
  }, { passive: true });
}

/* ================================================================== */
/* Sliding indicators: the tab underline and the segmented-control    */
/* thumb travel to the new choice instead of jumping                  */
/* ================================================================== */
function slider(box, itemSel, isOn, cls) {
  if (!box) return;
  const ind = document.createElement("span");
  ind.className = `${cls} off`;
  ind.setAttribute("aria-hidden", "true");
  box.classList.add("has-ind");
  let placed = false;
  const place = () => {
    if (!ind.isConnected) box.prepend(ind);          // the control was re-rendered
    const on = $$(itemSel, box).find(isOn);
    if (!on || !on.offsetWidth) { ind.classList.add("off"); placed = false; return; }
    const jump = !placed || still();
    if (jump) ind.style.transition = "none";
    ind.style.transform = `translateX(${on.offsetLeft}px) scaleX(${on.offsetWidth})`;
    ind.classList.remove("off");
    if (jump) { void ind.offsetWidth; ind.style.transition = ""; }
    placed = true;
  };
  new MutationObserver(place).observe(box, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-current", "aria-pressed", "disabled"] });
  new ResizeObserver(place).observe(box);
  place();
}

/* ================================================================== */
/* Wide tables: show when there's more to the right                   */
/* ================================================================== */
function tableHints() {
  for (const wrap of $$(".table-wrap")) {
    let hint = null;
    if (wrap.querySelector("#box")) {
      hint = document.createElement("p");
      hint.className = "swipe-hint";
      hint.setAttribute("aria-hidden", "true");
      hint.innerHTML = 'Swipe for all 16 stats<svg class="ico" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';
      wrap.before(hint);
    }
    const sync = () => {
      const more = wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 4;
      wrap.classList.toggle("more", more);
      wrap.classList.toggle("scrolled", wrap.scrollLeft > 2);
      if (hint) hint.classList.toggle("gone", wrap.scrollLeft > 24 || wrap.scrollWidth <= wrap.clientWidth + 4);
    };
    wrap.addEventListener("scroll", sync, { passive: true });
    new ResizeObserver(sync).observe(wrap);
    const table = $("table", wrap);
    if (table) new MutationObserver(sync).observe(table, { childList: true, subtree: true });
    sync();
  }
}

/* ================================================================== */
/* Wire up                                                            */
/* ================================================================== */
function init() {
  document.documentElement.classList.add("motion");
  for (const c of $$(".court")) asciiBand(c);

  // titles on the band reveal immediately; titles on the paper when they scroll in
  for (const id of ["#date-label", "#player-title"]) { const t = $(id); if (t) watchTitle(t, { now: true }); }
  for (const h of $$(".court .head-title:not(#date-label):not(#player-title)")) {
    reveal(h, { now: true });
    const head = h.closest(".head");
    if (head) new MutationObserver(() => { if (!head.hidden && !still()) play(h); }).observe(head, { attributes: true, attributeFilter: ["hidden"] });
  }
  for (const t of $$("main .title, .prose h2")) {
    if (t.id === "match-title" || t.id === "daily-title") watchTitle(t);
    else reveal(t);
  }

  for (const p of $$(".section-head .muted, .method .prose > p:not([id])")) paintWords(p);

  watchCount($("#day-facts"), "dd", 900);
  watchCount($("#figures"), ".v", 1200);
  watchCount($("#scoreline"), ".big", 1100);
  watchCount($("#facts"), "dd", 900);
  watchCount($("#player-facts"), "dd", 900);
  watchCount($("#player-sum"), "dd", 900);


  addEventListener("pointerover", (e) => {
    const t = e.target.closest(".tabs a, .btn-on-court, .seg button, .foot-links a, .btn");
    if (t && !t.contains(e.relatedTarget)) decode(t);
  });
  addEventListener("focusin", (e) => {
    const t = e.target.closest?.(".tabs a, .btn-on-court, .seg button, .foot-links a, .btn");
    if (t && t.matches(":focus-visible")) decode(t);
  });

  footerWord();
  pipeline();
  spotlight();
  tableHints();
  slider($(".tabs"), "a", (a) => a.getAttribute("aria-current") === "page", "tab-ind");
  for (const seg of $$(".seg")) slider(seg, "button", (b) => b.getAttribute("aria-pressed") === "true", "seg-thumb");

  // scroll-linked effects run only when something moved, not on every frame
  let queued = false;
  const tick = () => { queued = false; navTick(); footTick(); paintTick(); };
  const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(tick); } };
  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", schedule);
  new ResizeObserver(schedule).observe(document.body);
  schedule();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
