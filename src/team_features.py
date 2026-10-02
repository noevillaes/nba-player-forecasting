"""Features de equipo y rival (ritmo, eficiencia, lo que permite),
unidas a la tabla de jugador. Misma regla: solo información previa
al partido (shift(1) antes de cualquier ventana)."""
import numpy as np
import pandas as pd

RAW = "data/raw"
FEAT = "data/features"
N = 10
PREFIJOS_VALIDOS = ("2", "4", "5")  # gameId: regular, playoffs, play-in

NUM = ["teamScore", "opponentScore", "fieldGoalsAttempted",
       "freeThrowsAttempted", "reboundsOffensive", "reboundsTotal",
       "turnovers", "assists", "threePointersMade", "numMinutes"]
COLS = ["pace", "ortg", "drtg", "reb_permitidos",
        "ast_permitidas", "triples_permitidos"]


def cargar_equipos() -> pd.DataFrame:
    t = pd.read_parquet(f"{RAW}/TeamStatistics.parquet")
    t = t[t["gameId"].astype(str).str[0].isin(PREFIJOS_VALIDOS)]
    t = t[t["gameDateTimeEst"] >= "1995-10-01"].copy()
    assert not t.duplicated(["teamId", "gameId"]).any(), "Equipo duplicado"
    for c in NUM:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    for c in ["gameId", "teamId", "opponentTeamId"]:
        t[c] = t[c].astype("int64")
    return t


def metricas_por_partido(t: pd.DataFrame) -> pd.DataFrame:
    t["poss"] = (t["fieldGoalsAttempted"] + 0.44 * t["freeThrowsAttempted"]
                 - t["reboundsOffensive"] + t["turnovers"])

    # Lo que hizo el rival en ese mismo partido = lo que el equipo permitió
    rival = t[["gameId", "teamId", "poss", "reboundsTotal",
               "assists", "threePointersMade"]].add_prefix("opp_")
    t = t.merge(rival, left_on=["gameId", "opponentTeamId"],
                right_on=["opp_gameId", "opp_teamId"], how="left",
                validate="1:1")

    # Minutos del partido: si viene como suma de jugadores (~240), dividir entre 5
    mins = t["numMinutes"]
    if mins.median() > 100:
        mins = mins / 5
    mins = mins.where(mins > 0, 48)

    poss = (t["poss"] + t["opp_poss"]) / 2
    t["pace"] = poss / mins * 48
    t["ortg"] = t["teamScore"] / poss * 100
    t["drtg"] = t["opponentScore"] / poss * 100
    t["reb_permitidos"] = t["opp_reboundsTotal"]
    t["ast_permitidas"] = t["opp_assists"]
    t["triples_permitidos"] = t["opp_threePointersMade"]
    return t


def ventanas_previas(t: pd.DataFrame) -> pd.DataFrame:
    t = t.sort_values(["teamId", "gameDateTimeEst"]).reset_index(drop=True)
    g = t.groupby("teamId")
    out = t[["gameId", "teamId"]].copy()
    for c in COLS:
        prev = g[c].shift(1)
        out[f"{c}_{N}"] = (prev.groupby(t["teamId"])
                           .rolling(N, min_periods=3).mean()
                           .reset_index(level=0, drop=True))
    fecha = t["gameDateTimeEst"].dt.normalize()
    out["dias_descanso_eq"] = fecha.groupby(t["teamId"]).diff().dt.days.clip(upper=10)
    out["b2b_eq"] = out["dias_descanso_eq"].eq(1).astype(int)
    return out


def main():
    t = metricas_por_partido(cargar_equipos())
    print("Medianas de control:",
          t[["pace", "ortg", "drtg"]].median().round(1).to_dict())

    eq = ventanas_previas(t)

    p = pd.read_parquet(f"{FEAT}/player_features.parquet")
    for c in ["gameId", "playerteamId", "opponentteamId"]:
        p[c] = p[c].astype("Int64")   # entero que acepta vacíos
        print(f"{c} vacíos: {p[c].isna().sum()}")
    eq[["gameId", "teamId"]] = eq[["gameId", "teamId"]].astype("Int64")

    propio = eq.add_prefix("propio_").rename(
        columns={"propio_gameId": "gameId", "propio_teamId": "playerteamId"})
    rival = eq.add_prefix("rival_").rename(
        columns={"rival_gameId": "gameId", "rival_teamId": "opponentteamId"})

    p = p.merge(propio, on=["gameId", "playerteamId"], how="left", validate="m:1")
    p = p.merge(rival, on=["gameId", "opponentteamId"], how="left", validate="m:1")

    print(p.shape)
    nuevas = [c for c in p.columns if c.startswith(("propio_", "rival_"))]
    print("Vacíos en features de equipo:")
    print(p[nuevas].isna().mean().round(3).sort_values(ascending=False).head(6).to_string())

    p.to_parquet(f"{FEAT}/model_table.parquet", index=False)


if __name__ == "__main__":
    main()