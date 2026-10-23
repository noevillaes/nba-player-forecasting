#!/usr/bin/env python3
"""
Builds the static website.

Copies the page files in web/ to an output folder and turns the pipeline CSVs
into small JSON files the page loads on demand:

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
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
STATIC = ["index.html", "terms.html", "privacy.html", "style.css", "app.js", "favicon.svg"]
STATIC_DIRS = ["fonts"]

DATASETS = {
    "live": {
        "label": "Live 2026-27",
        "registry": "results/registro_modelos.json",
        "players": "predictions/historial.csv",
        "games": "predictions/historial_juegos.csv",
        "score": "results/marcador.csv",
    },
    "backtest": {
        "label": "Backtest, March 2026 (simulated)",
        "players": "predictions/historial_backtest.csv",
        "games": "predictions/historial_juegos_backtest.csv",
        "score": "results/marcador_backtest.csv",
    },
}

STATUS = {"Jugó": "played", "No jugó": "dnp", "Pendiente": "pending"}


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

    dates = sorted({g["date"] for g in games} | set(days), reverse=True)
    made = max((g["made"] for g in games if g["made"]), default="")

    folder = os.path.join(out, "data", key)
    os.makedirs(os.path.join(folder, "days"), exist_ok=True)
    dump(os.path.join(folder, "meta.json"), {
        "label": cfg["label"], "dates": dates, "latest": made, "games": games, "score": score,
        "versions": versions, "recal": recal,
    })
    for d, players in days.items():
        dump(os.path.join(folder, "days", f"{d}.json"), {"date": d, "players": list(players.values())})
    print(f"  {key}: {len(dates)} days, {len(games)} games, {len(player_rows)} player rows")
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
    for f in STATIC:
        shutil.copy2(os.path.join(WEB, f), os.path.join(out, f))
    for d in STATIC_DIRS:
        shutil.copytree(os.path.join(WEB, d), os.path.join(out, d))
    open(os.path.join(out, ".nojekyll"), "w").close()

    print(f"Building site in {out}")
    built = [k for k, cfg in DATASETS.items() if build_set(k, cfg, out)]
    dump(os.path.join(out, "data", "sets.json"), {
        "sets": [{"key": k, "label": DATASETS[k]["label"]} for k in built],
        "built": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
    })


if __name__ == "__main__":
    main()
