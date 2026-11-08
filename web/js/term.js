// The slate as a terminal printout: one line per game, typed out with a block meter.
// The markup already holds the final state, so with no script or with reduced motion
// the slate simply reads; the animation only plays a line in when it first scrolls
// into view.

import { reduceMotion } from "./format.js";

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=/<>";
export const CELLS = 24;   // blocks in a probability meter

/** The win-probability meter, read left to right. Only the favourite's share is filled
 *  with its colour; the underdog's share is drawn hollow in its own. */
export function termBar(pAway, away, home) {
  const n = Math.round(pAway * CELLS);
  const awayFav = pAway > 0.5;
  const cells = Array.from({ length: CELLS }, (_, i) => {
    const isAway = i < n;
    const dog = isAway !== awayFav ? " dog" : "";
    return `<i class="on${dog}" style="--c:${isAway ? away : home}"></i>`;
  });
  return `<span class="tbar" aria-hidden="true">${cells.join("")}</span>`;
}

/** Type a field out left to right, with a short scrambled edge ahead of the cursor. */
function typeOut(el, delay, step = 26) {
  const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (tw.nextNode()) nodes.push({ n: tw.currentNode, orig: tw.currentNode.data });
  const total = nodes.reduce((s, x) => s + x.orig.length, 0);
  if (!total) return 0;
  // blank, not empty: a monospace field keeps its width while it types
  const paint = (k) => {
    let at = 0;
    for (const { n, orig } of nodes) {
      n.data = [...orig].map((c, i) => {
        const j = at + i;
        if (j < k || c === " ") return c;
        if (j < k + 3) return GLYPHS[(Math.random() * GLYPHS.length) | 0];
        return " ";
      }).join("");
      at += orig.length;
    }
  };
  paint(0);
  let k = 0;
  setTimeout(function tick() {
    k += 1;
    paint(k);
    if (k < total + 3) setTimeout(tick, step);
    else for (const { n, orig } of nodes) n.data = orig;
  }, delay);
  return delay + (total + 3) * step;
}

function playLine(row) {
  const cells = [...row.querySelectorAll(".tbar i")];
  cells.forEach((c) => c.classList.remove("on"));
  let t = 0;
  for (const el of row.querySelectorAll(".tx")) {
    if (el.matches(".s-h")) {          // the meter draws between the two halves of the line
      cells.forEach((c, k) => setTimeout(() => c.classList.add("on"), t + k * 16));
      t += cells.length * 16;
    }
    t = typeOut(el, t, 22) - 40;
  }
}

let observer = null;
/** Play every line of a freshly built slate as it comes into view, a beat apart. */
export function playSlate(list) {
  observer?.disconnect();
  if (reduceMotion() || !("IntersectionObserver" in window)) return;
  let queue = 0, last = 0;
  observer = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      observer.unobserve(e.target);
      const now = performance.now();
      if (now - last > 600) queue = 0;   // a new batch scrolled in: start the stagger again
      last = now;
      setTimeout(() => playLine(e.target), queue++ * 110);
    }
  }, { threshold: 0.35 });
  for (const row of list.querySelectorAll(".row, .tl-note")) observer.observe(row);
}
