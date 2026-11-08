"""Momios, horarios y reporte de lesiones, para comparar el modelo contra las casas de apuestas.

Cada mañana, desde run_daily.py:
  - las líneas de hoy como están antes de los partidos (captura "previa") y la hora de cada partido
  - las líneas de cierre de ayer, que ESPN conserva después del partido (captura "cierre")
  - el reporte de lesiones de hoy

Una sola vez, para llenar lo que va de la temporada:
    python src/lineas.py --desde 2026-10-20

Fuente: la API pública (no documentada) de ESPN. Las líneas son las de DraftKings.

Escribe:
    predictions/lineas.csv              una fila por partido (la de cierre reemplaza a la previa)
    predictions/lesiones_<fecha>.csv    el reporte de lesiones de ese día"""
import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
PRED = Path("predictions")
LINEAS = PRED / "lineas.csv"
COLUMNAS = ["fecha", "gameId", "espn_id", "local", "visitante", "hora_utc", "casa",
            "spread_local", "total", "ml_local", "ml_visita", "prob_local_casa", "captura", "actualizado"]
SESION = requests.Session()
SESION.headers["User-Agent"] = "nba-player-forecasting (personal project)"


def pedir(ruta: str, **params) -> dict:
    """GET a la API de ESPN con tres intentos."""
    for intento in range(3):
        try:
            r = SESION.get(f"{API}/{ruta}", params=params, timeout=25)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if intento == 2:
                raise
            print(f"  reintento {ruta} ({e})")
            time.sleep(3 * (intento + 1))


# ---------------------------------------------------------------- lectura de momios
def numero(x):
    """'+9.5' -> 9.5, 'o238.5' -> 238.5, 'EVEN' -> 100, None -> None"""
    if x is None or x == "":
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().lower().lstrip("ou")
    if s in ("even", "ev", "pk", "pick"):
        return 100.0 if s.startswith("ev") else 0.0
    try:
        return float(s.replace("+", ""))
    except ValueError:
        return None


def cerrada(d: dict | None, *ruta):
    """d['home']['close']['line'], tolerando que falte cualquier nivel."""
    for k in ruta:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def prob_implicita(ml):
    if ml is None:
        return None
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def leer_momio(o: dict, local_abrev: str) -> dict:
    """Spread del local, total y moneylines de una entrada 'odds' (scoreboard) o 'pickcenter' (summary)."""
    spread = numero(cerrada(o, "pointSpread", "home", "close", "line"))
    if spread is None and o.get("spread") is not None:
        spread = numero(o["spread"])                      # ESPN lo da desde el punto de vista del local
    if spread is None and o.get("details"):               # "PHI -9.5"
        partes = str(o["details"]).split()
        if len(partes) == 2 and numero(partes[1]) is not None:
            v = numero(partes[1])
            spread = v if partes[0] == local_abrev else -v
    total = numero(o.get("overUnder")) or numero(cerrada(o, "total", "over", "close", "line"))
    ml_l = numero(cerrada(o, "moneyline", "home", "close", "odds")) or numero(cerrada(o, "homeTeamOdds", "moneyLine"))
    ml_v = numero(cerrada(o, "moneyline", "away", "close", "odds")) or numero(cerrada(o, "awayTeamOdds", "moneyLine"))
    pl, pv = prob_implicita(ml_l), prob_implicita(ml_v)
    prob = round(pl / (pl + pv), 3) if pl and pv else None   # sin la comisión de la casa
    casa = cerrada(o, "provider", "name") or ""
    return {"casa": casa, "spread_local": spread, "total": total,
            "ml_local": ml_l, "ml_visita": ml_v, "prob_local_casa": prob}


def elegir(entradas: list) -> dict | None:
    """DraftKings si está; si no, la primera casa con spread o total."""
    entradas = [o for o in entradas or [] if isinstance(o, dict)]
    for o in entradas:
        if "draftkings" in str(cerrada(o, "provider", "name")).lower():
            return o
    return next((o for o in entradas if o.get("spread") is not None or o.get("overUnder") is not None), None)


# ---------------------------------------------------------------- partidos
def ids_nba(fecha: str) -> dict:
    """(local, visitante) -> gameId de la NBA, desde los pronósticos de ese día."""
    ruta = PRED / f"juegos_{fecha}.csv"
    if not ruta.exists():
        return {}
    j = pd.read_csv(ruta, dtype={"gameId": str})
    return {(r.local, r.visitante): r.gameId for r in j.itertuples()}


