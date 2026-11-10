"""Banco de pruebas: una sola forma de medir cualquier cambio del modelo de jugadores.

Dos canchas, siempre las dos (lo que mejora en el histórico puede no mejorar en vivo):
  2025   temporada 2025-26 completa. Se entrena con las 8 temporadas anteriores a 2024-25
         y se calibra en 2024-25.
  vivo   temporada 2026-27 hasta hoy. Se entrena con las 8 anteriores a 2025-26 y se calibra
         en 2025-26 (el protocolo de inicio de temporada del modelo publicado).

Métricas por estadística, sobre los jugadores que jugaron:
  MAE          error absoluto de la mediana
  sesgo        mediana - real (negativo = subestima)
  pinball      pérdida de cuantiles promedio en q10, q50 y q90 (compara cualquier modelo)
  cob_80       cobertura del intervalo q10-q90 (ideal 0.80), con fallas abajo/arriba por separado
  ancho_80     ancho promedio del intervalo
  CRPS, PIT    solo para modelos que dan la distribución completa (rejilla de cuantiles)
Y los mismos números en cortes: minutos proyectados (titulares vs banca) y partidos sin jugar.

Un modelo es una función  f(fit, calib, test, cols) -> DataFrame  con, por estadística, las
columnas {obj}, {obj}_q10, {obj}_q90 y, opcionalmente, {obj}_q{05..95} y {obj}_media.

Uso:
    python src/banco.py                     # el modelo publicado (v2) en las dos canchas
    python src/banco.py --objetivos points numMinutes
Desde otro script:
    import banco; banco.comparar({"v2": banco.modelo_v2, "nuevo": mi_modelo})
"""
import argparse
import os
import time

import numpy as np
import pandas as pd

from conformal import entrenar, predecir, NIVEL
from evaluate import cargar, solo_evaluables, OBJETIVOS
from models import columnas_features, VENTANA_TRAIN

OUT = "results"
CANCHAS = {"2025": 2025, "vivo": 2026}
REJILLA = [round(q, 2) for q in np.arange(0.05, 0.96, 0.05)]     # 19 cuantiles: 0.05 ... 0.95
_tabla = None


# ---------------------------------------------------------------- datos
def tabla() -> pd.DataFrame:
    """Todas las filas con historial (incluye los que no jugaron). Se carga una sola vez."""
    global _tabla
    if _tabla is None:
        t = cargar()
        _tabla = t[t["temporada"] >= min(CANCHAS.values()) - 1 - VENTANA_TRAIN].copy()
        # cortes que no dependen del modelo que se esté probando
        _tabla["corte_sin_jugar_5"] = (1 - _tabla["y_jugo"]).groupby(_tabla["personId"]).transform(
            lambda s: s.shift(1).rolling(5, min_periods=1).sum())
    return _tabla


