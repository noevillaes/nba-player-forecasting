"""Experimento: ¿ayuda saber qué compañeros de rotación faltan? (ADR-0009, propuesto)

No forma parte del pipeline diario. Mide cuánto valdría la información de ausencias y qué pasa
cuando lo que el modelo ve al pronosticar no se parece a lo que vio al entrenar.

Todo se define con partidos jugados y el calendario del equipo, sin depender de filas de 0 minutos:
  jugador de rotación   antes de un partido: jugó 5+ de los últimos 10 partidos del equipo y
                        promedió 15+ minutos en ellos
  aus_*                 los de rotación que no juegan hoy. En el histórico se sabe después del
                        partido; en vivo saldría del reporte de lesiones y de la plantilla
  ausc_*                solo las ausencias que continúan: tampoco jugó el partido anterior del equipo
  prev_*                los de rotación que no jugaron el partido anterior, sin mirar hoy

Variantes (todas sobre jugadores v4, en las dos canchas):
  v4+aus        entrena y pronostica con información perfecta de quién falta hoy (el techo)
  v4+aus>cont   el mismo modelo, pero al pronosticar solo conoce las ausencias que continúan
  v4+ausc       entrena y pronostica solo con las que continúan
  v4+prev       sin mirar hoy

Uso:  python src/ausencias.py        -> results/banco_ausencias.csv  (tarda ~20 min)"""
import numpy as np
import pandas as pd

import banco
import paquete as paquetes
import team_features as tf
from models import columnas_features

STATS = {"min": "numMinutes", "pts": "points", "reb": "reboundsTotal", "ast": "assists"}
OBJETIVOS = list(STATS.values())
PARTIDOS, MINIMO_JUGADOS, MINIMO_MINUTOS = 10, 5, 15
AUS = ["aus_n", "aus_min", "aus_pts", "aus_reb", "aus_ast", "prev_min", "prev_pts", "aus_min_riv", "aus_pts_riv"]
AUSC = ["ausc_n", "ausc_min", "ausc_pts", "ausc_reb", "ausc_ast", "prev_min", "prev_pts", "ausc_min_riv", "ausc_pts_riv"]
PREV = ["prev_n", "prev_min", "prev_pts", "prev_reb", "prev_ast", "prev_min_riv", "prev_pts_riv"]
SOLO_CONTINUAN = {"aus_n": "ausc_n", "aus_min": "ausc_min", "aus_pts": "ausc_pts", "aus_reb": "ausc_reb",
                  "aus_ast": "ausc_ast", "aus_min_riv": "ausc_min_riv", "aus_pts_riv": "ausc_pts_riv"}


