"""El modelo contra las líneas de puntos de jugadores de las casas (predictions/props.csv).

Es la medición interna de si los pronósticos tienen valor contra el mercado. No se publica
en el sitio.

Por jugador y partido ya jugado:
  línea       la que ofrecen más casas en la última foto antes del salto
  mercado     la probabilidad de over sin la comisión de la casa, promedio de las casas que
              ofrecen justo esa línea; los momios, el mejor precio de cada lado en esa línea
  modelo      P(puntos > línea) con la distribución de jugadores v3 en adelante (la media del
              historial y la forma guardada en results/distribucion.json). En versiones
              anteriores solo hay mediana: el lado es over si la mediana supera la línea.

Qué se mide, por fecha y en total (results/props.csv):
  error_modelo / error_linea     error absoluto de la mediana del modelo y de la línea
  brier_modelo / brier_mercado   qué tan buenas son las dos probabilidades de over (menor es mejor)
  lado del modelo                todas las líneas, apostando 1 al lado que el modelo ve más probable
  ventaja >= 5 y >= 10 puntos    solo donde la probabilidad del modelo se separa de la del mercado
  kelly                          cuánto habría crecido una banca apostando un cuarto de Kelly
                                 (tope 5% por apuesta) donde la ventaja es de 5 puntos o más
Con momios de -110 hace falta acertar 52.4% para no perder.

El detalle, una fila por jugador y partido, queda en results/props_detalle.csv.

Uso:  python src/props.py"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import distribucion
from disponibilidad import clave

PROPS = Path("predictions/props.csv")
HIST = Path("predictions/historial.csv")
DIST = Path("results/distribucion.json")
SALIDA = Path("results/props.csv")
DETALLE = Path("results/props_detalle.csv")
VENTAJAS = [0.05, 0.10]
KELLY, TOPE = 0.25, 0.05
EPS = 1e-9          # 0.6 - 0.5 no da exactamente 0.1


def ganancia(momio: float) -> float:
    """Lo que gana una apuesta de 1 si acierta (momio americano)."""
    return momio / 100 if momio > 0 else 100 / -momio


def mercado(p: pd.DataFrame) -> pd.DataFrame:
    """Una fila por fecha y jugador: línea, probabilidad de over sin comisión y mejores momios."""
    p = p[(p["mercado"] == "player_points") & p["linea"].notna()]
    p = p[pd.to_datetime(p["capturado"], utc=True) < pd.to_datetime(p["inicio_utc"], utc=True)]
    p = p.sort_values("capturado").groupby(["fecha", "jugador", "casa"]).last().reset_index()
    p["clave"] = p["jugador"].map(clave)
    # la línea del jugador: la que ofrecen más casas (en empate, la más cercana a la mediana).
    # Los precios solo se comparan entre casas con esa misma línea.
    p["lejos"] = (p["linea"] - p.groupby(["fecha", "clave"])["linea"].transform("median")).abs()
    n = p.groupby(["fecha", "clave", "linea"]).agg(casas=("casa", "nunique"), lejos=("lejos", "first")).reset_index()
    elegida = n.sort_values(["casas", "lejos"], ascending=[False, True]).drop_duplicates(["fecha", "clave"])
    en_linea = p.merge(elegida[["fecha", "clave", "linea"]], on=["fecha", "clave", "linea"])
    return en_linea.groupby(["fecha", "clave"]).agg(
        linea=("linea", "first"), prob_mercado=("prob_over", "mean"),
        mejor_over=("over", "max"), mejor_under=("under", "max"), casas=("casa", "nunique")).reset_index()


def tabla() -> pd.DataFrame:
    m = mercado(pd.read_csv(PROPS))
    h = pd.read_csv(HIST)
    h = h[(h["estadistica"] == "PTS") & (h["estado"] == "Jugó")].copy()
    h["clave"] = h["jugador"].map(clave)
    for c in ("media", "modelo"):
        if c not in h:
            h[c] = np.nan
    d = m.merge(h[["fecha", "clave", "jugador", "pronostico", "media", "modelo", "real"]], on=["fecha", "clave"])

    # P(over) del modelo, con la forma de la distribución de la versión que hizo cada pronóstico
    formas = json.loads(DIST.read_text(encoding="utf-8")) if DIST.exists() else {}
    d["prob_modelo"] = np.nan
    for version, g in d.groupby("modelo"):
        par = formas.get(version, {}).get("points")
        con = g["media"].notna()
        if par is None or not con.any():
            continue
        d.loc[g.index[con], "prob_modelo"] = distribucion.prob_mayor(
            g.loc[con, "media"].to_numpy(float), (par["a"], par["b"]), g.loc[con, "linea"].to_numpy(float),
            np.asarray(par["recal"], float))
    return apostar(d)


def apostar(d: pd.DataFrame) -> pd.DataFrame:
    """Agrega el lado del modelo, si acertó, lo que pagó y la ventaja sobre el mercado."""
    d = d.copy()
    con_prob = d["prob_modelo"].notna()
    d["lado"] = np.where(con_prob, np.where(d["prob_modelo"] > 0.5, "over", "under"),
                         np.where(d["pronostico"] > d["linea"], "over", "under"))
    d.loc[~con_prob & (d["pronostico"] == d["linea"]), "lado"] = None       # sin probabilidad y mediana = línea: sin lado
    d["empate"] = d["real"] == d["linea"]                                   # la apuesta se devuelve
    d["over_real"] = (d["real"] > d["linea"]).astype(float).where(~d["empate"])
    acierto = np.where(d["lado"] == "over", d["real"] > d["linea"], d["real"] < d["linea"])
    d["acierto"] = pd.Series(acierto, index=d.index).astype(float).where(d["lado"].notna() & ~d["empate"])
    momio = np.where(d["lado"] == "over", d["mejor_over"], d["mejor_under"])
    d["momio"] = pd.Series(momio, index=d.index).where(d["lado"].notna())
    paga = d["momio"].map(lambda x: ganancia(x) if pd.notna(x) else np.nan)
    d["pago"] = np.where(d["acierto"] == 1, paga, -1.0)
    d.loc[d["acierto"].isna() | d["momio"].isna(), "pago"] = np.nan
    # ventaja: probabilidad del modelo para su lado menos la del mercado para ese mismo lado
    p_mod = np.where(d["lado"] == "over", d["prob_modelo"], 1 - d["prob_modelo"])
    p_mer = np.where(d["lado"] == "over", d["prob_mercado"], 1 - d["prob_mercado"])
    d["prob_lado"], d["ventaja"] = p_mod, p_mod - p_mer
    return d


def kelly(d: pd.DataFrame, minimo: float = VENTAJAS[0]) -> float:
    """Banca final (empezando en 1) con un cuarto de Kelly donde la ventaja llega al mínimo."""
    banca = 1.0
    for _, dia in d[(d["ventaja"] >= minimo - EPS) & d["pago"].notna()].sort_values("fecha").groupby("fecha"):
        b = dia["momio"].map(ganancia)
        f = (KELLY * (dia["prob_lado"] * b - (1 - dia["prob_lado"])) / b).clip(0, TOPE)
        banca *= 1 + float((f * dia["pago"]).sum())       # las apuestas de un mismo día van a la vez
    return banca


def resumen(d: pd.DataFrame) -> dict:
    v = d[d["pago"].notna()]
    p = d[d["prob_modelo"].notna() & d["prob_mercado"].notna() & d["over_real"].notna()]
    r = {
        "jugadores": len(d),
        "error_modelo": round(float((d["pronostico"] - d["real"]).abs().mean()), 3),
        "error_linea": round(float((d["linea"] - d["real"]).abs().mean()), 3),
        "over_real": round(float(d["over_real"].mean()), 3),
        "brier_modelo": round(float(((p["prob_modelo"] - p["over_real"]) ** 2).mean()), 4) if len(p) else None,
        "brier_mercado": round(float(((p["prob_mercado"] - p["over_real"]) ** 2).mean()), 4) if len(p) else None,
        "apuestas": len(v), "aciertos": int(v["acierto"].sum()),
        "pct_aciertos": round(float(v["acierto"].mean()), 3) if len(v) else None,
        "rendimiento": round(float(v["pago"].mean()), 3) if len(v) else None,
    }
    for x in VENTAJAS:
        s = v[v["ventaja"] >= x - EPS]
        k = f"ventaja_{int(x * 100)}"
        r[f"apuestas_{k}"] = len(s)
        r[f"pct_aciertos_{k}"] = round(float(s["acierto"].mean()), 3) if len(s) else None
        r[f"rendimiento_{k}"] = round(float(s["pago"].mean()), 3) if len(s) else None
    r["kelly"] = round(kelly(d), 4)
    return r


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
    SALIDA.parent.mkdir(exist_ok=True)
    pd.DataFrame(filas).to_csv(SALIDA, index=False)
    cols = ["fecha", "jugador", "modelo", "linea", "casas", "pronostico", "media", "prob_modelo", "prob_mercado",
            "lado", "ventaja", "momio", "real", "acierto", "pago"]
    d[cols].round(4).sort_values(["fecha", "jugador"]).to_csv(DETALLE, index=False)
    t = filas[-1]
    print(f"Props: {t['jugadores']} jugadores. Error: modelo {t['error_modelo']} vs línea {t['error_linea']}. "
          f"Brier: modelo {t['brier_modelo']} vs mercado {t['brier_mercado']}. "
          f"Lado del modelo: {t['aciertos']} de {t['apuestas']} ({t['pct_aciertos']}), rendimiento {t['rendimiento']} por apuesta; "
          f"con ventaja de 5+: {t['apuestas_ventaja_5']} apuestas, rendimiento {t['rendimiento_ventaja_5']}")


if __name__ == "__main__":
    main()
