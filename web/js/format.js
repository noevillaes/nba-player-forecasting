// Small, pure helpers: DOM lookup, escaping, numbers and dates.

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const isNum = (x) => typeof x === "number" && !Number.isNaN(x);
export const NONE = "-";
/** 12 -> "12", 12.34 -> "12.3" */
export const fmt = (x, d = 1) => (!isNum(x) ? NONE : Number.isInteger(x) ? String(x) : x.toFixed(d));
/** always one decimal: 17 -> "17.0" */
export const f1 = (x) => (!isNum(x) ? NONE : x.toFixed(1));
export const round = (x) => (!isNum(x) ? NONE : String(Math.round(x)));
export const pct = (x) => `${Math.round(x * 100)}%`;
export const count = (n) => n.toLocaleString("en-US");

export const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- dates ---------- */
const dateOf = (d) => new Date(`${d}T12:00:00`);
const dayFmt = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" });
const dayYearFmt = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const weekdayFmt = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric" });

export const longDate = (d, withYear = false) => (withYear ? dayYearFmt : dayFmt).format(dateOf(d));
export const shortDate = (d) => shortFmt.format(dateOf(d));
export const todayISO = () => {
  const t = new Date();
  return new Date(t - t.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
};

/** The pipeline stamps forecasts in Mexico City time (UTC-6), as "2026-10-23 10:43". */
export const ZONE = "(UTC−6)";
export function clock(stamp) {
  const t = (stamp || "").split(" ")[1];
  if (!t) return "";
  const [h, mi] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(mi).padStart(2, "0")} ${h < 12 ? "a.m." : "p.m."}`;
}
/** "10:43 a.m. (UTC−6) on Friday, Oct 23" */
export function published(stamp, { day = true } = {}) {
  if (!stamp) return "";
  const time = `${clock(stamp)} ${ZONE}`;
  return day ? `${time} on ${weekdayFmt.format(dateOf(stamp.split(" ")[0]))}` : time;
}

export function byMargin(home, away, m) {
  if (!isNum(m)) return NONE;
  if (Math.abs(m) < 0.05) return "Even";
  return `${m > 0 ? home : away} by ${fmt(Math.abs(m))}`;
}
