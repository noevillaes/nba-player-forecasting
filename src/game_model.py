"""Modelo de partidos: puntos de cada equipo, total, diferencia y
probabilidad de victoria del local.

Decisión (validación 2015-2018, ver results/metricas_partidos.csv):
LightGBM no le ganó a una fórmula estructural, así que el pronóstico es
  puntos = ritmo esperado × eficiencia esperada / 100 ± ventaja de local / 2
con intervalo conformal y probabilidad de victoria calibrada con regresión
logística sobre la diferencia (Platt scaling).

Validación:  python src/game_model.py"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import team_features as tf
from clean import temporada as temporada_de
from conformal import NIVEL
from models import VENTANA_TRAIN

OBJ = "teamScore"
TEMPORADAS = range(2015, 2019)  # validación
FEATS_EQ = [f"{c}_{tf.N}" for c in tf.COLS] + ["dias_descanso_eq", "b2b_eq"]


def tabla_equipos(t: pd.DataFrame, eq: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo-partido con sus features y los del rival."""
    cols = ["gameId", "teamId", "opponentTeamId", "home", "gameDateTimeEst"]
    base = t[cols + ([OBJ] if OBJ in t.columns else [])].copy()
    for c in ["gameId", "teamId", "opponentTeamId"]:
        base[c] = base[c].astype("int64")
    eq = eq.copy()
    eq[["gameId", "teamId"]] = eq[["gameId", "teamId"]].astype("int64")

    propio = eq[["gameId", "teamId"] + FEATS_EQ].add_prefix("propio_").rename(
        columns={"propio_gameId": "gameId", "propio_teamId": "teamId"})
    rival = eq[["gameId", "teamId"] + FEATS_EQ].add_prefix("rival_").rename(
        columns={"rival_gameId": "gameId", "rival_teamId": "opponentTeamId"})
    d = (base.merge(propio, on=["gameId", "teamId"], how="left", validate="1:1")
             .merge(rival, on=["gameId", "opponentTeamId"], how="left", validate="1:1"))

    d["local"] = d["home"].astype(int)
    d["temporada"] = temporada_de(d["gameDateTimeEst"])
    ritmo = (d["propio_pace_10"] + d["rival_pace_10"]) / 2
    d["total_formula"] = ritmo * (d["propio_ortg_10"] + d["rival_drtg_10"]) / 2 / 100
    return d


def historico() -> pd.DataFrame:
    t = tf.metricas_por_partido(tf.cargar_equipos())
    d = tabla_equipos(t, tf.ventanas_previas(t))
    return d[d["propio_pace_10"].notna() & d["rival_pace_10"].notna()]


def a_partidos(d: pd.DataFrame, centro, lo=None, hi=None) -> pd.DataFrame:
    """De filas equipo-partido a una fila por partido (local vs visitante)."""
    x = d[["gameId", "teamId", "local", "gameDateTimeEst"]].copy()
    x["pts"] = centro
    if lo is not None:
        x["pts_q10"], x["pts_q90"] = lo, hi
    if OBJ in d.columns:
        x["real"] = d[OBJ]
    x = x[x.groupby("gameId")["local"].transform("sum") == 1]
    loc = x[x["local"] == 1].set_index("gameId")
    vis = x[x["local"] == 0].set_index("gameId")
    j = loc.join(vis, lsuffix="_local", rsuffix="_visita", how="inner")
    j["total"] = j["pts_local"] + j["pts_visita"]
    j["spread"] = j["pts_local"] - j["pts_visita"]
    if "real_local" in j.columns:
        j["margen_real"] = j["real_local"] - j["real_visita"]
        j["gano_local"] = (j["margen_real"] > 0).astype(int)
    return j.reset_index()


def puntos(d: pd.DataFrame, paq: dict) -> pd.Series:
    h = paq["ventaja_local"] / 2
    return d["total_formula"] + np.where(d["local"] == 1, h, -h)


def entrenar_paquete(d: pd.DataFrame, objetivo: int) -> dict:
    """Ventaja de local con temporadas previas; intervalo y probabilidad
    calibrados en la temporada objetivo-1."""
    fit = d[(d["temporada"] < objetivo - 1)
            & (d["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    calib = d[d["temporada"] == objetivo - 1]

    paq = {"ventaja_local": float(fit.loc[fit["local"] == 1, OBJ].mean()
                                  - fit.loc[fit["local"] == 0, OBJ].mean())}
    pc = puntos(calib, paq)
    r = (calib[OBJ] - pc).abs()
    paq["ajuste"] = float(np.quantile(r, min(1.0, NIVEL * (1 + 1 / len(r)))))

    jc = a_partidos(calib, pc)
    paq["platt"] = LogisticRegression().fit(jc[["spread"]], jc["gano_local"])
    paq["tasa_local"] = float(a_partidos(fit, fit[OBJ])["gano_local"].mean())
    return paq


def pronosticar_partidos(d: pd.DataFrame, paq: dict) -> pd.DataFrame:
    c = puntos(d, paq)
    q = paq["ajuste"]
    j = a_partidos(d, c, c - q, c + q)
    j["prob_local"] = paq["platt"].predict_proba(j[["spread"]])[:, 1]
    return j


def main():
    d = historico()
    filas, todos = [], []
    for t in TEMPORADAS:
        paq = entrenar_paquete(d, t)
        j = pronosticar_partidos(d[d["temporada"] == t], paq)
        reales = pd.concat([j["real_local"], j["real_visita"]])
        pred = pd.concat([j["pts_local"], j["pts_visita"]])
        lo = pd.concat([j["pts_q10_local"], j["pts_q10_visita"]])
        hi = pd.concat([j["pts_q90_local"], j["pts_q90_visita"]])
        g = j["gano_local"]
        filas.append({
            "temporada": t, "partidos": len(j),
            "ventaja_local": paq["ventaja_local"],
            "MAE_pts": (pred - reales).abs().mean(),
            "cobertura_80": ((reales >= lo) & (reales <= hi)).mean(),
            "MAE_total": (j["total"] - (j["real_local"] + j["real_visita"])).abs().mean(),
            "MAE_spread": (j["spread"] - j["margen_real"]).abs().mean(),
            "acierto": ((j["prob_local"] > 0.5) == g).mean(),
            "brier": ((j["prob_local"] - g) ** 2).mean(),
            "brier_baseline": ((paq["tasa_local"] - g) ** 2).mean(),
        })
        todos.append(j[["prob_local", "gano_local"]])

    res = pd.DataFrame(filas)
    res.to_csv("results/metricas_partidos_formula.csv", index=False)
    pd.set_option("display.width", 200)
    print("Partidos con la fórmula, validación 2015-2018:")
    print(res.round(3).to_string(index=False))

    todos = pd.concat(todos)
    todos["rango"] = pd.cut(todos["prob_local"], [0, .2, .35, .5, .65, .8, 1])
    cal = todos.groupby("rango", observed=True).agg(
        partidos=("gano_local", "size"),
        prob_media=("prob_local", "mean"),
        gano_local_real=("gano_local", "mean"))
    print("\nCalibración de la probabilidad:")
    print(cal.round(3).to_string())


if __name__ == "__main__":
    main()