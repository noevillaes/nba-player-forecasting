"""Recalibración semanal de los intervalos del 80% con los errores en vivo.

Los intervalos se calibran al inicio con la temporada anterior. Si esta
temporada se comporta distinto (más o menos variable), la cobertura real se
aleja del 80%. Cada semana se repite la calibración conformal, ahora con los
pronósticos ya publicados de los últimos 28 días: son datos que el modelo no
vio, así que la garantía de cobertura se mantiene.

  E = max(q10 - y, y - q90)    sobre el intervalo SIN la recalibración anterior
  ajuste = cuantil 80% de E    (positivo ensancha, negativo angosta)

Solo usa pronósticos de la versión activa del modelo y necesita al menos
MIN_FILAS jugadores-partido; si no, deja todo como está.

Uso:  python src/recalibrar.py            (corre si pasó una semana)
      python src/recalibrar.py --forzar"""
import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

import registro
from clean import temporada as temporada_de
from conformal import NIVEL
from score import NOMBRES

HISTORIAL = "predictions/historial.csv"
VENTANA_DIAS = 28
CADA_DIAS = 7
MIN_FILAS = 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--fecha", default=date.today().isoformat())
    args = ap.parse_args()
    hoy = pd.Timestamp(args.fecha)
    objetivo = int(temporada_de(pd.Series([hoy])).iloc[0])

    reg = registro.cargar()
    t = registro.temporada(reg, objetivo)
    version = t["activo"]
    previas = [r for r in t["recalibraciones"] if r["version"] == version]
    if previas and not args.forzar:
        dias = (hoy - pd.Timestamp(max(r["desde"] for r in previas))).days
        if dias < CADA_DIAS:
            print(f"Última recalibración hace {dias} días; toca cada {CADA_DIAS}.")
            return

    try:
        h = pd.read_csv(HISTORIAL)
    except FileNotFoundError:
        print("Todavía no hay historial.")
        return
    h["modelo"] = h["modelo"].fillna("v1") if "modelo" in h else "v1"
    desde = (hoy - timedelta(days=VENTANA_DIAS)).strftime("%Y-%m-%d")
    h = h[(h["estado"] == "Jugó") & (h["modelo"] == version)
          & (h["fecha"] >= desde) & (h["fecha"] < hoy.strftime("%Y-%m-%d"))]
    n = h.groupby("estadistica").size().min() if len(h) else 0
    if n < MIN_FILAS:
        print(f"Recalibración: {n} jugadores-partido de la {version} en los últimos "
              f"{VENTANA_DIAS} días; hacen falta {MIN_FILAS}. Sin cambios.")
        return

    corto = {v: k for k, v in NOMBRES.items()}  # "PTS" -> "points"
    ajustes, filas = {}, []
    for est, d in h.groupby("estadistica"):
        obj = corto[est]
        # ajuste que tenía cada pronóstico cuando se publicó
        usado = d["fecha"].map(lambda f: registro.ajuste_vigente(t, version, f).get(obj, 0.0))
        y, lo, hi = d["real"], d["q10"], d["q90"]
        E = np.maximum(lo - y, y - hi) + usado          # error sin la recalibración previa
        q = float(np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E)))))
        ajustes[obj] = round(q, 3)
        filas.append({"estadistica": est, "jugadores": len(d),
                      "cobertura_actual": ((y >= lo) & (y <= hi)).mean(),
                      "ajuste_anterior": usado.iloc[-1], "ajuste_nuevo": q})

    t["recalibraciones"].append({"desde": hoy.strftime("%Y-%m-%d"), "version": version,
                                 "filas": int(n), "ajustes": ajustes})
    registro.guardar(reg)
    print(f"Recalibración de la {version} con {n} jugadores-partido "
          f"({desde} a {(hoy - timedelta(days=1)).date()}):")
    print(pd.DataFrame(filas).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
