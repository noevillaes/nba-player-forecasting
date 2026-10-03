"""Reconciliación de los puntos individuales con el total del equipo.

Problema: el modelo pronostica a cada jugador por separado. Si un equipo
junta a varios anotadores (o pierde a uno), los pronósticos no "saben"
que se reparten (o heredan) los tiros.

Identidad: E[puntos del equipo] = Σ P(juega_i) · E[puntos_i | juega]
  1. T = ritmo esperado × eficiencia esperada / 100 (información previa)
  2. Suma de pronósticos ponderada por la probabilidad de jugar
     (proporción de partidos jugados en los últimos 10)
  3. k = T / suma; k relativo = k / mediana(k) en la temporada de calibración
     (a la suma siempre le faltan los jugadores sin historial)
  4. Pronóstico reconciliado = pronóstico × k_rel^λ, con λ elegido en
     validación. λ = 0 equivale a no reconciliar."""
import os
import numpy as np
import pandas as pd

from evaluate import cargar, OUT
from models import columnas_features, VENTANA_TRAIN
from conformal import entrenar, predecir, NIVEL

TEMPORADAS = range(2015, 2019)  # validación
LAMBDAS = [0, 0.25, 0.5, 0.75, 1.0]
OBJ = "points"


def total_esperado(d: pd.DataFrame) -> pd.Series:
    ritmo = (d["propio_pace_10"] + d["rival_pace_10"]) / 2
    eficiencia = (d["propio_ortg_10"] + d["rival_drtg_10"]) / 2
    return ritmo * eficiencia / 100


def factor_k(d: pd.DataFrame, pred: pd.Series) -> pd.Series:
    """k por fila (igual para todos los jugadores del mismo equipo-partido)."""
    aporte = d["jugo_prop_10"].fillna(0) * pred
    suma = aporte.groupby([d["gameId"], d["playerteamId"]]).transform("sum")
    return total_esperado(d) / suma.replace(0, np.nan)


def main():
    todo = cargar()
    df = todo[todo["min_prom_10"].notna()]  # con historial, incluye DNP
    filas, diag = [], []

    for t in TEMPORADAS:
        fit = df[(df["temporada"] < t - 1)
                 & (df["temporada"] >= t - 1 - VENTANA_TRAIN)
                 & (df["y_jugo"] == 1)]
        cols = columnas_features(fit)
        mods = entrenar(fit, cols, OBJ)

        calib = df[df["temporada"] == t - 1]
        test = df[df["temporada"] == t]
        pc = predecir(mods, calib[cols], OBJ)
        pt = predecir(mods, test[cols], OBJ)

        # Ajuste conformal con los que jugaron en calibración
        jc = calib["y_jugo"] == 1
        yc = calib.loc[jc, f"y_{OBJ}"]
        E = np.maximum(pc.loc[jc, f"{OBJ}_q10"] - yc, yc - pc.loc[jc, f"{OBJ}_q90"])
        q = np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E))))

        # Factor de reconciliación (solo información previa al partido)
        k_med = factor_k(calib, pc[OBJ]).median()
        k_rel = (factor_k(test, pt[OBJ]) / k_med).fillna(1.0).clip(0.5, 1.5)

        jt = test["y_jugo"] == 1
        y = test.loc[jt, f"y_{OBJ}"]
        atipico = (k_rel[jt] - 1).abs() > 0.10  # equipos muy cargados o mermados
        for lam in LAMBDAS:
            f = k_rel[jt] ** lam
            centro = pt.loc[jt, OBJ] * f
            lo = (pt.loc[jt, f"{OBJ}_q10"] - q).clip(lower=0) * f
            hi = (pt.loc[jt, f"{OBJ}_q90"] + q) * f
            err = centro - y
            filas.append({"temporada": t, "lambda": lam,
                          "MAE": err.abs().mean(),
                          "MAE_atipicos": err[atipico].abs().mean(),
                          "sesgo": err.mean(),
                          "cobertura_80": ((y >= lo) & (y <= hi)).mean()})

        # Diagnóstico: ¿qué tan bien estima T el total real del equipo?
        llave = ["gameId", "playerteamId"]
        real = todo[todo["temporada"] == t].groupby(llave)[f"y_{OBJ}"].sum()
        Tg = total_esperado(test).groupby([test["gameId"], test["playerteamId"]]).first()
        real = real.reindex(Tg.index)
        diag.append({"temporada": t,
                     "MAE_total_equipo": (Tg - real).abs().mean(),
                     "sesgo_total_equipo": (Tg - real).mean(),
                     "k_mediana_calib": k_med,
                     "pct_filas_atipicas": atipico.mean()})
        print(f"Temporada {t} evaluada")

    res = pd.DataFrame(filas)
    os.makedirs(OUT, exist_ok=True)
    res.to_csv(f"{OUT}/metricas_reconciliacion.csv", index=False)

    print("\nPuntos, validación 2015-2018 (λ = 0 es sin reconciliar):")
    print(res.groupby("lambda")[["MAE", "MAE_atipicos", "sesgo",
                                 "cobertura_80"]].mean().round(3).to_string())
    print("\nDiagnóstico del total de equipo:")
    print(pd.DataFrame(diag).round(3).to_string(index=False))


if __name__ == "__main__":
    main()