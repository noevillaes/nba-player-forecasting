"""Nuevas versiones del modelo de jugadores, con control de calidad.

Mensual (lo llama run_daily.py; corre si pasaron 28 días desde el último intento):
  1. Retador: se entrena con las 8 temporadas previas + lo que va de esta
     temporada, excepto las últimas 2 semanas.
  2. Esas 2 semanas no las vio ninguno de los dos modelos: ahí se comparan el
     modelo activo (campeón) y el retador, estadística por estadística.
  3. El retador solo se activa si su error promedio es menor. Sus intervalos
     se calibran (conformal) con esas mismas 2 semanas.
  Requiere MIN_PARTIDOS de esta temporada para tener algo que aprender.

Inicio (--inicio): entrena una versión con el protocolo de inicio de temporada
(8 temporadas antes de la anterior, calibración en la anterior) y las
features actuales. Se usa cuando cambian las features, como en la v2.

Cada intento queda en results/reentrenos.csv y cada versión en
results/registro_modelos.json.

Uso:  python src/reentrenar.py              (mensual, respeta la cadencia)
      python src/reentrenar.py --forzar     (mensual, ya)
      python src/reentrenar.py --inicio --descripcion "..." """
import argparse
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import registro
from clean import temporada as temporada_de
from conformal import entrenar, predecir, NIVEL
from evaluate import cargar, solo_evaluables, OBJETIVOS
from models import columnas_features, VENTANA_TRAIN
from reconcile import factor_k

CADA_DIAS = 28
DIAS_VALIDACION = 14
MIN_PARTIDOS = 300          # ~20 partidos por equipo
LOG = Path("results/reentrenos.csv")


def entrenar_paquete(fit, calib, calib_todos, cols) -> dict:
    """Entrena los 48 modelos, calibra los intervalos en `calib` (jugaron) y
    la referencia de reconciliación en `calib_todos` (incluye DNP)."""
    paquete = {"cols": cols, "modelos": {}, "ajuste": {}}
    for obj in OBJETIVOS:
        mods = entrenar(fit, cols, obj)
        pc = predecir(mods, calib[cols], obj)
        y = calib[f"y_{obj}"]
        E = np.maximum(pc[f"{obj}_q10"] - y, y - pc[f"{obj}_q90"])
        paquete["modelos"][obj] = mods
        paquete["ajuste"][obj] = float(np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E)))))
        print(f"  {obj}: ajuste conformal {paquete['ajuste'][obj]:+.2f}")
    pc = predecir(paquete["modelos"]["points"], calib_todos[cols], "points")
    paquete["k_mediana"] = float(factor_k(calib_todos, pc["points"]).median())
    return paquete


def tablas(objetivo):
    """(todas las filas con historial, solo las evaluables) de las temporadas
    que se usan. Se carga una sola vez para no duplicar memoria."""
    todos = cargar()
    todos = todos[(todos["temporada"] >= objetivo - 1 - VENTANA_TRAIN) & todos["min_prom_10"].notna()]
    return todos, solo_evaluables(todos)


def registrar(reg, t, objetivo, paquete, descripcion, extra=None) -> str:
    v = registro.siguiente_version(t)
    archivo = f"modelo_{objetivo}_{v}.joblib"
    registro.MODELOS.mkdir(exist_ok=True)
    joblib.dump(paquete, registro.MODELOS / archivo)
    t["versiones"].append({"version": v, "archivo": archivo, "creada": registro.hoy(),
                           "descripcion": descripcion, "features": len(paquete["cols"]),
                           **(extra or {})})
    t["activo"] = v
    registro.guardar(reg)
    print(f"\nActiva desde el próximo pronóstico: {v} ({archivo})")
    return v


