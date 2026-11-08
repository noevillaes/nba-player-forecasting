"""Mezcla el modelo con el mercado de apuestas.

Partidos:   margen, total y probabilidad = peso × modelo + (1 − peso) × mercado
            (la probabilidad se mezcla en escala logit). Los pesos se eligen con los
            partidos ya jugados que tienen línea registrada.
Jugadores:  los puntos de cada jugador se escalan por (puntos del equipo mezclados /
            puntos del equipo del modelo)^λ, con λ elegido con los mismos partidos.

Ajuste diario (desde run_daily.py, antes de predict.py):
    python src/mezcla.py           -> results/mezcla.json

Los pesos se ajustan con líneas de la mañana (las que existen a la hora del pronóstico)
cuando ya hay al menos MIN_MANANA partidos con ellas; mientras tanto, con las de cierre de
DraftKings, que son más precisas y le dan un poco más de peso al mercado del que tendrá en la mañana.

predict.py llama a mezclar() con el mercado de cada partido de hoy: la mediana de las casas
(predictions/casas.csv) o, si no hay, la línea de DraftKings de la mañana (predictions/lineas.csv).
Un partido sin línea se queda con el modelo solo."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PRED = Path("predictions")
SALIDA = Path("results/mezcla.json")
MIN_MANANA = 60
LAMBDAS = [0, 0.25, 0.5, 0.75, 1.0]
logit = lambda p: np.log(p / (1 - p))
sigmoide = lambda z: 1 / (1 + np.exp(-z))


# ---------------------------------------------------------------- el mercado
def mercado_casas(fecha: str | None = None) -> pd.DataFrame:
    """Mediana entre casas de la última foto antes del salto, por partido."""
    ruta = PRED / "casas.csv"
    if not ruta.exists():
        return pd.DataFrame()
    c = pd.read_csv(ruta, dtype={"gameId": str})
    if fecha:
        c = c[c["fecha"] == fecha]
    c = c[pd.to_datetime(c["capturado"], utc=True) < pd.to_datetime(c["inicio_utc"], utc=True)]
    if c.empty:
        return pd.DataFrame()
    c = c.sort_values("capturado").groupby(["fecha", "local", "visitante", "casa"]).last().reset_index()
    m = c.groupby(["fecha", "local", "visitante"]).agg(
        spread_local=("spread_local", "median"), total=("total", "median"),
        prob_local=("prob_local", "mean"), casas=("casa", "nunique")).reset_index()
    m["fuente"] = m["casas"].map(lambda n: f"mediana de {n} casas")
    return m.drop(columns="casas")


def mercado_lineas(captura: str, fecha: str | None = None) -> pd.DataFrame:
    """DraftKings vía ESPN: 'previa' (la mañana del partido) o 'cierre'."""
    ruta = PRED / "lineas.csv"
    if not ruta.exists():
        return pd.DataFrame()
    l = pd.read_csv(ruta, dtype={"gameId": str})
    l = l[(l["captura"] == captura) & l["spread_local"].notna()]
    if fecha:
        l = l[l["fecha"] == fecha]
    l = l.rename(columns={"prob_local_casa": "prob_local"})
    l["fuente"] = f"DraftKings ({'mañana' if captura == 'previa' else 'cierre'})"
    return l[["fecha", "local", "visitante", "spread_local", "total", "prob_local", "fuente"]]


def mercado_de_hoy(fecha: str) -> pd.DataFrame:
    casas = mercado_casas(fecha)
    dk = mercado_lineas("previa", fecha)
    if casas.empty:
        return dk
    falta = dk.merge(casas[["local", "visitante"]], how="left", indicator=True)
    return pd.concat([casas, falta[falta["_merge"] == "left_only"].drop(columns="_merge")], ignore_index=True)


# ---------------------------------------------------------------- ajuste de pesos
def _pesos(d: pd.DataFrame) -> dict:
    w = {}
    for col, mk, real in [("spread", "m_margen", "margen_real"), ("total", "m_total", "real_total")]:
        x, y = d[col] - d[mk], d[real] - d[mk]
        w[col] = float(np.clip((x * y).sum() / (x * x).sum(), 0, 1)) if (x * x).sum() else 0.0
    con_p = d.dropna(subset=["m_prob"])
    rejilla = np.linspace(0, 1, 21)
    brier = [np.mean((sigmoide(a * logit(con_p["prob_local"].clip(.01, .99))
                               + (1 - a) * logit(con_p["m_prob"].clip(.01, .99))) - con_p["gano_local"]) ** 2)
             for a in rejilla]
    w["prob"] = float(rejilla[int(np.argmin(brier))]) if len(con_p) else 0.0
    return w


def _mezclar_filas(d: pd.DataFrame, w: dict) -> pd.DataFrame:
    o = d.copy()
    o["b_margen"] = o["m_margen"] + w["spread"] * (o["spread"] - o["m_margen"])
    o["b_total"] = o["m_total"] + w["total"] * (o["total"] - o["m_total"])
    return o


def ajustar():
    j = pd.read_csv(PRED / "historial_juegos.csv", dtype={"gameId": str})
    j = j[j["estado"] == "Jugado"]
    # lo que dijo el modelo solo (los archivos de antes de la mezcla no traen *_solo)
    for c in ["spread", "total", "prob_local", "pts_local", "pts_visita"]:
        if f"{c}_solo" in j:
            j[c] = j[f"{c}_solo"].fillna(j[c])
    manana = pd.concat([mercado_casas(), mercado_lineas("previa")], ignore_index=True) \
        .drop_duplicates(["fecha", "local", "visitante"])
    usar = "mañana"
    m = j.merge(manana, on=["fecha", "local", "visitante"], suffixes=("", "_m"))
    if len(m) < MIN_MANANA:
        usar = "cierre"
        m = j.merge(mercado_lineas("cierre"), on=["fecha", "local", "visitante"], suffixes=("", "_m"))
    if len(m) < 20:
        print(f"Solo {len(m)} partidos con línea: todavía no se mezcla.")
        return
    m = m.rename(columns={"spread_local": "m_spread", "total_m": "m_total", "prob_local_m": "m_prob"})
    m["m_margen"] = -m["m_spread"]
    w = _pesos(m)

    # jugadores: λ que más baja el error en puntos con el marcador mezclado del equipo
    o = _mezclar_filas(m, w)
    o["b_local"], o["b_visita"] = (o["b_total"] + o["b_margen"]) / 2, (o["b_total"] - o["b_margen"]) / 2
    h = pd.read_csv(PRED / "historial.csv", dtype={"gameId": str})
    h = h[(h["estadistica"] == "PTS") & (h["estado"] == "Jugó")]
    if "ajuste_mercado" in h:
        h["pronostico"] = h["pronostico"] / h["ajuste_mercado"].fillna(1.0)
    p = h.merge(o[["gameId", "pts_local", "pts_visita", "b_local", "b_visita"]], on="gameId")
    f = np.where(p["local"] == 1, p["b_local"] / p["pts_local"], p["b_visita"] / p["pts_visita"])
    errores = {lam: float(np.mean(np.abs(p["pronostico"] * f ** lam - p["real"]))) for lam in LAMBDAS}
    lam = min(errores, key=errores.get)

    res = {
        "ajustado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "lineas": usar, "partidos": int(len(m)), "jugadores": int(len(p)),
        "peso_modelo": {k: round(v, 3) for k, v in w.items()},
        "lambda_jugadores": lam, "mae_puntos_por_lambda": {str(k): round(v, 4) for k, v in errores.items()},
    }
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Mezcla con {len(m)} partidos (líneas de {usar}): peso del modelo "
          f"margen {w['spread']:.2f}, total {w['total']:.2f}, probabilidad {w['prob']:.2f}; λ jugadores {lam}")


# ---------------------------------------------------------------- aplicar hoy
def mezclar(juegos: pd.DataFrame, pred: pd.DataFrame, fecha: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (juegos, jugadores) mezclados. Guarda lo del modelo solo en columnas *_solo
    y el factor de cada jugador en ajuste_mercado."""
    pred = pred.copy()
    pred["ajuste_mercado"] = 1.0
    if not SALIDA.exists():
        print("Sin results/mezcla.json: se publica el modelo solo.")
        return juegos, pred
    cfg = json.loads(SALIDA.read_text(encoding="utf-8"))
    w, lam = cfg["peso_modelo"], cfg["lambda_jugadores"]
    mk = mercado_de_hoy(fecha)
    if mk.empty:
        mk = pd.DataFrame(columns=["fecha", "local", "visitante", "spread_local", "total", "prob_local", "fuente"])
    j = juegos.copy()
    for c in ["pts_local", "pts_visita", "total", "spread", "prob_local"]:
        j[f"{c}_solo"] = j[c]
    j = j.merge(mk.drop(columns="fecha"), on=["local", "visitante"], how="left", suffixes=("", "_m"))
    j = j.rename(columns={"spread_local": "mercado_spread_local", "total_m": "mercado_total",
                          "prob_local_m": "mercado_prob_local", "fuente": "mercado_fuente"})
    hay = j["mercado_spread_local"].notna() & j["mercado_total"].notna()
    margen = -j["mercado_spread_local"] + w["spread"] * (j["spread_solo"] + j["mercado_spread_local"])
    total = j["mercado_total"] + w["total"] * (j["total_solo"] - j["mercado_total"])
    local, visita = (total + margen) / 2, (total - margen) / 2
    for lado, nuevo in [("local", local), ("visita", visita)]:
        delta = (nuevo - j[f"pts_{lado}_solo"]).where(hay, 0)
        for c in [f"pts_{lado}", f"pts_{lado}_q10", f"pts_{lado}_q90"]:
            j[c] = (j[c] + delta).round(1)
    j["total"] = (j["pts_local"] + j["pts_visita"]).round(1)
    j["spread"] = (j["pts_local"] - j["pts_visita"]).round(1)
    con_p = hay & j["mercado_prob_local"].notna()
    p = sigmoide(w["prob"] * logit(j["prob_local_solo"].clip(.01, .99))
                 + (1 - w["prob"]) * logit(j["mercado_prob_local"].clip(.01, .99)))
    j["prob_local"] = p.where(con_p, j["prob_local_solo"]).round(3)

    # jugadores: siguen al marcador mezclado de su equipo
    fac = {}
    for r in j[hay].itertuples():
        fac[(int(r.gameId), 1)] = (r.pts_local / r.pts_local_solo) ** lam
        fac[(int(r.gameId), 0)] = (r.pts_visita / r.pts_visita_solo) ** lam
    llave = list(zip(pred["gameId"].astype("int64"), pred["local"].astype(float).astype(int)))
    pred["ajuste_mercado"] = [round(fac.get(k, 1.0), 3) for k in llave]
    for c in ["points", "points_q10", "points_q90"]:
        pred[c] = (pred[c] * pred["ajuste_mercado"]).round(1)
    print(f"Mezcla: {int(hay.sum())} de {len(j)} partidos con mercado; "
          f"peso del modelo margen {w['spread']:.2f}, total {w['total']:.2f}, prob {w['prob']:.2f}; λ {lam}")
    return j, pred


if __name__ == "__main__":
    ajustar()