def partes(objetivo: int, hasta: str = None) -> tuple:
    """(fit, calib, test) con las filas evaluables del protocolo de inicio de temporada."""
    df = solo_evaluables(tabla())
    fit = df[(df["temporada"] < objetivo - 1) & (df["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    calib = df[df["temporada"] == objetivo - 1]
    test = df[df["temporada"] == objetivo]
    if hasta:
        test = test[test["fecha"] < hasta]
    return fit, calib, test


# ---------------------------------------------------------------- métricas
def pinball(y, q, a):
    d = y - q
    return np.maximum(a * d, (a - 1) * d)


def crps_rejilla(y: np.ndarray, Q: np.ndarray, niveles: list) -> np.ndarray:
    """CRPS aproximado como 2 x promedio de la pérdida de cuantiles en la rejilla."""
    a = np.asarray(niveles)[None, :]
    return 2 * pinball(y[:, None], Q, a).mean(axis=1)


def pit_rejilla(y: np.ndarray, Q: np.ndarray, niveles: list, rng) -> np.ndarray:
    """PIT aleatorizado (los conteos empatan mucho con los cuantiles): uniforme entre
    F(y-) y F(y), con F interpolada en la rejilla."""
    niv = np.concatenate([[0.0], niveles, [1.0]])
    pit = np.empty(len(y))
    for i in range(len(y)):
        q = np.concatenate([[min(Q[i, 0], 0) - 1e-9], Q[i], [max(Q[i, -1], y[i]) + 1e-9]])
        hi = np.interp(y[i], q, niv)                    # F(y)
        lo = np.interp(y[i] - 1, q, niv) if float(y[i]).is_integer() else hi   # F(y-1) en conteos
        pit[i] = rng.uniform(min(lo, hi), hi)
    return pit


def medir(test: pd.DataFrame, pred: pd.DataFrame, objetivos: list, corte: pd.Series = None) -> pd.DataFrame:
    filas = []
    rng = np.random.default_rng(0)
    grupos = [("todos", pd.Series(True, index=test.index))] if corte is None else \
        [(k, corte == k) for k in corte.dropna().unique()]
    for nombre, m in grupos:
        t, p = test[m], pred[m]
        for obj in objetivos:
            y = t[f"y_{obj}"].to_numpy(float)
            c, lo, hi = (p[k].to_numpy(float) for k in (obj, f"{obj}_q10", f"{obj}_q90"))
            f = {"corte": nombre, "objetivo": obj, "n": len(y),
                 "MAE": np.abs(c - y).mean(), "sesgo": (c - y).mean(),
                 "MAE_base": np.abs(t[f"b1_{obj}"].to_numpy(float) - y).mean(),
                 "pinball": (pinball(y, lo, .1) + pinball(y, c, .5) + pinball(y, hi, .9)).mean() / 3,
                 "cob_80": ((y >= lo) & (y <= hi)).mean(),
                 "bajo": (y < lo).mean(), "sobre": (y > hi).mean(),
                 "ancho_80": (hi - lo).mean()}
            cols = [f"{obj}_q{int(round(q * 100)):02d}" for q in REJILLA]
            if all(k in p for k in cols):
                Q = p[cols].to_numpy(float)
                f["CRPS"] = crps_rejilla(y, Q, REJILLA).mean()
                pit = pit_rejilla(y, Q, REJILLA, rng)
                # qué tan lejos está el PIT de ser uniforme: desviación máxima en 10 cajones (0 = perfecto)
                f["PIT_desv"] = np.abs(np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit) - 0.1).max()
            if f"{obj}_media" in p:
                f["MAE_media"] = np.abs(p[f"{obj}_media"].to_numpy(float) - y).mean()
                f["sesgo_media"] = (p[f"{obj}_media"].to_numpy(float) - y).mean()
            filas.append(f)
    return pd.DataFrame(filas)


def cortes(test: pd.DataFrame) -> dict:
    """Los cortes del diagnóstico de nov 2026: dónde gana y dónde no gana el modelo."""
    mins = test["min_prom_10"]
    return {
        "minutos": pd.cut(mins, [-1, 15, 25, 60], labels=["banca (<15)", "rotación (15-25)", "titulares (25+)"]).astype(str),
        "sin_jugar": np.select([test["corte_sin_jugar_5"] == 0, test["corte_sin_jugar_5"] <= 2],
                               ["0 de 5 sin jugar", "1-2 sin jugar"], "3+ sin jugar"),
    }


# ---------------------------------------------------------------- el modelo publicado
def modelo_v2(fit, calib, test, cols, objetivos=OBJETIVOS) -> pd.DataFrame:
    """LightGBM por cuantiles (q10, q50, q90) + ajuste conformal en la temporada de calibración.
    Igual que conformal.py / reentrenar.inicio: es lo que corre en vivo, sin reconciliar."""
    out = pd.DataFrame(index=test.index)
    for obj in objetivos:
        mods = entrenar(fit, cols, obj)
        pc = predecir(mods, calib[cols], obj)
        y = calib[f"y_{obj}"]
        E = np.maximum(pc[f"{obj}_q10"] - y, y - pc[f"{obj}_q90"])
        q = float(np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E)))))
        pt = predecir(mods, test[cols], obj)
        out[obj] = pt[obj]
        out[f"{obj}_q10"] = (pt[f"{obj}_q10"] - q).clip(lower=0)
        out[f"{obj}_q90"] = pt[f"{obj}_q90"] + q
    return out


