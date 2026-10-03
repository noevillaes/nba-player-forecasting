"""Marcador: compara los pronósticos publicados con lo que realmente pasó.

Genera dos archivos pensados para Power BI (formato largo):
  predictions/historial.csv    un renglón por jugador × partido × estadística
  results/marcador_diario.csv  métricas por día y estadística (modelo vs baseline)

Uso:     python src/score.py
Prueba:  python src/score.py --backtest   (usa los archivos *_backtest.csv)"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

from datos import leer
from clean import parsear_minutos
from evaluate import OBJETIVOS

NOMBRES = {"numMinutes": "Minutos", "points": "Puntos",
           "reboundsTotal": "Rebotes", "assists": "Asistencias",
           "threePointersMade": "Triples"}
COLS_ID = ["fecha", "gameId", "personId", "jugador", "equipo", "rival",
           "local", "estado", "ajuste_equipo"]


def cargar_pronosticos(backtest: bool) -> pd.DataFrame:
    patron = ("predictions/????-??-??_backtest.csv" if backtest
        else "predictions/????-??-??.csv")
    archivos = sorted(glob.glob(patron))
    if not archivos:
        raise SystemExit("No hay pronósticos que evaluar")
    pr = pd.concat([pd.read_csv(a) for a in archivos], ignore_index=True)
    pr["personId"] = pr["personId"].astype("int64")
    pr["gameId"] = pr["gameId"].astype("int64")
    print(f"{len(archivos)} días de pronósticos, {len(pr):,} jugadores-partido")
    return pr


def cargar_reales(game_ids: set) -> pd.DataFrame:
    ps = leer("PlayerStatistics")
    ps = ps[ps["gameId"].astype("int64").isin(game_ids)].copy()
    ps["personId"] = ps["personId"].astype("int64")
    ps["gameId"] = ps["gameId"].astype("int64")
    ps["numMinutes"] = parsear_minutos(ps["numMinutes"]).fillna(0)
    ps["jugo"] = ps["numMinutes"] > 0
    return ps[["personId", "gameId", "jugo"] + OBJETIVOS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    args = ap.parse_args()

    pr = cargar_pronosticos(args.backtest)
    reales = cargar_reales(set(pr["gameId"]))
    jugados = set(reales["gameId"])

    m = pr.merge(reales, on=["personId", "gameId"], how="left",
                 suffixes=("", "_real"))
    m["estado"] = np.where(~m["gameId"].isin(jugados), "Pendiente",
                           np.where(m["jugo"].fillna(False).astype(bool),
                                    "Jugó", "No jugó"))
    m["jugador"] = m["firstName"] + " " + m["lastName"]

    # Formato largo: un renglón por jugador × partido × estadística
    partes = []
    for obj in OBJETIVOS:
        d = m.reindex(columns=COLS_ID).copy()
        d["estadistica"] = NOMBRES[obj]
        d["pronostico"] = m[obj]
        d["q10"] = m[f"{obj}_q10"]
        d["q90"] = m[f"{obj}_q90"]
        d["baseline"] = m.get(f"{obj}_base")
        d["real"] = m[f"{obj}_real"].where(m["estado"] == "Jugó")
        d["error_abs"] = (d["pronostico"] - d["real"]).abs()
        d["error_abs_baseline"] = (d["baseline"] - d["real"]).abs()
        dentro = (d["real"] >= d["q10"]) & (d["real"] <= d["q90"])
        d["dentro_80"] = dentro.astype(float).where(d["real"].notna())  # 1/0
        partes.append(d)
    hist = pd.concat(partes, ignore_index=True)

    ev = hist[hist["estado"] == "Jugó"]
    diario = (ev.groupby(["fecha", "estadistica"])
                .agg(jugadores=("real", "size"),
                     MAE=("error_abs", "mean"),
                     MAE_baseline=("error_abs_baseline", "mean"),
                     cobertura_80=("dentro_80", "mean"))
                .reset_index())
    diario["mejora_pct"] = (1 - diario["MAE"] / diario["MAE_baseline"]) * 100

    sufijo = "_backtest" if args.backtest else ""
    os.makedirs("results", exist_ok=True)
    hist.round(3).to_csv(f"predictions/historial{sufijo}.csv", index=False)
    diario.round(3).to_csv(f"results/marcador{sufijo}.csv", index=False)

    print(f"Historial: {len(hist):,} renglones | "
          f"{hist['estado'].value_counts().to_dict()}")
    if len(ev):
        resumen = ev.groupby("estadistica").agg(
            MAE=("error_abs", "mean"), MAE_baseline=("error_abs_baseline", "mean"),
            cobertura_80=("dentro_80", "mean"))
        resumen["mejora_pct"] = (1 - resumen["MAE"] / resumen["MAE_baseline"]) * 100
        print("\nAcumulado:")
        print(resumen.round(3).to_string())


if __name__ == "__main__":
    main()