def calcular(desde: int = 2014) -> pd.DataFrame:
    """Una fila por (personId, gameId) con aus_*, ausc_* y prev_* de su equipo (sin contarlo a él)
    y aus/ausc/prev de minutos y puntos del rival."""
    df = pd.read_parquet("data/clean/player_games.parquet",
                         columns=["personId", "gameId", "temporada", "playerteamId", "opponentteamId", "jugo"] + OBJETIVOS)
    df = df[(df["temporada"] >= desde - 2) & df["playerteamId"].notna()].copy()
    for c in ["playerteamId", "opponentteamId", "gameId", "personId"]:
        df[c] = df[c].astype("int64")
    t = tf.cargar_equipos(f"{desde - 3}-10-01")[["gameId", "teamId", "gameDateTimeEst"]].sort_values(["teamId", "gameDateTimeEst"])
    t["i"] = t.groupby("teamId").cumcount()
    df = df.merge(t[["gameId", "teamId", "i"]].rename(columns={"teamId": "playerteamId"}), on=["gameId", "playerteamId"])
    pj = df[df["jugo"]]

    equipo, propio = [], []
    for team, d in pj.groupby("playerteamId"):
        n = int(t.loc[t["teamId"] == team, "i"].max()) + 1
        piv = {k: d.pivot(index="i", columns="personId", values=c).reindex(range(n)) for k, c in STATS.items()}
        jug = piv["min"].notna()
        prom = {k: p.rolling(PARTIDOS, min_periods=1).mean().shift(1) for k, p in piv.items()}
        rotacion = (jug.rolling(PARTIDOS, min_periods=1).sum().shift(1) >= MINIMO_JUGADOS) & (prom["min"] >= MINIMO_MINUTOS)
        grupos = {"aus": rotacion & ~jug}
        grupos["ausc"] = grupos["aus"] & ~jug.shift(1, fill_value=True)
        grupos["prev"] = grupos["aus"].shift(1, fill_value=False)
        valores = {"aus": prom, "ausc": prom, "prev": {k: p.shift(1) for k, p in prom.items()}}
        fila = {"playerteamId": team, "i": np.arange(n)}
        for g, quien in grupos.items():
            fila[f"{g}_n"] = quien.sum(axis=1).to_numpy()
            for k in STATS:
                fila[f"{g}_{k}"] = valores[g][k].where(quien).sum(axis=1).to_numpy()
            # lo que aporta cada uno a la suma de su equipo, para no contarlo en su propia fila
            a = quien.stack()
            a = a[a].index.to_frame(index=False)
            a.columns = ["i", "personId"]
            llave = pd.MultiIndex.from_frame(a[["i", "personId"]])
            a["playerteamId"], a["grupo"] = team, g
            for k in STATS:
                a[k] = valores[g][k].stack(future_stack=True).reindex(llave).to_numpy()
            propio.append(a)
        equipo.append(pd.DataFrame(fila))
    eq, own = pd.concat(equipo, ignore_index=True), pd.concat(propio, ignore_index=True)

    x = df[df["temporada"] >= desde][["personId", "gameId", "playerteamId", "opponentteamId", "i"]]
    x = x.merge(eq, on=["playerteamId", "i"], how="left")
    for g in ("aus", "ausc", "prev"):
        o = own[own["grupo"] == g].drop(columns="grupo").rename(columns={k: f"_{k}" for k in STATS})
        x = x.merge(o, on=["playerteamId", "i", "personId"], how="left")
        x[f"{g}_n"] = x[f"{g}_n"] - x["_min"].notna()
        for k in STATS:
            x[f"{g}_{k}"] = x[f"{g}_{k}"] - x[f"_{k}"].fillna(0)
        x = x.drop(columns=[f"_{k}" for k in STATS])
    riv = eq[["playerteamId", "i"] + [f"{g}_{k}" for g in ("aus", "ausc", "prev") for k in ("min", "pts")]]
    riv = riv.rename(columns={c: f"{c}_riv" for c in riv.columns if c not in ("playerteamId", "i")})
    riv = riv.rename(columns={"playerteamId": "opponentteamId", "i": "i_riv"})
    x = x.merge(t[["gameId", "teamId", "i"]].rename(columns={"teamId": "opponentteamId", "i": "i_riv"}),
                on=["gameId", "opponentteamId"], how="left").merge(riv, on=["opponentteamId", "i_riv"], how="left")
    return x.drop(columns=["playerteamId", "opponentteamId", "i", "i_riv"])


def main():
    x = calcular()
    t = banco.tabla().merge(x, on=["personId", "gameId"], how="left", validate="1:1")
    banco._tabla = t
    nuevas = [c for c in x.columns if c not in ("personId", "gameId")]
    guardados = {}

    def variante(extra: list, servir_como: dict = None, de: str = None):
        def f(fit, calib, test, cols, objetivos):
            base = [c for c in columnas_features(fit, "jugados") if c not in nuevas]
            if de:                               # un modelo ya entrenado, servido con menos información
                test = test.copy()
                for k, v in servir_como.items():
                    test[k] = test[v]
                return banco._de_paquete(guardados[(de, len(fit))], test, objetivos)
            paq = paquetes.entrenar(fit, calib, base + extra, "nb", objetivos)
            guardados[(extra[0] if extra else "v4", len(fit))] = paq
            return banco._de_paquete(paq, test, objetivos)
        return f

    res = banco.comparar({"v4": variante([]), "v4+aus": variante(AUS),
                          "v4+aus>cont": variante(AUS, SOLO_CONTINUAN, de=AUS[0]),
                          "v4+ausc": variante(AUSC), "v4+prev": variante(PREV)},
                         OBJETIVOS, guardar="banco_ausencias.csv")
    banco.resumen(res, ("MAE", "pinball"))


if __name__ == "__main__":
    main()
