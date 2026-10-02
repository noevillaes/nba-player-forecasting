"""Descarga el dataset (versión fija), valida fechas y convierte a parquet."""
import os
import kagglehub
import pandas as pd

DATASET = "eoinamoore/historical-nba-data-and-player-box-scores"
VERSION = 515
ARCHIVOS = ["PlayerStatistics", "PlayerStatisticsExtended",
            "TeamStatistics", "TeamStatisticsExtended", "Games"]
OUT = "data/raw"


def descargar() -> str:
    return kagglehub.dataset_download(f"{DATASET}/versions/{VERSION}")


def parsear_fechas(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="mixed", errors="coerce")


def rellenar_fechas(d: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Fechas vacías → se toman de Games.csv usando gameId."""
    faltan = d["gameDateTimeEst"].isna()
    if faltan.any():
        mapa = games.drop_duplicates("gameId").set_index("gameId")["gameDateTimeEst"]
        d.loc[faltan, "gameDateTimeEst"] = d.loc[faltan, "gameId"].map(mapa)
    return d


def main():
    ruta = descargar()
    print("Dataset en:", ruta)
    os.makedirs(OUT, exist_ok=True)

    games = pd.read_csv(os.path.join(ruta, "Games.csv"), low_memory=False)
    games["gameDateTimeEst"] = parsear_fechas(games["gameDateTimeEst"])

    for nombre in ARCHIVOS:
        d = pd.read_csv(os.path.join(ruta, f"{nombre}.csv"), low_memory=False)
        d["gameDateTimeEst"] = parsear_fechas(d["gameDateTimeEst"])
        d = rellenar_fechas(d, games)

        n_nat = d["gameDateTimeEst"].isna().sum()
        print(f"{nombre}: {d.shape} | "
              f"{d['gameDateTimeEst'].min()} → {d['gameDateTimeEst'].max()} | "
              f"fechas sin resolver: {n_nat}")

        d.to_parquet(os.path.join(OUT, f"{nombre}.parquet"), index=False)
        del d


if __name__ == "__main__":
    main()