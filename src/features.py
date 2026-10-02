"""Features por jugador-partido.
Regla de oro: cada feature usa solo información disponible ANTES del
partido. Por eso todo pasa por shift(1) antes de cualquier ventana."""
import os
import numpy as np
import pandas as pd

CLEAN = "data/clean"
OUT = "data/features"
VENTANAS = [5, 10, 20]
STATS = ["points", "reboundsTotal", "assists", "threePointersMade",
         "steals", "blocks", "turnovers", "fieldGoalsAttempted",
         "freeThrowsAttempted"]
OBJETIVOS = ["numMinutes", "points", "reboundsTotal", "assists",
             "threePointersMade"]


def previo(df: pd.DataFrame, col: str) -> pd.Series:
    """Valor del partido anterior del mismo jugador."""
    return df.groupby("personId")[col].shift(1)


def ventana(df: pd.DataFrame, col: str, n: int, func: str = "mean") -> pd.Series:
    """Estadística de los n partidos ANTERIORES del mismo jugador."""
    r = previo(df, col).groupby(df["personId"]).rolling(n, min_periods=1)
    return getattr(r, func)().reset_index(level=0, drop=True)


def main():
    df = pd.read_parquet(f"{CLEAN}/player_games.parquet")
    df = df.sort_values(["personId", "gameDateTimeEst"]).reset_index(drop=True)
    df["fecha"] = df["gameDateTimeEst"].dt.normalize()
    df["titular"] = df["titular"].astype(float)
    df["jugo"] = df["jugo"].astype(float)
    for c in STATS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)  # DNP = 0

    f = pd.DataFrame(index=df.index)

    # 1. Rol: minutos, titularidad, disponibilidad y uso
    for n in VENTANAS:
        f[f"min_prom_{n}"] = ventana(df, "numMinutes", n)
    f["min_ultimo"] = previo(df, "numMinutes")
    f["titular_prop_10"] = ventana(df, "titular", 10)
    f["jugo_prop_10"] = ventana(df, "jugo", 10)
    f["uso_prom_10"] = ventana(df, "usagePercentage", 10)

    # 2. Producción por minuto: suma(stat) / suma(minutos) en la ventana.
    #    Es más estable que promediar porcentajes partido a partido.
    for n in [10, 20]:
        mins = ventana(df, "numMinutes", n, "sum").replace(0, np.nan)
        for stat in STATS:
            f[f"{stat}_pm_{n}"] = ventana(df, stat, n, "sum") / mins

    # 3. Producción por minuto en lo que va de la temporada
    grp = df.groupby(["personId", "temporada"])
    min_temp = (grp["numMinutes"].cumsum() - df["numMinutes"]).replace(0, np.nan)
    for stat in ["points", "reboundsTotal", "assists"]:
        f[f"{stat}_pm_temp"] = (grp[stat].cumsum() - df[stat]) / min_temp
    f["partidos_temp"] = grp.cumcount()

    # 4. Descanso. Se usan fechas sin hora: con hora, un partido a las 22:00
    #    y otro a las 19:00 del día siguiente contarían como 0 días.
    dias = df.groupby("personId")["fecha"].diff().dt.days
    f["dias_descanso"] = dias.clip(upper=10)
    f["back_to_back"] = dias.eq(1).astype(int)

    # 5. Contexto del partido (se conoce antes de jugarlo)
    f["local"] = df["home"].astype(int)
    f["playoffs"] = df["tipo"].eq("playoffs").astype(int)

    # Prueba anti-fuga: el primer partido de cada jugador no tiene historia
    primeros = df.groupby("personId").cumcount().eq(0)
    assert f.loc[primeros, "min_prom_5"].isna().all(), "Fuga de información"

    ids = ["personId", "firstName", "lastName", "gameId", "fecha",
           "temporada", "tipo", "playerteamId", "opponentteamId"]
    objetivos = df[OBJETIVOS + ["jugo"]].add_prefix("y_")
    out = pd.concat([df[ids], f, objetivos], axis=1)

    os.makedirs(OUT, exist_ok=True)
    out.to_parquet(f"{OUT}/player_features.parquet", index=False)
    print(out.shape)
    print(f.isna().mean().round(3).sort_values(ascending=False).head(10).to_string())


if __name__ == "__main__":
    main()