def inicio(objetivo, descripcion, descripcion_en=None):
    reg = registro.cargar()
    t = registro.temporada(reg, objetivo)
    todos, df = tablas(objetivo)
    fit = df[(df["temporada"] < objetivo - 1) & (df["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    calib = df[df["temporada"] == objetivo - 1]
    calib_todos = todos[todos["temporada"] == objetivo - 1]
    cols = columnas_features(fit)
    print(f"Entrenando con {len(fit):,} filas y {len(cols)} features "
          f"(calibración: temporada {objetivo - 1})")
    paquete = entrenar_paquete(fit, calib, calib_todos, cols)
    extra = {"protocolo": "inicio de temporada"}
    if descripcion_en:
        extra["descripcion_en"] = descripcion_en  # la que muestra el sitio web
    registrar(reg, t, objetivo, paquete, descripcion, extra)


def mensual(objetivo, hoy, forzar):
    reg = registro.cargar()
    t = registro.temporada(reg, objetivo)
    ultimo = t.get("ultimo_intento")
    if ultimo and not forzar and (hoy - pd.Timestamp(ultimo)).days < CADA_DIAS:
        print(f"Último intento de reentrenamiento: {ultimo}. Toca cada {CADA_DIAS} días.")
        return

    todos, df = tablas(objetivo)
    actual = df[df["temporada"] == objetivo]
    partidos = actual["gameId"].nunique()
    if partidos < MIN_PARTIDOS and not forzar:
        print(f"Reentrenamiento: {partidos} partidos de esta temporada; espera a {MIN_PARTIDOS}.")
        return

    corte = hoy - timedelta(days=DIAS_VALIDACION)
    val = actual[(actual["fecha"] >= corte) & (actual["fecha"] < hoy)]
    fit = df[(df["temporada"] >= objetivo - VENTANA_TRAIN)
             & ((df["temporada"] < objetivo) | (df["fecha"] < corte))]
    val_todos = todos[(todos["temporada"] == objetivo) & (todos["fecha"] >= corte)
                      & (todos["fecha"] < hoy)]
    print(f"Retador: {len(fit):,} filas hasta {corte.date()} | validación: {len(val):,} "
          f"jugadores-partido del {corte.date()} al {(hoy - timedelta(days=1)).date()}")

    version, ruta = registro.version_activa(objetivo)
    campeon = joblib.load(ruta)
    cols = columnas_features(fit)
    retador = entrenar_paquete(fit, val, val_todos, cols)

    filas = []
    for obj in OBJETIVOS:
        y = val[f"y_{obj}"]
        mae_c = (predecir(campeon["modelos"][obj], val[campeon["cols"]], obj)[obj] - y).abs().mean()
        mae_r = (predecir(retador["modelos"][obj], val[cols], obj)[obj] - y).abs().mean()
        filas.append({"fecha": hoy.strftime("%Y-%m-%d"), "campeon": version, "objetivo": obj,
                      "jugadores": len(y), "MAE_campeon": mae_c, "MAE_retador": mae_r,
                      "cambio_pct": (mae_r / mae_c - 1) * 100})
    res = pd.DataFrame(filas)
    cambio = res["cambio_pct"].mean()
    gana = cambio < 0
    res["promovido"] = gana
    print(res[["objetivo", "MAE_campeon", "MAE_retador", "cambio_pct"]].round(3).to_string(index=False))
    print(f"\nCambio promedio del error: {cambio:+.2f}% -> "
          f"{'el retador gana' if gana else 'se queda el modelo actual'}")

    res.round(4).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    t["ultimo_intento"] = hoy.strftime("%Y-%m-%d")
    if gana:
        registrar(reg, t, objetivo, retador,
                  f"Reentrenamiento mensual con datos hasta el {corte.date()}; "
                  f"{abs(cambio):.1f}% menos error que la {version} en las 2 semanas de validación.",
                  {"protocolo": "mensual", "datos_hasta": str(corte.date()),
                   "cambio_vs_anterior_pct": round(cambio, 2)})
    else:
        registro.guardar(reg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--descripcion", default="Modelo de inicio de temporada con las features actuales.")
    ap.add_argument("--descripcion-en", default=None, help="texto en inglés para el sitio web")
    args = ap.parse_args()
    hoy = pd.Timestamp(args.fecha)
    objetivo = int(temporada_de(pd.Series([hoy])).iloc[0])
    if args.inicio:
        inicio(objetivo, args.descripcion, args.descripcion_en)
    else:
        mensual(objetivo, hoy, args.forzar)


if __name__ == "__main__":
    main()
