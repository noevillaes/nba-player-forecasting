#!/usr/bin/env python3
"""
Builds the static website.

Copies the page files in web/ to an output folder (filling in the shared pieces
in web/partials/, marked <!-- include:NAME --> in the pages) and turns the
pipeline CSVs into small JSON files the page loads on demand:

    data/<set>/meta.json          every game (forecast + result) and the daily scoreboard
    data/<set>/days/<date>.json   every player forecast for that day

Loading one day at a time keeps the site fast even when historial.csv grows to
tens of MB over the season.

Only uses the standard library.

    python web/build.py                # writes _site/
    python -m http.server -d _site     # preview at http://localhost:8000
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
PAGES = ["index.html", "terms.html", "privacy.html"]
STATIC = ["style.css", "favicon.svg", "og.png"]
STATIC_DIRS = ["fonts", "js"]
INCLUDE = re.compile(r"<!-- include:([a-z]+) -->")
# where the site is published: link previews (WhatsApp, Instagram, X) need the image's full address
SITE_URL = os.environ.get("SITE_URL", "https://noevillaes.github.io/nba-player-forecasting/")
# style.css and the js modules get ?v=<hash of the site's code>, so a browser never mixes
# a new page with an old stylesheet or script it kept in its cache
ASSET_REF = re.compile(r'((?:href|src)="(?:style\.css|js/[a-z]+\.js))(")')
JS_IMPORT = re.compile(r'(from\s+"\./[a-z]+\.js)(")')

DATASETS = {
    "live": {
        "label": "Live 2026-27",
        "registry": "results/registro_modelos.json",
        "players": "predictions/historial.csv",
        "games": "predictions/historial_juegos.csv",
        "score": "results/marcador.csv",
        "status": "results/estado.json",
        "lines": "predictions/lineas.csv",
        "injuries": "predictions/lesiones_{date}.csv",
        "why": "predictions/{date}.csv",
    },
    "backtest": {
        "label": "Backtest, March 2026 (simulated)",
        "players": "predictions/historial_backtest.csv",
        "games": "predictions/historial_juegos_backtest.csv",
        "score": "results/marcador_backtest.csv",
    },
}

STATUS = {"Jugó": "played", "No jugó": "dnp", "Pendiente": "pending"}
INJURY = {"Out": "out", "Day-To-Day": "dtd", "Questionable": "dtd", "Doubtful": "out"}
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")

def person_key(name, team):
    """'Luka Dončić', 'Lakers' -> 'luka doncic|lakers', so ESPN's injury names meet the NBA's."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = SUFFIX.sub("", re.sub(r"[^a-z ]", "", n.replace("-", " ")))
    return " ".join(n.split()) + "|" + (team or "").lower()


WHY = {"PTS": "points", "REB": "reboundsTotal", "AST": "assists"}


def parse_why(text):
    """'10.1|forma:+19.3;minutos:+2.6' -> [10.1, [['forma', 19.3], ['minutos', 2.6]]]"""
    if not text or "|" not in text:
        return None
    base, parts = text.split("|", 1)
    items = []
    for part in filter(None, parts.split(";")):
        name, _, value = part.partition(":")
        items.append([name, num(value, 1)])
    return [num(base, 1), items]


def read_times(path):
    """Tip-off time of each game (predictions/lineas.csv, written by src/lineas.py), by gameId and by
    date|home|away (the morning rows are saved before the forecast gives the game its NBA id)."""
    out = {}
    for r in read(path) or []:
        if not r.get("hora_utc"):
            continue
        out[f'{r["fecha"]}|{r["local"]}|{r["visitante"]}'] = r["hora_utc"]
        if r.get("gameId"):
            out[r["gameId"]] = r["hora_utc"]
    return out


def num(x, nd=2):
    """'12.30' -> 12.3, '' -> None, '5.0' -> 5"""
    if x is None or x == "":
        return None
    try:
        v = round(float(x), nd)
    except ValueError:
        return None
    return int(v) if v == int(v) else v


