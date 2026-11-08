"""Momios de varias casas de apuestas (The Odds API), para comparar el modelo contra el mercado.

Cada corrida guarda una foto de las líneas de los partidos que no han empezado: spread, total y
moneyline de cada casa. El sitio usa, por casa y por partido, la última foto antes del salto inicial.

    python src/casas.py             # desde run_daily.py, en la mañana
    python src/casas.py --tarde     # opcional, más cerca de los partidos (ver abajo)

La clave va en la variable de entorno ODDS_API_KEY o en un archivo .env en la raíz del proyecto
(una línea:  ODDS_API_KEY=tu_clave). El .env está en .gitignore y nunca se sube a GitHub.
Sin clave, el script avisa y termina sin error.

Costo: cada corrida pide 3 mercados a un grupo de hasta 10 casas, que The Odds API cobra como
3 créditos. Una corrida al día son ~90 créditos al mes; dos, ~180 (el plan gratis trae 500).
Los días sin partidos no cuestan nada.

La foto de la tarde la corre run_casas_tarde.bat desde una tarea programada de Windows
(17:45 en Monterrey, antes de los partidos de las 7 p.m. del Este).

Props de jugadores (solo en la foto de la mañana): la línea de puntos de cada jugador en cada
casa, para medir el modelo contra ellas (src/props.py). Cuestan 1 crédito por partido, así que
solo se piden si después quedan más de RESERVA_PROPS créditos en el mes.

Escribe predictions/casas.csv (una fila por partido, casa y foto) y predictions/props.csv
(una fila por jugador, casa y foto)."""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from lineas import ids_nba, prob_implicita   # noqa: E402

API = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
# Casas de EE. UU. del plan gratis, más Pinnacle, la casa de referencia del mercado.
# Hasta 10 casas cuentan como una sola región: cambiar la lista no cambia el costo mientras sean 10 o menos.
CASAS = ["draftkings", "fanduel", "betmgm", "betrivers", "espnbet", "hardrockbet",
         "bovada", "betonlineag", "pinnacle"]
SALIDA = Path("predictions/casas.csv")
PROPS = Path("predictions/props.csv")
RESERVA_PROPS = 150
MERCADOS_PROPS = ["player_points"]
COLUMNAS = ["fecha", "gameId", "local", "visitante", "inicio_utc", "casa", "casa_nombre",
            "spread_local", "total", "ml_local", "ml_visita", "prob_local", "foto", "capturado"]
ESTE = ZoneInfo("America/New_York")


