"""El modelo de jugadores como paquete: una sola interfaz para entrenar y pronosticar,
sea cual sea la versión guardada en models/*.joblib.

Dos tipos de paquete:
  "cuantiles"  (v1 y v2) por estadística, tres LightGBM de cuantiles (q10, q50, q90) y un
               ajuste conformal del intervalo.
  "nb"         (v3) los minutos siguen igual; las 15 estadísticas de conteo son una
               distribución completa: media (LightGBM Poisson) + binomial negativa
               recalibrada (ver distribucion.py). De ahí salen la mediana, el intervalo
               del 80%, la media y P(estadística > X).

Un paquete es un dict:
  tipo, cols, modelos{obj}, ajuste{obj}            (ajuste: conformal; en "nb" solo minutos)
  disp{obj}, recal{obj}                            (solo "nb": dispersión y mapa del PIT)
  k_mediana, k_mediana_<stat>, version_k           (referencias para reconciliar; reconcile.py)
"""
import numpy as np
import pandas as pd

import conformal
import distribucion as dist
from features import OBJETIVOS

MINUTOS = "numMinutes"
NIVELES = (0.1, 0.5, 0.9)


def es_nb(paq: dict) -> bool:
    return paq.get("tipo") == "nb"


def es_conteo(paq: dict, obj: str) -> bool:
    """True si esa estadística se pronostica con una distribución discreta completa."""
    return es_nb(paq) and obj != MINUTOS


# ---------------------------------------------------------------- entrenar
def _cuantiles_conformal(fit, calib, cols, obj) -> tuple:
    mods = conformal.entrenar(fit, cols, obj)
    pc = conformal.predecir(mods, calib[cols], obj)
    y = calib[f"y_{obj}"]
    E = np.maximum(pc[f"{obj}_q10"] - y, y - pc[f"{obj}_q90"])
    return mods, float(np.quantile(E, min(1.0, conformal.NIVEL * (1 + 1 / len(E)))))


def entrenar(fit: pd.DataFrame, calib: pd.DataFrame, cols: list, tipo: str = "nb",
             objetivos: list = OBJETIVOS) -> dict:
    """fit: filas de entrenamiento; calib: filas que el modelo no ve, para calibrar
    (intervalo conformal de los minutos; dispersión y PIT de los conteos)."""
    paq = {"tipo": tipo, "cols": cols, "modelos": {}, "ajuste": {}, "disp": {}, "recal": {}}
    for obj in objetivos:
        if tipo != "nb" or obj == MINUTOS:
            paq["modelos"][obj], paq["ajuste"][obj] = _cuantiles_conformal(fit, calib, cols, obj)
            print(f"  {obj}: ajuste conformal {paq['ajuste'][obj]:+.2f}")
            continue
        m = dist.entrenar_media(fit, cols, obj)
        yc, muc = calib[f"y_{obj}"].to_numpy(float), m.predict(calib[cols])
        paq["modelos"][obj] = {"media": m}
        paq["disp"][obj] = dist.ajustar_dispersion(yc, muc)
        paq["recal"][obj] = dist.ajustar_recalibracion(yc, muc, paq["disp"][obj])
        print(f"  {obj}: log r = {paq['disp'][obj][0]:+.2f} {paq['disp'][obj][1]:+.2f}·log mu")
    return paq


# ---------------------------------------------------------------- pronosticar
def cuantiles(paq: dict, obj: str, mu, recal=None) -> tuple:
    """(q10, q50, q90) de un conteo a partir de su media. recal: mapa del PIT que sustituye
    al del paquete (la recalibración semanal con datos en vivo)."""
    mu = np.asarray(mu, float)
    mapa = paq["recal"][obj] if recal is None else np.asarray(recal, float)
    return tuple(dist.cuantil(mu, paq["disp"][obj], q, mapa) for q in NIVELES)


def pronosticar(paq: dict, X: pd.DataFrame, obj: str) -> pd.DataFrame:
    """Columnas {obj}, {obj}_q10, {obj}_q90 y, en los conteos de un paquete "nb", {obj}_media."""
    X = X[paq["cols"]]
    if es_conteo(paq, obj):
        mu = paq["modelos"][obj]["media"].predict(X)
        lo, med, hi = cuantiles(paq, obj, mu)
        return pd.DataFrame({obj: med, f"{obj}_q10": lo, f"{obj}_q90": hi, f"{obj}_media": mu}, index=X.index)
    p = conformal.predecir(paq["modelos"][obj], X, obj)
    q = paq["ajuste"][obj]
    return pd.DataFrame({obj: p[obj], f"{obj}_q10": (p[f"{obj}_q10"] - q).clip(lower=0),
                         f"{obj}_q90": p[f"{obj}_q90"] + q}, index=X.index)


def central(paq: dict, X: pd.DataFrame, obj: str) -> pd.Series:
    """El pronóstico publicado (la mediana), para comparar versiones entre sí."""
    return pronosticar(paq, X, obj)[obj]


def para_sumar(paq: dict, X: pd.DataFrame, obj: str) -> pd.Series:
    """Lo que se suma para armar el total del equipo: la media si la hay (las medianas no
    se pueden sumar); si no, la mediana, como hacían la v1 y la v2."""
    p = pronosticar(paq, X, obj)
    return p[f"{obj}_media"] if f"{obj}_media" in p else p[obj]


def modelo_explicable(paq: dict, obj: str):
    """(modelo, en_log): el modelo central y si sus contribuciones están en escala logarítmica."""
    if es_conteo(paq, obj):
        return paq["modelos"][obj]["media"], True
    return paq["modelos"][obj][""], False


def parametros(paq: dict) -> dict:
    """Lo que el sitio necesita para dibujar la distribución de cada conteo a partir de su
    media: dispersión (a, b) y mapa del PIT. Sin modelos: cabe en un JSON chico."""
    if not es_nb(paq):
        return {}
    return {obj: {"a": round(paq["disp"][obj][0], 4), "b": round(paq["disp"][obj][1], 4),
                  "recal": [round(float(x), 4) for x in paq["recal"][obj]]}
            for obj in paq["disp"]}
