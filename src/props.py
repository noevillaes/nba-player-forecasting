"""El modelo contra las líneas de puntos de jugadores de las casas (predictions/props.csv).

Para cada jugador y partido ya jugado se toma, en cada casa, su última línea antes del salto, y
la mediana entre casas. Se compara:
  - error del modelo contra el error de la línea como pronóstico (la línea es la mediana del mercado)
  - el lado del modelo (over si pronostica más que la línea, under si menos): récord y rendimiento
    con el momio real del mejor precio disponible de ese lado, apostando 1 a cada uno
    (con momios de −110, hace falta acertar 52.4% para no perder)
  - lo mismo solo cuando el modelo se separa de la línea al menos 1.5 puntos

Es solo para medir: no se publica en el sitio.

Uso:  python src/props.py         -> results/props.csv (un renglón por fecha y en total)"""
from pathlib import Path

import numpy as np
import pandas as pd

from disponibilidad import clave

PROPS = Path("predictions/props.csv")
HIST = Path("predictions/historial.csv")
SALIDA = Path("results/props.csv")
UMBRAL = 1.5


def ganancia(momio: float) -> float:
    """Lo que gana una apuesta de 1 si acierta (momio americano)."""
    return momio / 100 if momio > 0 else 100 / -momio


def tabla() -> pd.DataFrame:
    p = pd.read_csv(PROPS)
    p = p[(p["mercado"] == "player_points") & p["linea"].notna()]
    p = p[pd.to_datetime(p["capturado"], utc=True) < pd.to_datetime(p["inicio_utc"], utc=True)]
    p = p.sort_values("capturado").groupby(["fecha", "jugador", "casa"]).last().reset_index()
    p["clave"] = p["jugador"].map(clave)
    m = p.groupby(["fecha", "clave"]).agg(linea=("linea", "median"), mejor_over=("over", "max"),
                                          mejor_under=("under", "max"), casas=("casa", "nunique")).reset_index()
    h = pd.read_csv(HIST)
    h = h[(h["estadistica"] == "PTS") & (h["estado"] == "Jugó")].copy()
    h["clave"] = h["jugador"].map(clave)
    return m.merge(h[["fecha", "clave", "jugador", "pronostico", "real"]], on=["fecha", "clave"])


def resumen(d: pd.DataFrame) -> dict:
    lado_over = d["pronostico"] > d["linea"]
    empate = d["pronostico"] == d["linea"]
    push = d["real"] == d["linea"]
    acierto = np.where(lado_over, d["real"] > d["linea"], d["real"] < d["linea"])
    momio = np.where(lado_over, d["mejor_over"], d["mejor_under"])
    valido = ~empate & ~push & pd.notna(momio)
    pago = np.where(acierto, [ganancia(x) if pd.notna(x) else np.nan for x in momio], -1.0)
    lejos = valido & ((d["pronostico"] - d["linea"]).abs() >= UMBRAL)
    return {
        "jugadores": len(d),
        "error_modelo": round(float((d["pronostico"] - d["real"]).abs().mean()), 3),
        "error_linea": round(float((d["linea"] - d["real"]).abs().mean()), 3),
        "apuestas": int(valido.sum()), "aciertos": int(acierto[valido].sum()),
        "pct_aciertos": round(float(acierto[valido].mean()), 3) if valido.any() else None,
        "rendimiento": round(float(pago[valido].mean()), 3) if valido.any() else None,
        f"apuestas_{UMBRAL}": int(lejos.sum()),
        f"pct_aciertos_{UMBRAL}": round(float(acierto[lejos].mean()), 3) if lejos.any() else None,
        f"rendimiento_{UMBRAL}": round(float(pago[lejos].mean()), 3) if lejos.any() else None,
    }


def main():
    if not PROPS.exists() or not HIST.exists():
        print("Todavía no hay props o historial para comparar.")
        return
    d = tabla()
    if d.empty:
        print("Ningún prop coincide todavía con un partido ya jugado.")
        return
    filas = [{"fecha": f, **resumen(g)} for f, g in d.groupby("fecha")]
    filas.append({"fecha": "total", **resumen(d)})
    out = pd.DataFrame(filas)
    SALIDA.parent.mkdir(exist_ok=True)
    out.to_csv(SALIDA, index=False)
    t = filas[-1]
    print(f"Props: {t['jugadores']} jugadores. Error: modelo {t['error_modelo']} vs línea {t['error_linea']}. "
          f"Lado del modelo: {t['aciertos']} de {t['apuestas']} ({t['pct_aciertos']}), rendimiento {t['rendimiento']} por apuesta")


if __name__ == "__main__":
    main()
