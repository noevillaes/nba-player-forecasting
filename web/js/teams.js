// Team colours are data: they identify the two sides of a game and nothing else.

const PRIMARY = {
  Hawks: "#C8102E", Celtics: "#007A33", Nets: "#1A1A1A", Hornets: "#1D1160", Bulls: "#CE1141",
  Cavaliers: "#860038", Mavericks: "#00538C", Nuggets: "#0E2240", Pistons: "#C8102E", Warriors: "#1D428A",
  Rockets: "#CE1141", Pacers: "#002D62", Clippers: "#C8102E", Lakers: "#552583", Grizzlies: "#5D76A9",
  Heat: "#98002E", Bucks: "#00471B", Timberwolves: "#0C2340", Pelicans: "#0C2340", Knicks: "#006BB6",
  Thunder: "#007AC1", Magic: "#0077C0", "76ers": "#006BB6", Suns: "#1D1160", "Trail Blazers": "#E03A3E",
  Kings: "#5A2D81", Spurs: "#2B2B2B", Raptors: "#CE1141", Jazz: "#002B5C", Wizards: "#002B5C",
};
// secondary colour, used when both teams share almost the same primary
const SECONDARY = {
  Hawks: "#26282A", Celtics: "#963821", Nets: "#707271", Hornets: "#00788C", Bulls: "#1A1A1A",
  Cavaliers: "#041E42", Mavericks: "#002B5E", Nuggets: "#8B6F2E", Pistons: "#1D42BA", Warriors: "#A47A00",
  Rockets: "#5A5F63", Pacers: "#A07800", Clippers: "#1D428A", Lakers: "#9A7000", Grizzlies: "#12173F",
  Heat: "#41454A", Bucks: "#7A6A4F", Timberwolves: "#236192", Pelicans: "#85714D", Knicks: "#D5520F",
  Thunder: "#EF3B24", Magic: "#5F6A72", "76ers": "#ED174C", Suns: "#E56020", "Trail Blazers": "#1A1A1A",
  Kings: "#63727A", Spurs: "#6F787E", Raptors: "#1A1A1A", Jazz: "#6B5B00", Wizards: "#E31837",
};
const FALLBACK = "#5F646C";

export const darkScheme = matchMedia("(prefers-color-scheme: dark)");

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const luminance = (hex) => {
  const lin = rgb(hex).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
};

/** On the dark theme, near-black team colours are lifted toward white so they stay visible. */
function visible(hex) {
  if (!darkScheme.matches || luminance(hex) >= 0.05) return hex;
  return `#${rgb(hex).map((v) => Math.round(v + (255 - v) * 0.45).toString(16).padStart(2, "0")).join("")}`;
}

/** { away, home } colours that are distinguishable from each other and from the page. */
export function matchupColors(away, home) {
  const a = PRIMARY[away] || FALLBACK;
  let h = PRIMARY[home] || FALLBACK;
  const [x, y] = [rgb(a), rgb(h)];
  if (x.reduce((s, v, i) => s + (v - y[i]) ** 2, 0) < 60 ** 2) h = SECONDARY[home] || FALLBACK;
  return { away: visible(a), home: visible(h) };
}

export const dot = (color) => `<i class="dot" style="--c:${color}" aria-hidden="true"></i>`;
