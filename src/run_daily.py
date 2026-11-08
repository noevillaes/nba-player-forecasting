"""Corre el pipeline completo del día, en orden, y publica los pronósticos.

Uso normal:   python src/run_daily.py
Prueba:       python src/run_daily.py --fecha 2026-10-20 --sin-push"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
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


TIPOS = ["regular", "playoffs", "playin"]


def esperar_internet(log, espera=30, maximo=10 * 60) -> bool:
    """Al despertar, la laptop tarda en reconectar el Wi-Fi: reintenta cada 30 s hasta 10 min
    antes de rendirse, en vez de fallar con el primer error de DNS."""
    inicio = time.monotonic()
    intento = 0
    while True:
        intento += 1
        try:
            socket.create_connection(("stats.nba.com", 443), timeout=8).close()
            if intento > 1:
                log.write(f"Internet disponible tras {intento} intentos ({time.monotonic() - inicio:.0f} s)\n")
            return True
        except OSError as e:
            if time.monotonic() - inicio + espera > maximo:
                log.write(f"Sin internet tras {maximo // 60} min: {e}\n")
                return False
            msg = f"Sin internet (intento {intento}: {e}). Reintento en {espera} s."
            print(msg)
            log.write(msg + "\n")
            log.flush()
            time.sleep(espera)


def hay_partidos(fecha: str) -> bool:
    cal = pd.read_parquet("data/raw/schedule_2026_27.parquet")
    hoy = cal["fecha"] == pd.Timestamp(fecha)
    return bool((hoy & cal["tipo"].isin(TIPOS)).any())


def escribir_estado(fecha: str):
    """results/estado.json: qué encontró la corrida de hoy, para que el sitio explique los días sin partidos."""
    cal = pd.read_parquet("data/raw/schedule_2026_27.parquet")
    cal = cal[cal["tipo"].isin(TIPOS)]
    hoy = pd.Timestamp(fecha)
    despues = cal[cal["fecha"] > hoy]
    sig = despues["fecha"].min() if len(despues) else None
    def primer_salto(dia):
        """Hora del primer partido de ese día (el calendario viene en hora del Este, sin zona)."""
        h = cal.loc[cal["fecha"] == dia, "gameDateTimeEst"]
        if not len(h):
            return None
        return h.min().tz_localize("America/New_York").isoformat()

    estado = {
        "fecha": fecha,
        "corrida": datetime.now().astimezone().isoformat(timespec="minutes"),
        "partidos_hoy": int((cal["fecha"] == hoy).sum()),
        "hora_hoy": primer_salto(hoy),
        "siguiente": sig.date().isoformat() if sig is not None else None,
        "partidos_siguiente": int((cal["fecha"] == sig).sum()) if sig is not None else 0,
        "hora_siguiente": primer_salto(sig) if sig is not None else None,
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--sin-push", action="store_true")
    args = ap.parse_args()

    LOGS.mkdir(exist_ok=True)
    ruta_log = LOGS / f"run_{args.fecha}.log"
    inicio = datetime.now()

    with open(ruta_log, "a", encoding="utf-8") as log:
        if not esperar_internet(log):
            print(f"FALLÓ: sin internet después de 10 minutos. Revisa {ruta_log}")
            sys.exit(1)
        for paso in PASOS:
            if correr([sys.executable, paso], log) != 0:
                print(f"FALLÓ {paso}. Revisa {ruta_log}")
                sys.exit(1)
            print(f"OK  {paso}")

        # Cada semana: recalibra los intervalos con los errores en vivo
        if correr([sys.executable, "src/recalibrar.py", "--fecha", args.fecha], log) == 0:
            print("OK  src/recalibrar.py")
        else:
            print(f"FALLÓ recalibrar.py (se usan los intervalos de antes). Revisa {ruta_log}")

        if hay_partidos(args.fecha):
            if correr([sys.executable, "src/predict.py", "--fecha", args.fecha], log) != 0:
                print(f"FALLÓ predict.py. Revisa {ruta_log}")
                sys.exit(1)
            print("OK  src/predict.py")
        else:
            print(f"No hay partidos el {args.fecha}.")
        escribir_estado(args.fecha)

        # Momios de DraftKings, horarios y reporte de lesiones (ESPN). Si falla, el sitio sale sin ellos.
        if correr([sys.executable, "src/lineas.py", "--fecha", args.fecha], log) == 0:
            print("OK  src/lineas.py")
        else:
            print(f"FALLÓ lineas.py (los pronósticos sí se generaron). Revisa {ruta_log}")
        # Momios de varias casas (The Odds API); sin clave en .env se salta solo
        if correr([sys.executable, "src/casas.py"], log) == 0:
            print("OK  src/casas.py")
        else:
            print(f"FALLÓ casas.py (los pronósticos sí se generaron). Revisa {ruta_log}")

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

        # Cada mes: entrena un retador y lo activa solo si le gana al modelo actual.
        # Va después de publicar para no retrasar los pronósticos de hoy; si gana,
        # se usa desde mañana y el registro se sube con el commit de mañana.
        if correr([sys.executable, "src/reentrenar.py", "--fecha", args.fecha], log) == 0:
            print("OK  src/reentrenar.py")
        else:
            print(f"FALLÓ reentrenar.py (se sigue usando el modelo actual). Revisa {ruta_log}")

    print(f"Listo en {(datetime.now() - inicio).seconds // 60} min. Log: {ruta_log}")


if __name__ == "__main__":
    main()