def read(path):
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_set(key, cfg, out):
    games_rows, player_rows, score_rows = read(cfg["games"]), read(cfg["players"]), read(cfg["score"])
    if games_rows is None or player_rows is None:
        print(f"  {key}: missing CSVs, skipped")
        return False

    games = []
    for g in games_rows:
        played = g.get("estado") == "Jugado"
        games.append({
            "id": g["gameId"], "date": g["fecha"],
            "home": g["local"], "away": g["visitante"],
            "ph": num(g["pts_local"], 1), "ph10": num(g["pts_local_q10"], 1), "ph90": num(g["pts_local_q90"], 1),
            "pa": num(g["pts_visita"], 1), "pa10": num(g["pts_visita_q10"], 1), "pa90": num(g["pts_visita_q90"], 1),
            "total": num(g["total"], 1), "spread": num(g["spread"], 1), "prob": num(g["prob_local"], 3),
            "made": g.get("generado", ""),
            "played": played,
            "rh": num(g.get("real_local")) if played else None,
            "ra": num(g.get("real_visita")) if played else None,
            "err_total": num(g.get("error_total"), 1) if played else None,
            "err_spread": num(g.get("error_spread"), 1) if played else None,
            "hit": num(g.get("acierto_ganador")) if played else None,
            "brier": num(g.get("brier"), 3) if played else None,
            "in_h": num(g.get("dentro_80_local")) if played else None,
            "in_a": num(g.get("dentro_80_visita")) if played else None,
        })
    times = read_times(cfg["lines"]) if cfg.get("lines") else {}
    for g in games:
        g["time"] = times.get(g["id"]) or times.get(f'{g["date"]}|{g["home"]}|{g["away"]}')

    # players grouped by day, then by game + person
    days = {}
    for r in player_rows:
        day = days.setdefault(r["fecha"], {})
        pid = str(int(float(r["personId"])))
        p = day.setdefault((r["gameId"], pid), {
            "g": r["gameId"], "id": pid, "n": r["jugador"], "t": r["equipo"],
            "home": int(float(r["local"] or 0)), "st": STATUS.get(r["estado"], r["estado"]),
            "adj": num(r.get("ajuste_equipo"), 3), "s": {},
        })
        # forecast, q10, q90, last-10 average, actual, abs error, inside 80% range
        p["s"][r["estadistica"]] = [
            num(r["pronostico"], 1), num(r["q10"], 1), num(r["q90"], 1), num(r["baseline"], 1),
            num(r["real"], 1), num(r["error_abs"], 2), num(r["dentro_80"]),
        ]

    # why: what moved each forecast (src/explicar.py), from the day's forecast file
    if cfg.get("why"):
        for d, day in days.items():
            for r in read(cfg["why"].format(date=d)) or []:
                p = day.get((r.get("gameId"), str(int(float(r["personId"])))))
                if not p:
                    continue
                why = {k: parse_why(r.get(f"pq_{col}")) for k, col in WHY.items()}
                why = {k: v for k, v in why.items() if v}
                if why:
                    p["why"] = why

    if cfg.get("injuries"):
        for d, day in days.items():
            report = read(cfg["injuries"].format(date=d))
            if not report:
                continue
            listed = {person_key(r["jugador"], r["equipo"]): r for r in report}
            for p in day.values():
                r = listed.get(person_key(p["n"], p["t"]))
                if r and r.get("estado") in INJURY:
                    p["inj"] = [INJURY[r["estado"]], r.get("tipo") or ""]

    score = [{
        "d": r["fecha"], "s": r["estadistica"], "n": int(float(r["jugadores"] or 0)),
        "mae": num(r["MAE"], 3), "base": num(r["MAE_baseline"], 3), "cov": num(r["cobertura_80"], 3),
        "m": r.get("modelo") or "v1",
    } for r in (score_rows or [])]

    # first and last day each model version made forecasts
    used = {}
    for r in player_rows:
        v = r.get("modelo") or "v1"
        a, b = used.get(v, (r["fecha"], r["fecha"]))
        used[v] = (min(a, r["fecha"]), max(b, r["fecha"]))
    versions, recal = model_versions(cfg.get("registry"), used)

    # one file per player with his whole season, plus a small index for the search box
    gmap = {g["id"]: g for g in games}
    people = {}
    for d in sorted(days):
        for (gid, pid), p in days[d].items():
            g = gmap.get(gid, {})
            home = bool(p["home"])
            opp = g.get("away") if home else g.get("home")
            q = people.setdefault(pid, {"id": pid, "n": p["n"], "t": p["t"], "g": []})
            q["n"], q["t"] = p["n"], p["t"]          # latest name and team win
            q["g"].append({"d": d, "g": gid, "o": opp, "h": int(home), "st": p["st"],
                           "s": {c: v[:5] + v[6:7] for c, v in p["s"].items()}})   # forecast, q10, q90, base, actual, inside
            if p.get("inj"):
                q["g"][-1]["inj"] = p["inj"]
            if p.get("why") and p["st"] == "pending":       # only the next game needs it on the player page
                q["g"][-1]["why"] = p["why"]
            if g.get("time"):
                q["g"][-1]["tm"] = g["time"]
    pdir = os.path.join(out, "data", key, "players")
    os.makedirs(pdir, exist_ok=True)
    index = []
    for pid, q in people.items():
        dump(os.path.join(pdir, f"{pid}.json"), q)
        played = [x for x in q["g"] if x["st"] == "played"]
        pts = [x["s"]["PTS"][0] for x in q["g"] if x["s"].get("PTS") and x["s"]["PTS"][0] is not None]
        index.append({"id": pid, "n": q["n"], "t": q["t"], "k": len(q["g"]), "p": len(played),
                      "fp": round(sum(pts) / len(pts), 1) if pts else 0})
    index.sort(key=lambda x: x["n"])
    dump(os.path.join(out, "data", key, "players.json"), index)

    status = None
    if cfg.get("status") and os.path.isfile(os.path.join(ROOT, cfg["status"])):
        with open(os.path.join(ROOT, cfg["status"]), encoding="utf-8") as f:
            e = json.load(f)
        status = {"date": e.get("fecha"), "ran": e.get("corrida"), "games": e.get("partidos_hoy"),
                  "next": e.get("siguiente"), "next_games": e.get("partidos_siguiente"),
                  "next_time": e.get("hora_siguiente"), "today_time": e.get("hora_hoy")}

    dates = sorted({g["date"] for g in games} | set(days), reverse=True)
    made = max((g["made"] for g in games if g["made"]), default="")

    folder = os.path.join(out, "data", key)
    os.makedirs(os.path.join(folder, "days"), exist_ok=True)
    dump(os.path.join(folder, "meta.json"), {
        "label": cfg["label"], "dates": dates, "latest": made, "games": games, "score": score,
        "versions": versions, "recal": recal, "status": status,
    })
    for d, players in days.items():
        dump(os.path.join(folder, "days", f"{d}.json"), {"date": d, "players": list(players.values())})
    print(f"  {key}: {len(dates)} days, {len(games)} games, {len(player_rows)} player rows, {len(people)} players")
    return True


