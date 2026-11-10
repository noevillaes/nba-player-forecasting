"""Modelo de partidos: puntos de cada equipo, total, diferencia y
probabilidad de victoria del local.

Versión 2 (nov 2026): rating de equipo que se actualiza partido a partido.
  Cada equipo tiene tres números: ataque y defensa (puntos por 100 posesiones contra el
  promedio de la liga) y ritmo. Antes de cada partido:
      eficiencia esperada = liga + ataque propio + defensa rival ± ventaja de local / 2
      puntos = ritmo esperado × eficiencia esperada / 100
  y después del partido cada rating se mueve una fracción K del error (como un Elo, pero en
  puntos por posesión). Entre temporadas los ratings regresan REGRESO hacia la media.
  Encima va un ajuste lineal por descanso (back-to-back propio y del rival).
  K, K_RITMO y REGRESO se eligieron en 2015-2018, antes de ver 2019 en adelante
  (python src/game_model.py --rejilla). La comparación queda en results/metricas_partidos_rating.csv.

  Contra la versión 1 (ritmo × eficiencia de los últimos 10 partidos + ausencias):
      2019-2025 (7 temporadas)  margen 11.24 -> 10.94 | total 15.10 -> 14.83 | Brier .2256 -> .2185  (mejor en las 7)
      2026-27 en vivo (146)     margen 12.42 -> 11.52 | total 15.34 -> 14.93 | Brier .2270 -> .2054
  El promedio de 10 partidos olvidaba demasiado rápido y sus márgenes salían comprimidos
  (desviación 4.7 puntos contra 7.4 del mercado); el rating usa toda la historia.

  Descartado: sumar el ajuste por ausencias encima del rating. En 2019-2025 ayudaba un pelo
  (margen 10.94 -> 10.92) pero en vivo empeoraba (11.52 -> 11.70), así que no entra.

Intervalo conformal para los puntos y probabilidad de victoria calibrada con regresión
logística sobre la diferencia (Platt scaling), igual que antes.

Validación:  python src/game_model.py            (versión 1 contra versión 2, 2019 a hoy)
             python src/game_model.py --rejilla  (elección de hiperparámetros, 2015-2018)"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression

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


def con_ausencias(d: pd.DataFrame, a: pd.DataFrame = None) -> pd.DataFrame:
    """Agrega aus_pts (puntos esperados de los ausentes del equipo) y opp_aus_pts (del rival).
    a: columnas gameId, teamId, aus_pts (de disponibilidad.por_equipo). Sin datos, cero."""
    d = d.drop(columns=[c for c in ("aus_pts", "opp_aus_pts") if c in d.columns])
    if a is None or a.empty:
        return d.assign(aus_pts=0.0, opp_aus_pts=0.0)
    a = a[["gameId", "teamId", "aus_pts"]]
    d = d.merge(a, on=["gameId", "teamId"], how="left").merge(
        a.rename(columns={"teamId": "opponentTeamId", "aus_pts": "opp_aus_pts"}),
        on=["gameId", "opponentTeamId"], how="left")
    d[["aus_pts", "opp_aus_pts"]] = d[["aus_pts", "opp_aus_pts"]].fillna(0.0)
    return d


def historico() -> pd.DataFrame:
    import disponibilidad
    from evaluate import FEAT
    t = tf.metricas_por_partido(tf.cargar_equipos())
    d = tabla_equipos(t, tf.ventanas_previas(t))
    # solo las columnas que hacen falta: la tabla completa ocupa varios GB en memoria
    jug = pd.read_parquet(FEAT, columns=["gameId", "playerteamId", "y_jugo", "min_prom_10", "points_pm_10"])
    d = con_ausencias(d, disponibilidad.por_equipo(jug))
    d = con_rating(d, t)
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


AUS = ["aus_pts", "opp_aus_pts"]
DESCANSO = ["propio_b2b_eq", "rival_b2b_eq"]
VERSION = 2            # sube cuando cambia el modelo: predict.py recalibra el paquete guardado
K, K_RITMO, REGRESO = 0.025, 0.10, 0.30
K_LIGA, K_LOCAL = 0.01, 0.005


class Rating:
    """Estado de los ratings. esperado() no modifica nada; actualizar() aprende de un partido jugado."""

    def __init__(self, k: float = K, k_ritmo: float = K_RITMO, regreso: float = REGRESO):
        self.k, self.k_ritmo, self.regreso = k, k_ritmo, regreso
        self.ataque, self.defensa, self.ritmo = {}, {}, {}
        self.liga, self.liga_ritmo, self.local = 108.0, 96.0, 2.5
        self.temporada = None

    def nueva_temporada(self, temporada):
        if self.temporada is not None and temporada != self.temporada:
            for r in (self.ataque, self.defensa, self.ritmo):
                for k in r:
                    r[k] *= 1 - self.regreso
        self.temporada = temporada

    def esperado(self, local: int, visita: int) -> tuple:
        """(eficiencia del local, eficiencia del visitante, ritmo) antes del partido."""
        e_l = self.liga + self.ataque.get(local, 0.0) + self.defensa.get(visita, 0.0) + self.local / 2
        e_v = self.liga + self.ataque.get(visita, 0.0) + self.defensa.get(local, 0.0) - self.local / 2
        return e_l, e_v, self.liga_ritmo + self.ritmo.get(local, 0.0) + self.ritmo.get(visita, 0.0)

    def actualizar(self, local, visita, ortg_l, ortg_v, ritmo):
        e_l, e_v, p = self.esperado(local, visita)
        for atq, dfn, err in ((local, visita, ortg_l - e_l), (visita, local, ortg_v - e_v)):
            self.ataque[atq] = self.ataque.get(atq, 0.0) + self.k * err
            self.defensa[dfn] = self.defensa.get(dfn, 0.0) + self.k * err
        for eq in (local, visita):
            self.ritmo[eq] = self.ritmo.get(eq, 0.0) + self.k_ritmo * (ritmo - p)
        self.liga += K_LIGA * ((ortg_l + ortg_v) / 2 - (e_l + e_v) / 2)
        self.liga_ritmo += K_LIGA * (ritmo - p)
        self.local += K_LOCAL * ((ortg_l - ortg_v) - (e_l - e_v))


def con_rating(d: pd.DataFrame, t: pd.DataFrame = None, **hiper) -> pd.DataFrame:
    """Agrega rating_pts: los puntos que el rating esperaba de cada equipo ANTES de ese partido.
    t: partidos jugados con pace y ortg (tf.metricas_por_partido); por defecto, todos.
    Las filas de d que no están en t (partidos por jugar) se pronostican con el estado final."""
    if t is None:
        t = tf.metricas_por_partido(tf.cargar_equipos())
    t = t[["gameId", "teamId", "home", "gameDateTimeEst", "pace", "ortg"]].dropna()
    loc, vis = t[t["home"] == 1].set_index("gameId"), t[t["home"] == 0].set_index("gameId")
    g = loc.join(vis, lsuffix="_l", rsuffix="_v", how="inner").sort_values("gameDateTimeEst_l")
    temporadas = temporada_de(g["gameDateTimeEst_l"]).to_numpy()

    r, previos = Rating(**hiper), {}
    for gid, l, v, ol, ov, p, temp in zip(g.index, g["teamId_l"], g["teamId_v"], g["ortg_l"],
                                          g["ortg_v"], g["pace_l"], temporadas):
        r.nueva_temporada(temp)
        e_l, e_v, ritmo = r.esperado(l, v)
        previos[(gid, l)], previos[(gid, v)] = ritmo * e_l / 100, ritmo * e_v / 100
        r.actualizar(l, v, ol, ov, p)

    d = d.copy()
    llaves = list(zip(d["gameId"].astype("int64"), d["teamId"].astype("int64")))
    d["rating_pts"] = [previos.get(k, np.nan) for k in llaves]
    falta = d["rating_pts"].isna()
    if falta.any():                       # partidos por jugar: el estado después del último jugado
        for temp in sorted(d.loc[falta, "temporada"].unique()):
            r.nueva_temporada(temp)
            m = falta & (d["temporada"] == temp)
            vals = []
            for eq, riv, es_local in zip(d.loc[m, "teamId"], d.loc[m, "opponentTeamId"], d.loc[m, "local"]):
                e_l, e_v, ritmo = r.esperado(eq, riv) if es_local else r.esperado(riv, eq)
                vals.append(ritmo * (e_l if es_local else e_v) / 100)
            d.loc[m, "rating_pts"] = vals
    return d


def puntos_formula(d: pd.DataFrame, paq: dict) -> pd.Series:
    """Versión 1: ritmo × eficiencia de los últimos 10 partidos ± local + ausencias."""
    h = paq["ventaja_local"] / 2
    p = d["total_formula"] + np.where(d["local"] == 1, h, -h)
    if "aus_coef" in paq and all(c in d.columns for c in AUS):
        a, b, c = paq["aus_coef"]
        p = p + a * d["aus_pts"] + b * d["opp_aus_pts"] + c
    return p


def puntos(d: pd.DataFrame, paq: dict) -> pd.Series:
    if paq.get("version", 1) < 2:
        return puntos_formula(d, paq)
    a, b, c = paq["descanso_coef"]
    p = d["rating_pts"] + a * d["propio_b2b_eq"].fillna(0) + b * d["rival_b2b_eq"].fillna(0) + c
    return p.fillna(puntos_formula(d, paq))        # un equipo sin rating: la fórmula de antes


def entrenar_paquete(d: pd.DataFrame, objetivo: int, version: int = VERSION) -> dict:
    """Ventaja de local con temporadas previas; intervalo y probabilidad
    calibrados en la temporada objetivo-1."""
    fit = d[(d["temporada"] < objetivo - 1)
            & (d["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    calib = d[d["temporada"] == objetivo - 1]

    paq = {"ventaja_local": float(fit.loc[fit["local"] == 1, OBJ].mean()
                                  - fit.loc[fit["local"] == 0, OBJ].mean())}
    if all(c in fit.columns for c in AUS):
        reg = LinearRegression().fit(fit[AUS], fit[OBJ] - puntos(fit, paq))
        paq["aus_coef"] = [float(reg.coef_[0]), float(reg.coef_[1]), float(reg.intercept_)]
    if version >= 2:
        con = fit[fit["rating_pts"].notna()]
        reg = LinearRegression().fit(con[DESCANSO].fillna(0), con[OBJ] - con["rating_pts"])
        paq["descanso_coef"] = [float(reg.coef_[0]), float(reg.coef_[1]), float(reg.intercept_)]
        paq["version"] = version
    pc = puntos(calib, paq)
    r = (calib[OBJ] - pc).abs()
    paq["ajuste"] = float(np.quantile(r, min(1.0, NIVEL * (1 + 1 / len(r)))))

    # la probabilidad se calibra con todas las temporadas de entrenamiento y la de calibración:
    # el rating de cada partido solo usa partidos anteriores, así que no hay fuga
    jc = a_partidos(pd.concat([fit, calib]), puntos(pd.concat([fit, calib]), paq)) if version >= 2 else a_partidos(calib, pc)
    paq["platt"] = LogisticRegression().fit(jc[["spread"]], jc["gano_local"])
    paq["tasa_local"] = float(a_partidos(fit, fit[OBJ])["gano_local"].mean())
    return paq


def pronosticar_partidos(d: pd.DataFrame, paq: dict) -> pd.DataFrame:
    c = puntos(d, paq)
    q = paq["ajuste"]
    j = a_partidos(d, c, c - q, c + q)
    j["prob_local"] = paq["platt"].predict_proba(j[["spread"]])[:, 1]
    return j


def validar(d: pd.DataFrame, temporadas, version: int) -> pd.DataFrame:
    filas = []
    for t in temporadas:
        if not (d["temporada"] == t).any():
            continue
        paq = entrenar_paquete(d, t, version)
        j = pronosticar_partidos(d[d["temporada"] == t], paq)
        reales = pd.concat([j["real_local"], j["real_visita"]])
        pred = pd.concat([j["pts_local"], j["pts_visita"]])
        lo = pd.concat([j["pts_q10_local"], j["pts_q10_visita"]])
        hi = pd.concat([j["pts_q90_local"], j["pts_q90_visita"]])
        g = j["gano_local"]
        filas.append({
            "version": version, "temporada": t, "partidos": len(j),
            "MAE_pts": (pred - reales).abs().mean(),
            "cobertura_80": ((reales >= lo) & (reales <= hi)).mean(),
            "MAE_total": (j["total"] - (j["real_local"] + j["real_visita"])).abs().mean(),
            "sesgo_total": (j["total"] - (j["real_local"] + j["real_visita"])).mean(),
            "MAE_spread": (j["spread"] - j["margen_real"]).abs().mean(),
            "acierto": ((j["prob_local"] > 0.5) == g).mean(),
            "brier": ((j["prob_local"] - g) ** 2).mean(),
            "brier_baseline": ((paq["tasa_local"] - g) ** 2).mean(),
            "desv_spread": j["spread"].std(),
        })
    return pd.DataFrame(filas)


def rejilla(d: pd.DataFrame, temporadas=TEMPORADAS):
    """Cómo se eligieron K, K_RITMO y REGRESO: validación 2015-2018, antes de ver 2019 en adelante."""
    import itertools
    t = tf.metricas_por_partido(tf.cargar_equipos())
    filas = []
    for k, kr, reg in itertools.product([0.02, 0.025, 0.03, 0.04, 0.06, 0.10], [0.05, 0.10, 0.15], [0.2, 0.3, 0.4]):
        r = validar(con_rating(d, t, k=k, k_ritmo=kr, regreso=reg), temporadas, 2)
        filas.append({"K": k, "K_RITMO": kr, "REGRESO": reg, "MAE_spread": r["MAE_spread"].mean(),
                      "MAE_total": r["MAE_total"].mean(), "brier": r["brier"].mean()})
    res = pd.DataFrame(filas)
    res["orden"] = res["MAE_spread"].rank() + res["MAE_total"].rank()
    print(f"Validación {temporadas[0]}-{temporadas[-1]}, mejores 8 (margen + total):")
    print(res.sort_values("orden").head(8).round(4).to_string(index=False))


def main():
    import sys
    d = historico()
    if "--rejilla" in sys.argv:
        return rejilla(d)
    prueba = range(2019, int(d["temporada"].max()) + 1)
    res = pd.concat([validar(d, prueba, 1), validar(d, prueba, 2)], ignore_index=True)
    res.round(4).to_csv("results/metricas_partidos_rating.csv", index=False)
    pd.set_option("display.width", 220)
    ultima = int(d["temporada"].max())
    print(f"Versión 1 (fórmula de 10 partidos) contra versión 2 (rating), {prueba[0]}-{ultima}:")
    print(res.pivot_table(index="temporada", columns="version",
                          values=["MAE_spread", "MAE_total", "brier", "cobertura_80"]).round(3).to_string())
    h = res[res["temporada"] < ultima].groupby("version")[["MAE_spread", "MAE_total", "brier", "acierto", "cobertura_80"]].mean()
    print(f"\nPromedio {prueba[0]}-{ultima - 1}:")
    print(h.round(4).to_string())


if __name__ == "__main__":
    main()
