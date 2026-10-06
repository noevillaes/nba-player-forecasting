"""Marcador: compara los pronósticos publicados con lo que realmente pasó.

Genera archivos pensados para Power BI:
  predictions/historial.csv          jugador × partido × estadística (formato largo)
  results/marcador.csv               métricas por día y estadística
  predictions/historial_juegos.csv   un renglón por partido

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

NOMBRES = {"numMinutes": "MIN", "fieldGoalsMade": "FGM",
           "fieldGoalsAttempted": "FGA", "threePointersMade": "3PM",
           "threePointersAttempted": "3PA", "freeThrowsMade": "FTM",
           "freeThrowsAttempted": "FTA", "reboundsOffensive": "OREB",
           "reboundsDefensive": "DREB", "reboundsTotal": "REB",
           "assists": "AST", "steals": "STL", "blocks": "BLK",
           "turnovers": "TO", "foulsPersonal": "PF", "points": "PTS"}
ORDEN = {nombre: i for i, nombre in enumerate(NOMBRES.values())}
COLS_ID = ["fecha", "gameId", "personId", "jugador", "equipo", "rival",
           "local", "estado", "ajuste_equipo"]


def leer_archivos(patron: str) -> pd.DataFrame:
    archivos = sorted(glob.glob(patron))
    if not archivos:
        return pd.DataFrame()
    d = pd.concat([pd.read_csv(a) for a in archivos], ignore_index=True)
    d["gameId"] = d["gameId"].astype("int64")
    return d


# ---------- Jugadores ----------

def cargar_reales(game_ids: set) -> pd.DataFrame:
    ps = leer("PlayerStatistics")
    ps = ps[ps["gameId"].astype("int64").isin(game_ids)].copy()
    ps["personId"] = ps["personId"].astype("int64")
    ps["gameId"] = ps["gameId"].astype("int64")
    ps["numMinutes"] = parsear_minutos(ps["numMinutes"]).fillna(0)
    ps["jugo"] = ps["numMinutes"] > 0
    return ps[["personId", "gameId", "jugo"] + OBJETIVOS]


def marcador_jugadores(backtest: bool, sufijo: str):
    patron = ("predictions/????-??-??_backtest.csv" if backtest
              else "predictions/????-??-??.csv")
    pr = leer_archivos(patron)
    if pr.empty:
        print("No hay pronósticos de jugadores que evaluar")
        return
    pr["personId"] = pr["personId"].astype("int64")
    print(f"Jugadores: {pr['fecha'].nunique()} días, {len(pr):,} jugadores-partido")

    reales = cargar_reales(set(pr["gameId"]))
    jugados = set(reales["gameId"])
    m = pr.merge(reales, on=["personId", "gameId"], how="left", suffixes=("", "_real"))
    m["estado"] = np.where(~m["gameId"].isin(jugados), "Pendiente",
                           np.where(m["jugo"].fillna(False).astype(bool),
                                    "Jugó", "No jugó"))
    m["jugador"] = m["firstName"] + " " + m["lastName"]

    partes = []
    for obj in OBJETIVOS:
        d = m.reindex(columns=COLS_ID).copy()
        d["estadistica"] = NOMBRES[obj]
        d["orden"] = ORDEN[NOMBRES[obj]]
        d["pronostico"] = m[obj]
        d["q10"] = m[f"{obj}_q10"]
        d["q90"] = m[f"{obj}_q90"]
        d["baseline"] = m.get(f"{obj}_base")
        d["real"] = m[f"{obj}_real"].where(m["estado"] == "Jugó")
        d["error_abs"] = (d["pronostico"] - d["real"]).abs()
        d["error_abs_baseline"] = (d["baseline"] - d["real"]).abs()
        dentro = (d["real"] >= d["q10"]) & (d["real"] <= d["q90"])
        d["dentro_80"] = dentro.astype(float).where(d["real"].notna())
        partes.append(d)
    hist = pd.concat(partes, ignore_index=True)

    ev = hist[hist["estado"] == "Jugó"]
    diario = (ev.groupby(["fecha", "estadistica"])
                .agg(jugadores=("real", "size"), MAE=("error_abs", "mean"),
                     MAE_baseline=("error_abs_baseline", "mean"),
                     cobertura_80=("dentro_80", "mean"))
                .reset_index())
    diario["mejora_pct"] = (1 - diario["MAE"] / diario["MAE_baseline"]) * 100

    hist.round(3).to_csv(f"predictions/historial{sufijo}.csv", index=False)
    diario.round(3).to_csv(f"results/marcador{sufijo}.csv", index=False)

    if len(ev):
        resumen = ev.groupby("estadistica").agg(
            MAE=("error_abs", "mean"), MAE_baseline=("error_abs_baseline", "mean"),
            cobertura_80=("dentro_80", "mean"))
        resumen["mejora_pct"] = (1 - resumen["MAE"] / resumen["MAE_baseline"]) * 100
        print(resumen.round(3).to_string())


# ---------- Partidos ----------

def marcador_juegos(backtest: bool, sufijo: str):
    patron = ("predictions/juegos_????-??-??_backtest.csv" if backtest
              else "predictions/juegos_????-??-??.csv")
    j = leer_archivos(patron)
    if j.empty:
        print("No hay pronósticos de partidos que evaluar")
        return

    ts = leer("TeamStatistics", columns=["gameId", "teamId", "home", "teamScore"])
    ts = ts[ts["gameId"].astype("int64").isin(set(j["gameId"]))].copy()
    ts["gameId"] = ts["gameId"].astype("int64")
    ts = ts.drop_duplicates(["gameId", "home"])
    pts_local = ts[ts["home"] == 1].set_index("gameId")["teamScore"]
    pts_visita = ts[ts["home"] == 0].set_index("gameId")["teamScore"]

    j["real_local"] = j["gameId"].map(pts_local)
    j["real_visita"] = j["gameId"].map(pts_visita)
    jugado = j["real_local"].notna() & j["real_visita"].notna()
    j["estado"] = np.where(jugado, "Jugado", "Pendiente")
    j["real_total"] = j["real_local"] + j["real_visita"]
    j["margen_real"] = j["real_local"] - j["real_visita"]
    j["gano_local"] = (j["margen_real"] > 0).astype(float).where(jugado)
    j["error_total"] = (j["total"] - j["real_total"]).abs()
    j["error_spread"] = (j["spread"] - j["margen_real"]).abs()
    j["acierto_ganador"] = ((j["prob_local"] > 0.5).astype(float)
                            == j["gano_local"]).astype(float).where(jugado)
    j["brier"] = (j["prob_local"] - j["gano_local"]) ** 2
    for lado in ["local", "visita"]:
        dentro = ((j[f"real_{lado}"] >= j[f"pts_{lado}_q10"])
                  & (j[f"real_{lado}"] <= j[f"pts_{lado}_q90"]))
        j[f"dentro_80_{lado}"] = dentro.astype(float).where(jugado)

    j.round(3).to_csv(f"predictions/historial_juegos{sufijo}.csv", index=False)

    ev = j[jugado]
    print(f"\nPartidos: {len(j)} pronosticados, {len(ev)} jugados")
    if len(ev):
        err_pts = pd.concat([(ev["pts_local"] - ev["real_local"]).abs(),
                             (ev["pts_visita"] - ev["real_visita"]).abs()])
        cob = pd.concat([ev["dentro_80_local"], ev["dentro_80_visita"]])
        print(f"  MAE puntos por equipo: {err_pts.mean():.2f} | cobertura 80%: {cob.mean():.3f}")
        print(f"  MAE total: {ev['error_total'].mean():.2f} | "
              f"MAE diferencia: {ev['error_spread'].mean():.2f}")
        print(f"  Acierto ganador: {ev['acierto_ganador'].mean():.1%} | "
              f"Brier: {ev['brier'].mean():.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    args = ap.parse_args()
    sufijo = "_backtest" if args.backtest else ""
    os.makedirs("results", exist_ok=True)
    marcador_jugadores(args.backtest, sufijo)
    marcador_juegos(args.backtest, sufijo)


if __name__ == "__main__":
    main()