def partidos(fecha: str) -> list:
    """Partidos de ESPN de ese día (fecha del Este) con hora, equipos y, si ya los hay, momios."""
    d = pedir("scoreboard", dates=fecha.replace("-", ""))
    ids = ids_nba(fecha)
    salida = []
    for e in d.get("events", []):
        c = e["competitions"][0]
        eq = {t["homeAway"]: t["team"] for t in c["competitors"]}
        local, visita = eq["home"]["name"], eq["away"]["name"]
        salida.append({
            "fecha": fecha, "gameId": ids.get((local, visita), ""), "espn_id": e["id"],
            "local": local, "visitante": visita, "hora_utc": e.get("date", ""),
            "_abrev": eq["home"].get("abbreviation", ""), "_odds": c.get("odds"),
            "_terminado": c["status"]["type"].get("completed", False),
        })
    return salida


def con_momio(p: dict, entrada: dict | None, captura: str) -> dict | None:
    if not entrada:
        return None
    m = leer_momio(entrada, p["_abrev"])
    if m["spread_local"] is None and m["total"] is None:
        return None
    fila = {k: v for k, v in p.items() if not k.startswith("_")}
    return {**fila, **m, "captura": captura, "actualizado": datetime.now().isoformat(timespec="minutes")}


def previa(fecha: str) -> list:
    """Las líneas de hoy antes de los partidos (o solo la hora, si todavía no hay momios)."""
    filas = []
    for p in partidos(fecha):
        f = con_momio(p, elegir(p["_odds"]), "previa")
        filas.append(f or {**{k: v for k, v in p.items() if not k.startswith("_")}, "captura": "sin momios",
                           "actualizado": datetime.now().isoformat(timespec="minutes")})
    return filas


def cierre(fecha: str) -> list:
    """Las líneas de cierre de un día ya jugado, partido por partido."""
    filas = []
    for p in partidos(fecha):
        try:
            s = pedir("summary", event=p["espn_id"])
        except requests.RequestException as e:
            print(f"  sin resumen para {p['visitante']} en {p['local']}: {e}")
            continue
        f = con_momio(p, elegir(s.get("pickcenter")), "cierre")
        if f:
            filas.append(f)
        time.sleep(0.3)
    return filas


def guardar(filas: list):
    """Agrega o reemplaza por partido; una línea de cierre nunca se pisa con una previa."""
    if not filas:
        return
    todo = pd.DataFrame(filas).reindex(columns=COLUMNAS).astype({"gameId": str, "espn_id": str})
    if LINEAS.exists():
        viejo = pd.read_csv(LINEAS, dtype={"gameId": str, "espn_id": str})
        todo = pd.concat([viejo, todo], ignore_index=True)
    # por partido se queda la mejor captura (cierre > previa > sin momios) y, entre iguales, la más reciente
    todo["_p"] = todo["captura"].map({"cierre": 2, "previa": 1}).fillna(0)
    todo["_n"] = range(len(todo))
    todo = todo.sort_values(["_p", "_n"]).drop_duplicates("espn_id", keep="last")
    todo = todo.drop(columns=["_p", "_n"]).sort_values(["fecha", "hora_utc", "local"])
    todo["gameId"] = todo["gameId"].replace({"nan": ""})
    todo.to_csv(LINEAS, index=False)


# ---------------------------------------------------------------- lesiones
def lesiones(fecha: str):
    d = pedir("injuries")
    filas = []
    for equipo in d.get("injuries", []):
        for i in equipo.get("injuries", []):
            a = i.get("athlete") or {}
            det = i.get("details") or {}
            filas.append({
                "fecha": fecha, "jugador": a.get("displayName", ""),
                "equipo": cerrada(a, "team", "name") or "",
                "estado": i.get("status", ""), "tipo": det.get("type", ""),
                "regreso": det.get("returnDate", ""), "reportado": i.get("date", ""),
            })
    pd.DataFrame(filas).to_csv(PRED / f"lesiones_{fecha}.csv", index=False)
    print(f"  lesiones: {len(filas)} jugadores en el reporte")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--desde", help="llena las líneas de cierre desde esta fecha hasta ayer")
    args = ap.parse_args()
    hoy = date.fromisoformat(args.fecha)

    if args.desde:
        dia = date.fromisoformat(args.desde)
        while dia < hoy:
            filas = cierre(dia.isoformat())
            guardar(filas)
            print(f"{dia}: {len(filas)} líneas de cierre")
            dia += timedelta(days=1)

    ayer = (hoy - timedelta(days=1)).isoformat()
    guardar(cierre(ayer))
    print(f"OK  cierre de {ayer}")
    filas = previa(hoy.isoformat())
    guardar(filas)
    print(f"OK  {len(filas)} partidos hoy ({sum(f['captura'] == 'previa' for f in filas)} con momios)")
    try:
        lesiones(hoy.isoformat())
    except requests.RequestException as e:
        print(f"Sin reporte de lesiones: {e}")


if __name__ == "__main__":
    main()
