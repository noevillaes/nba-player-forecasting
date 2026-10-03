"""LightGBM con regresión por cuantiles (percentiles 10, 50 y 90),
evaluado con el mismo marco walk-forward que los baselines."""
import os
import numpy as np
import pandas as pd
import lightgbm as lgb

from evaluate import (datos_evaluables, walk_forward, prom_10_jugados,
                      OBJETIVOS, OUT)

TEMPORADAS = range(2019, 2026)  # 7 temporadas de prueba
VENTANA_TRAIN = 8               # temporadas previas usadas para entrenar
CUANTILES = [(0.1, "_q10"), (0.5, ""), (0.9, "_q90")]

NO_FEATURES = {"personId", "firstName", "lastName", "gameId", "fecha",
               "temporada", "tipo", "playerteamId", "opponentteamId"}

PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=63,
              min_child_samples=100, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1)


def columnas_features(df: pd.DataFrame) -> list:
    """Todo lo que no es identificador ni objetivo. Las columnas b1_
    (promedio de los últimos 10 jugados) sí entran: solo usan el pasado."""
    return [c for c in df.columns
            if c not in NO_FEATURES and not c.startswith("y_")]


def lgbm_cuantiles(train, test):
    t = test["temporada"].iloc[0]
    train = train[train["temporada"] >= t - VENTANA_TRAIN]
    cols = columnas_features(train)

    pred = pd.DataFrame(index=test.index)
    for obj in OBJETIVOS:
        for alpha, sufijo in CUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **PARAMS)
            m.fit(train[cols], train[f"y_{obj}"])
            pred[obj + sufijo] = m.predict(test[cols])

        # Los cuantiles se entrenan por separado y a veces se cruzan:
        # se ordenan para garantizar q10 <= q50 <= q90
        trio = np.sort(pred[[f"{obj}_q10", obj, f"{obj}_q90"]].to_numpy(), axis=1)
        pred[f"{obj}_q10"], pred[obj], pred[f"{obj}_q90"] = trio.T
    return pred


def main():
    df = datos_evaluables()
    modelos = {"prom_10_jugados": prom_10_jugados,
               "lgbm_cuantiles": lgbm_cuantiles}
    res = walk_forward(df, modelos, TEMPORADAS)

    os.makedirs(OUT, exist_ok=True)
    res.to_csv(f"{OUT}/metricas_lgbm.csv", index=False)

    mae = res.pivot_table(index="objetivo", columns="modelo", values="MAE")
    mae["mejora_%"] = (1 - mae["lgbm_cuantiles"] / mae["prom_10_jugados"]) * 100
    print("\nMAE promedio 2019-2025:")
    print(mae.round(2).to_string())

    cob = res[res["modelo"] == "lgbm_cuantiles"].groupby("objetivo")[
        ["cobertura_80", "ancho_80"]].mean()
    print("\nIntervalo del 80% (la cobertura ideal es 0.80):")
    print(cob.round(3).to_string())


if __name__ == "__main__":
    main()