def clave() -> str | None:
    if os.environ.get("ODDS_API_KEY"):
        return os.environ["ODDS_API_KEY"].strip()
    env = Path(".env")
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("ODDS_API_KEY="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def apodo(nombre: str, apodos: set) -> str:
    """'Philadelphia 76ers' -> '76ers', 'Portland Trail Blazers' -> 'Trail Blazers' (como los nombra el pipeline)."""
    for a in sorted(apodos, key=len, reverse=True):
        if nombre.endswith(" " + a) or nombre == a:
            return a
    return nombre.split()[-1]


def leer_casa(b: dict, local: str, visita: str) -> dict:
    """Spread del local, total y moneylines de una casa."""
    m = {x["key"]: x for x in b.get("markets", [])}
    def precio(mercado, nombre, campo="price"):
        for o in m.get(mercado, {}).get("outcomes", []):
            if o.get("name") == nombre:
                return o.get(campo)
        return None
    ml_l, ml_v = precio("h2h", local), precio("h2h", visita)
    pl, pv = prob_implicita(ml_l), prob_implicita(ml_v)
    return {
        "spread_local": precio("spreads", local, "point"),
        "total": precio("totals", "Over", "point"),
        "ml_local": ml_l, "ml_visita": ml_v,
        "prob_local": round(pl / (pl + pv), 3) if pl and pv else None,   # sin la comisión de la casa
    }


def foto(etiqueta: str) -> list:
    k = clave()
    if not k:
        print("Sin ODDS_API_KEY (variable de entorno o .env): no se piden momios de otras casas.")
        return []
    r = requests.get(API, timeout=30, params={
        "apiKey": k, "bookmakers": ",".join(CASAS), "markets": "h2h,spreads,totals",
        "oddsFormat": "american", "dateFormat": "iso",
    })
    if r.status_code in (401, 429):
        print(f"The Odds API rechazó la consulta ({r.status_code}): {r.text[:200]}")
        return []
    r.raise_for_status()
    print(f"  créditos: usados {r.headers.get('x-requests-used')}, quedan {r.headers.get('x-requests-remaining')}")
    foto.restantes = int(r.headers.get("x-requests-remaining") or 0)
    hoy = datetime.now(ESTE).date()       # props solo de los partidos de hoy que no han empezado
    inicio = lambda e: datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
    foto.eventos = [e for e in r.json() if inicio(e) > datetime.now(timezone.utc) and inicio(e).astimezone(ESTE).date() == hoy]
    ahora = datetime.now(timezone.utc).isoformat(timespec="minutes")
    filas, ids_por_dia = [], {}
    for e in r.json():
        inicio = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if inicio <= datetime.now(timezone.utc):
            continue                                     # ya empezó: esa línea ya no es previa
        fecha = inicio.astimezone(ESTE).date().isoformat()
        ids = ids_por_dia.setdefault(fecha, ids_nba(fecha))
        apodos = {n for par in ids for n in par}
        local, visita = apodo(e["home_team"], apodos), apodo(e["away_team"], apodos)
        for b in e.get("bookmakers", []):
            filas.append({
                "fecha": fecha, "gameId": ids.get((local, visita), ""), "local": local, "visitante": visita,
                "inicio_utc": e["commence_time"], "casa": b["key"], "casa_nombre": b.get("title", b["key"]),
                **leer_casa(b, e["home_team"], e["away_team"]), "foto": etiqueta, "capturado": ahora,
            })
    return filas


def props(eventos: list, restantes: int) -> list:
    """Líneas de puntos por jugador de cada partido que no ha empezado."""
    k = clave()
    if not eventos or restantes - len(eventos) * len(MERCADOS_PROPS) < RESERVA_PROPS:
        print(f"  props: no se piden (quedan {restantes} créditos; la reserva es {RESERVA_PROPS})")
        return []
    ahora = datetime.now(timezone.utc).isoformat(timespec="minutes")
    filas = []
    for e in eventos:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{e['id']}/odds", timeout=30, params={
            "apiKey": k, "bookmakers": ",".join(CASAS), "markets": ",".join(MERCADOS_PROPS),
            "oddsFormat": "american", "dateFormat": "iso"})
        if r.status_code != 200:
            print(f"  props de {e['away_team']} en {e['home_team']}: {r.status_code}")
            continue
        fecha = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(ESTE).date().isoformat()
        for b in r.json().get("bookmakers", []):
            for m in b.get("markets", []):
                lados = {}
                for o in m.get("outcomes", []):
                    lados.setdefault((o.get("description"), o.get("point")), {})[o.get("name")] = o.get("price")
                for (jugador, linea), p in lados.items():
                    po, pu = prob_implicita(p.get("Over")), prob_implicita(p.get("Under"))
                    filas.append({"fecha": fecha, "inicio_utc": e["commence_time"], "local": e["home_team"],
                                  "visitante": e["away_team"], "jugador": jugador, "mercado": m["key"],
                                  "casa": b["key"], "linea": linea, "over": p.get("Over"), "under": p.get("Under"),
                                  "prob_over": round(po / (po + pu), 3) if po and pu else None, "capturado": ahora})
    print(f"  props: {len(filas)} líneas de {len({f['jugador'] for f in filas})} jugadores")
    return filas


def guardar_props(filas: list):
    if not filas:
        return
    nuevo = pd.DataFrame(filas)
    if PROPS.exists():
        nuevo = pd.concat([pd.read_csv(PROPS), nuevo], ignore_index=True)
    nuevo.drop_duplicates(["inicio_utc", "jugador", "mercado", "casa", "capturado"], keep="last").to_csv(PROPS, index=False)


def guardar(filas: list):
    if not filas:
        return
    nuevo = pd.DataFrame(filas).reindex(columns=COLUMNAS)
    if SALIDA.exists():
        nuevo = pd.concat([pd.read_csv(SALIDA, dtype={"gameId": str}), nuevo], ignore_index=True)
    nuevo = nuevo.drop_duplicates(["inicio_utc", "local", "casa", "capturado"], keep="last")
    nuevo.sort_values(["fecha", "inicio_utc", "local", "casa", "capturado"]).to_csv(SALIDA, index=False)


def main():
    os.chdir(Path(__file__).resolve().parent.parent)   # la tarea programada arranca en otra carpeta
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarde", action="store_true", help="marca la foto como de la tarde")
    args = ap.parse_args()
    try:
        filas = foto("tarde" if args.tarde else "mañana")
    except requests.RequestException as e:
        print(f"Sin momios de otras casas: {e}")
        return
    guardar(filas)
    if not args.tarde and filas:
        try:
            guardar_props(props(getattr(foto, "eventos", []), getattr(foto, "restantes", 0)))
        except requests.RequestException as e:
            print(f"Sin props: {e}")
    juegos = len({(f["inicio_utc"], f["local"]) for f in filas})
    print(f"OK  {len(filas)} líneas de {len({f['casa'] for f in filas})} casas para {juegos} partidos")


if __name__ == "__main__":
    main()
