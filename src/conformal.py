"""Calibración conformal de los intervalos (Conformalized Quantile Regression).

Para pronosticar la temporada t:
  1. Se entrenan los cuantiles con temporadas anteriores a t-1.
  2. En la temporada t-1 (calibración, no vista) se mide cuánto se sale
     el valor real del intervalo: E = max(q10 - y, y - q90).
  3. Los intervalos de t se ajustan por el cuantil 80% de E.
Garantía: cobertura >= 80% si los datos son intercambiables entre temporadas."""
import os
import numpy as np
import pandas as pd
import lightgbm as lgb

from evaluate import datos_evaluables, walk_forward, OBJETIVOS, OUT
from models import columnas_features, PARAMS, CUANTILES, VENTANA_TRAIN

TEMPORADAS = range(2015, 2019)  # validación: aquí se ajusta todo
NIVEL = 0.80
_cache = {}


def entrenar(train, cols, obj):
    modelos = {}
    for alpha, sufijo in CUANTILES:
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **PARAMS)
        m.fit(train[cols], train[f"y_{obj}"])
        modelos[sufijo] = m
    return modelos


def predecir(modelos, X, obj):
    p = pd.DataFrame({obj + s: m.predict(X) for s, m in modelos.items()},
                     index=X.index)
    trio = np.sort(p[[f"{obj}_q10", obj, f"{obj}_q90"]].to_numpy(), axis=1)
    p[f"{obj}_q10"], p[obj], p[f"{obj}_q90"] = trio.T
    return p


def correr(train, test):
    """Entrena una sola vez por temporada y devuelve (crudo, conformal)."""
    t = test["temporada"].iloc[0]
    if t in _cache:
        return _cache[t]

    calib = train[train["temporada"] == t - 1]
    fit = train[(train["temporada"] < t - 1)
                & (train["temporada"] >= t - 1 - VENTANA_TRAIN)]
    cols = columnas_features(fit)

    crudo = pd.DataFrame(index=test.index)
    conf = pd.DataFrame(index=test.index)
    for obj in OBJETIVOS:
        mods = entrenar(fit, cols, obj)

        # Puntajes de no-conformidad en la temporada de calibración
        pc = predecir(mods, calib[cols], obj)
        y = calib[f"y_{obj}"]
        E = np.maximum(pc[f"{obj}_q10"] - y, y - pc[f"{obj}_q90"])
        n = len(E)
        q = np.quantile(E, min(1.0, NIVEL * (1 + 1 / n)))

        pt = predecir(mods, test[cols], obj)
        for c in pt.columns:
            crudo[c] = pt[c]
        conf[obj] = pt[obj]
        conf[f"{obj}_q10"] = (pt[f"{obj}_q10"] - q).clip(lower=0)
        conf[f"{obj}_q90"] = pt[f"{obj}_q90"] + q
        print(f"  {t} {obj}: ajuste conformal = {q:+.2f}")

    _cache[t] = (crudo, conf)
    return _cache[t]


def lgbm_crudo(train, test):
    return correr(train, test)[0]


def lgbm_conformal(train, test):
    return correr(train, test)[1]


def main():
    df = datos_evaluables()
    res = walk_forward(df, {"lgbm_crudo": lgbm_crudo,
                            "lgbm_conformal": lgbm_conformal}, TEMPORADAS)

    os.makedirs(OUT, exist_ok=True)
    res.to_csv(f"{OUT}/metricas_conformal.csv", index=False)

    print("\nCobertura del intervalo del 80% (validación 2015-2018):")
    print(res.pivot_table(index="objetivo", columns="modelo",
                          values="cobertura_80").round(3).to_string())
    print("\nAncho promedio del intervalo:")
    print(res.pivot_table(index="objetivo", columns="modelo",
                          values="ancho_80").round(2).to_string())


if __name__ == "__main__":
    main()