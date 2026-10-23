"""¿Ayudan las features nuevas? Comparación walk-forward con el mismo
protocolo que producción: para pronosticar la temporada t se entrena con las
8 temporadas anteriores a t-1, se calibra en t-1 y se evalúa en t.

Variantes (mismas filas de prueba para todas):
  original   las 77 features de la v1
  + rol      + minutos de los últimos 3, tendencia, titular/jugó el último partido
  + largo    + producción por minuto en 82 partidos y suavizada

Uso:  python src/evaluate_features.py            (temporadas 2024 y 2025)
Salida: results/metricas_features.csv"""
import os
import sys
import numpy as np
import pandas as pd

import features
from conformal import entrenar, predecir, NIVEL
from evaluate import datos_evaluables, OBJETIVOS, OUT
from models import columnas_features, VENTANA_TRAIN

TEMPORADAS = [2024, 2025]


def variantes(cols_todas: list) -> dict:
    nuevas = set(features.ROL) | set(features.LARGO)
    original = [c for c in cols_todas if c not in nuevas]
    return {
        "original": original,
        "+ rol": original + features.ROL,
        "+ rol + largo": original + features.ROL + features.LARGO,
    }


def main():
    temporadas = [int(t) for t in sys.argv[1:]] or TEMPORADAS
    df = datos_evaluables()
    filas = []
    for t in temporadas:
        fit = df[(df["temporada"] < t - 1) & (df["temporada"] >= t - 1 - VENTANA_TRAIN)]
        calib = df[df["temporada"] == t - 1]
        test = df[df["temporada"] == t]
        print(f"\nTemporada {t}: {len(fit):,} para entrenar, {len(test):,} de prueba")
        for nombre, cols in variantes(columnas_features(fit)).items():
            for obj in OBJETIVOS:
                mods = entrenar(fit, cols, obj)
                pc = predecir(mods, calib[cols], obj)
                yc = calib[f"y_{obj}"]
                E = np.maximum(pc[f"{obj}_q10"] - yc, yc - pc[f"{obj}_q90"])
                q = np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E))))
                pt = predecir(mods, test[cols], obj)
                y = test[f"y_{obj}"]
                lo, hi = (pt[f"{obj}_q10"] - q).clip(lower=0), pt[f"{obj}_q90"] + q
                filas.append({
                    "temporada": t, "variante": nombre, "objetivo": obj, "n": len(y),
                    "features": len(cols),
                    "MAE": (pt[obj] - y).abs().mean(),
                    "MAE_prom10": (test[f"b1_{obj}"] - y).abs().mean(),
                    "cobertura_80": ((y >= lo) & (y <= hi)).mean(),
                    "ancho_80": (hi - lo).mean(),
                })
            r = pd.DataFrame(filas)
            r = r[(r["temporada"] == t) & (r["variante"] == nombre)]
            print(f"  {nombre:15s} ({len(cols)} features): MAE medio {r['MAE'].mean():.4f}")
            os.makedirs(OUT, exist_ok=True)
            pd.DataFrame(filas).to_csv(f"{OUT}/metricas_features.csv", index=False)

    res = pd.DataFrame(filas)
    tabla = res.pivot_table(index="objetivo", columns="variante", values="MAE")
    base = tabla["original"]
    for c in tabla.columns:
        if c != "original":
            tabla[f"cambio {c} %"] = (tabla[c] / base - 1) * 100
    print("\nMAE promedio de las temporadas de prueba (negativo = mejor que la original):")
    print(tabla.round(3).to_string())


if __name__ == "__main__":
    main()