def desde_paquete(ruta: str):
    """Un modelo ya entrenado (models/*.joblib) como función del banco: no vuelve a entrenar."""
    import joblib
    paq = joblib.load(ruta)

    def f(fit, calib, test, cols, objetivos=OBJETIVOS):
        out = pd.DataFrame(index=test.index)
        for obj in objetivos:
            pt = predecir(paq["modelos"][obj], test[paq["cols"]], obj)
            q = paq["ajuste"][obj]
            out[obj] = pt[obj]
            out[f"{obj}_q10"] = (pt[f"{obj}_q10"] - q).clip(lower=0)
            out[f"{obj}_q90"] = pt[f"{obj}_q90"] + q
        return out
    return f


# ---------------------------------------------------------------- comparar
def comparar(modelos: dict, objetivos: list = None, canchas: list = None, guardar: str = None,
             hasta_vivo: str = None) -> pd.DataFrame:
    """Corre cada modelo en cada cancha y devuelve una fila por cancha, modelo, corte y estadística.
    modelos: {nombre: función}  o  {nombre: {"2025": función, "vivo": función}}."""
    objetivos = objetivos or OBJETIVOS
    res = []
    for cancha in canchas or list(CANCHAS):
        fit, calib, test = partes(CANCHAS[cancha], hasta_vivo if cancha == "vivo" else None)
        cols = columnas_features(fit)
        cols = [c for c in cols if not c.startswith("corte_")]      # los cortes no son features
        print(f"\n[{cancha}] entrena {len(fit):,} | calibra {len(calib):,} | prueba {len(test):,} | {len(cols)} features")
        for nombre, fn in modelos.items():
            fn = fn[cancha] if isinstance(fn, dict) else fn
            t0 = time.time()
            pred = fn(fit, calib, test, cols, objetivos)
            partes_res = [medir(test, pred, objetivos).assign(tipo_corte="todos")]
            for tipo, c in cortes(test).items():
                partes_res.append(medir(test, pred, objetivos, pd.Series(c, index=test.index)).assign(tipo_corte=tipo))
            r = pd.concat(partes_res).assign(cancha=cancha, modelo=nombre)
            res.append(r)
            print(f"  {nombre}: {time.time() - t0:.0f} s")
    res = pd.concat(res, ignore_index=True)
    res["mejora_vs_base_pct"] = (1 - res["MAE"] / res["MAE_base"]) * 100
    if guardar:
        os.makedirs(OUT, exist_ok=True)
        res.round(4).to_csv(f"{OUT}/{guardar}", index=False)
    return res


def resumen(res: pd.DataFrame, metricas=("MAE", "pinball", "cob_80")) -> None:
    pd.set_option("display.width", 250)
    t = res[res["tipo_corte"] == "todos"]
    for m in metricas:
        if m in t:
            print(f"\n{m}:")
            print(t.pivot_table(index="objetivo", columns=["cancha", "modelo"], values=m, sort=False).round(3).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objetivos", nargs="*", default=None)
    ap.add_argument("--canchas", nargs="*", default=None)
    args = ap.parse_args()
    res = comparar({"v2": modelo_v2}, args.objetivos, args.canchas, guardar="banco_v2.csv")
    resumen(res)
    t = res[(res["tipo_corte"] != "todos") & res["objetivo"].isin(["points", "numMinutes", "reboundsTotal", "assists"])]
    print("\nMejora contra el promedio de 10 partidos (%), por corte:")
    print(t.pivot_table(index=["tipo_corte", "corte"], columns=["cancha", "objetivo"], values="mejora_vs_base_pct").round(1).to_string())


if __name__ == "__main__":
    main()
