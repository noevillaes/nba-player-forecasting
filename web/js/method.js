// The How it works view: the model versions listed from the live set's metadata.

import { $, esc, count, shortDate } from "./format.js";

export function renderVersions(m) {
  $("#versions").innerHTML = (m.versions || []).map((v) => {
    let when = "not used yet";
    if (v.from) when = v.active ? `in use since ${shortDate(v.from)}` : `${shortDate(v.from)} to ${shortDate(v.to)}`;
    return `<li><b>${esc(v.v)}</b>, ${when}${v.active ? " (current)" : ""}. ${esc(v.text)}</li>`;
  }).join("");
  $("#recal-note").textContent = m.recal
    ? `The current version's ranges were last recalibrated on ${shortDate(m.recal.from)}, with ${count(m.recal.rows)} player-games.`
    : "The current version's ranges haven't been recalibrated yet. That starts once 1,000 player-games are scored.";
}
