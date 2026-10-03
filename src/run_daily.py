"""Corre el pipeline completo del día, en orden, y publica los pronósticos.

Uso normal:   python src/run_daily.py
Prueba:       python src/run_daily.py --fecha 2026-10-20 --sin-push"""
import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

LOGS = Path("logs")
PASOS = ["src/ingest_live.py",   # partidos de anoche + calendario actualizado
         "src/rosters.py",       # plantillas de hoy
         "src/clean.py",
         "src/features.py",
         "src/team_features.py"]
ENTORNO = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def correr(args: list, log) -> int:
    log.write(f"\n=== {' '.join(args)} ({datetime.now():%H:%M:%S}) ===\n")
    log.flush()
    r = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, env=ENTORNO)
    return r.returncode


def hay_partidos(fecha: str) -> bool:
    cal = pd.read_parquet("data/raw/schedule_2026_27.parquet")
    hoy = cal["fecha"] == pd.Timestamp(fecha)
    return bool((hoy & cal["tipo"].isin(["regular", "playoffs", "playin"])).any())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--sin-push", action="store_true")
    args = ap.parse_args()

    LOGS.mkdir(exist_ok=True)
    ruta_log = LOGS / f"run_{args.fecha}.log"
    inicio = datetime.now()

    with open(ruta_log, "a", encoding="utf-8") as log:
        for paso in PASOS:
            if correr([sys.executable, paso], log) != 0:
                print(f"FALLÓ {paso}. Revisa {ruta_log}")
                sys.exit(1)
            print(f"OK  {paso}")

        if hay_partidos(args.fecha):
            if correr([sys.executable, "src/predict.py", "--fecha", args.fecha], log) != 0:
                print(f"FALLÓ predict.py. Revisa {ruta_log}")
                sys.exit(1)
            print("OK  src/predict.py")
        else:
            print(f"No hay partidos el {args.fecha}.")

        # El marcador corre siempre: evalúa los partidos ya jugados
        if any(Path("predictions").glob("????-??-??.csv")):
            if correr([sys.executable, "src/score.py"], log) == 0:
                print("OK  src/score.py")
            else:
                print(f"FALLÓ score.py (los pronósticos sí se generaron). Revisa {ruta_log}")

        if not args.sin_push:
            correr(["git", "add", "predictions", "results"], log)
            if correr(["git", "commit", "-m", f"Pronósticos y marcador {args.fecha}"], log) == 0:
                correr(["git", "push"], log)
                print("OK  publicado en GitHub")

    print(f"Listo en {(datetime.now() - inicio).seconds // 60} min. Log: {ruta_log}")


if __name__ == "__main__":
    main()