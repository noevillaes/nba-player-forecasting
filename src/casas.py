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

Escribe predictions/casas.csv: una fila por partido, casa y foto."""
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
    juegos = len({(f["inicio_utc"], f["local"]) for f in filas})
    print(f"OK  {len(filas)} líneas de {len({f['casa'] for f in filas})} casas para {juegos} partidos")


if __name__ == "__main__":
    main()
