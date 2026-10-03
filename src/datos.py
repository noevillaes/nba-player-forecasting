"""Lectura unificada: dataset de Kaggle + partidos descargados en vivo con
nba_api. Si un partido existe en ambas fuentes, se queda la versión de Kaggle."""
import os
import pandas as pd

RAW = "data/raw"
VIVO = {"PlayerStatistics": "vivo_player.parquet",
        "PlayerStatisticsExtended": "vivo_extended.parquet",
        "TeamStatistics": "vivo_team.parquet"}


def leer(nombre: str, columns: list = None) -> pd.DataFrame:
    d = pd.read_parquet(f"{RAW}/{nombre}.parquet", columns=columns)
    ruta = f"{RAW}/{VIVO[nombre]}" if nombre in VIVO else None
    if ruta and os.path.exists(ruta):
        v = pd.read_parquet(ruta)
        if columns:
            v = v[[c for c in columns if c in v.columns]]
        en_kaggle = set(d["gameId"].astype("int64"))
        v = v[~v["gameId"].astype("int64").isin(en_kaggle)]
        d = pd.concat([d, v], ignore_index=True)
    return d