def model_versions(path, used):
    """Model versions for the site, in English, from results/registro_modelos.json
    (written by the pipeline) plus the days each version was actually used."""
    reg = {}
    if path and os.path.isfile(os.path.join(ROOT, path)):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            reg = json.load(f)
    season = reg.get(max(reg, key=int)) if reg else {}
    listed = season.get("versiones") or [{"version": "v1", "features": 77}]
    out = []
    for v in listed:
        name = v["version"]
        feats = v.get("features") or (77 if name == "v1" else None)
        if v.get("descripcion_en"):
            text = v["descripcion_en"]
        elif v.get("protocolo") == "mensual":
            text = (f"Monthly retrain with this season's games through {v.get('datos_hasta')}. "
                    f"It made {abs(v.get('cambio_vs_anterior_pct', 0)):.1f}% less error than the "
                    f"previous version on two weeks neither model had seen, so it replaced it.")
        else:
            text = ("Start-of-season model: trained on the 8 seasons before last season, "
                    "with its 80% ranges calibrated on last season.")
        if feats and not v.get("descripcion_en"):
            text += f" {feats} features."
        first, last = used.get(name, (None, None))
        out.append({"v": name, "from": first, "to": last, "text": text,
                    "active": name == season.get("activo", "v1")})
    active = season.get("activo", "v1")
    recs = [r for r in season.get("recalibraciones", []) if r["version"] == active]
    recal = None
    if recs:
        r = max(recs, key=lambda r: r["desde"])
        recal = {"from": r["desde"], "rows": r["filas"], "count": len(recs)}
    return out, recal


def code_version():
    """Short hash of everything the browser caches between deploys (pages, partials, css, js)."""
    h = hashlib.sha256()
    for folder, _, names in sorted(os.walk(WEB)):
        if "__pycache__" in folder or os.sep + "fonts" in folder:
            continue
        for n in sorted(names):
            if n.endswith((".html", ".css", ".js", ".svg")):
                with open(os.path.join(folder, n), "rb") as f:
                    h.update(n.encode() + f.read())
    return h.hexdigest()[:10]


def render_page(name):
    """A page with its <!-- include:NAME --> markers replaced by web/partials/NAME.html or NAME.svg."""
    def part(m):
        for ext in (".html", ".svg"):
            path = os.path.join(WEB, "partials", m.group(1) + ext)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return f.read().strip()
        raise SystemExit(f"{name}: no partial called {m.group(1)!r} in web/partials/")

    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        html = INCLUDE.sub(part, f.read())
    html = html.replace("{{SITE_URL}}", SITE_URL)
    if name != "index.html":  # mark the legal page being read in the shared footer
        html = html.replace(f'<a href="{name}">', f'<a href="{name}" aria-current="page">', 1)
    return html


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    out = os.path.abspath(ap.parse_args().out)

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    v = code_version()
    for page in PAGES:
        with open(os.path.join(out, page), "w", encoding="utf-8") as f:
            f.write(ASSET_REF.sub(rf"\1?v={v}\2", render_page(page)))
    for f in STATIC:
        shutil.copy2(os.path.join(WEB, f), os.path.join(out, f))
    for d in STATIC_DIRS:
        shutil.copytree(os.path.join(WEB, d), os.path.join(out, d))
    js = os.path.join(out, "js")
    for n in os.listdir(js):        # versioned imports between modules too
        p = os.path.join(js, n)
        with open(p, encoding="utf-8") as f:
            code = f.read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(JS_IMPORT.sub(rf"\1?v={v}\2", code))
    open(os.path.join(out, ".nojekyll"), "w").close()

    print(f"Building site in {out}")
    built = [k for k, cfg in DATASETS.items() if build_set(k, cfg, out)]
    dump(os.path.join(out, "data", "sets.json"), {
        "sets": [{"key": k, "label": DATASETS[k]["label"]} for k in built],
        "built": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
    })


if __name__ == "__main__":
    main()
