"""Normaliza, filtra y arma la tabla jugador-partido base."""
import os
import pandas as pd

RAW = "data/raw"
OUT = "data/clean"

MAPA_GAMETYPE = {
    "Regular Season":     "regular",
    "Playoffs":           "playoffs",
    "Play-in Tournament": "playin",
    "Play-in Tour":       "playin",
    "Preseason":          "preseason",
    "Pre Season":         "preseason",
    "All-Star Game":      "allstar",
    # La Copa NBA aparece con 4 nombres distintos según la temporada
    "NBA Emirates Cup":   "cup",
    "Emirates NBA Cup":   "cup",
    "NBA Cup":            "cup",
    "in-season-knockout": "cup",
}


def temporada(fecha: pd.Series) -> pd.Series:
    """Año de inicio de la temporada. Corte en agosto, excepto la burbuja
    de 2020: los playoffs de 2019-20 se jugaron de agosto a octubre de 2020."""
    t = fecha.dt.year - (fecha.dt.month < 8).astype(int)
    burbuja = (fecha >= "2020-08-01") & (fecha < "2020-11-01")
    return t.where(~burbuja, 2019)


def normalizar_gametype(d: pd.DataFrame) -> pd.Series:
    """Mapea gameType a categorías limpias. Los partidos de la Copa NBA
    cuentan como temporada regular, excepto la final."""
    desconocidas = set(d["gameType"].dropna().unique()) - set(MAPA_GAMETYPE)
    if desconocidas:
        raise ValueError(f"Etiquetas de gameType sin mapear: {desconocidas}")

    tipo = d["gameType"].map(MAPA_GAMETYPE)
    es_cup = tipo.eq("cup")
    # La final de 2023 viene como 'NBA Cup' sin sub-etiqueta;
    # las finales posteriores traen gameSubLabel == 'Championship'
    es_final = es_cup & (d["gameSubLabel"].eq("Championship")
                         | d["gameType"].eq("NBA Cup"))
    tipo = tipo.where(~es_cup, "regular")
    tipo = tipo.where(~es_final, "cup_final")
    return tipo


def parsear_minutos(s: pd.Series) -> pd.Series:
    """Convierte minutos a float. Acepta números, '34' o '34:12' (mm:ss)."""
    texto = s.astype("string").str.strip()
    tiene_dos_puntos = texto.str.contains(":", na=False)

    resultado = pd.to_numeric(texto.where(~tiene_dos_puntos), errors="coerce")

    if tiene_dos_puntos.any():
        partes = texto[tiene_dos_puntos].str.split(":", expand=True)
        if partes.shape[1] != 2:
            raise ValueError("Formato de minutos con más de un ':' encontrado")
        resultado[tiene_dos_puntos] = (
            pd.to_numeric(partes[0], errors="coerce")
            + pd.to_numeric(partes[1], errors="coerce") / 60
        )

    sin_convertir = resultado.isna() & s.notna()
    if sin_convertir.any():
        raise ValueError(f"Minutos no reconocidos: "
                         f"{s[sin_convertir].unique()[:10]}")
    return resultado.astype(float)


def main(desde=1996):
    ps = pd.read_parquet(f"{RAW}/PlayerStatistics.parquet")
    ext = pd.read_parquet(f"{RAW}/PlayerStatisticsExtended.parquet")

    # 1. Tipo de partido y temporada
    ps["tipo"] = normalizar_gametype(ps)
    ps = ps[ps["tipo"].isin(["regular", "playoffs", "playin"])].copy()
    ps["temporada"] = temporada(ps["gameDateTimeEst"])
    ps = ps[ps["temporada"] >= desde]

    # 2. Banderas útiles
    ps["numMinutes"] = parsear_minutos(ps["numMinutes"]).fillna(0)
    ps["jugo"] = ps["numMinutes"] > 0
    ps["titular"] = ps["startingPosition"].notna()

    # 3. Unir columnas avanzadas (solo las que no están en ps)
    extra = [c for c in ext.columns if c not in ps.columns]
    ps = ps.merge(ext[["personId", "gameId"] + extra],
                  on=["personId", "gameId"], how="left", validate="1:1")

    # 4. Validaciones
    assert not ps.duplicated(["personId", "gameId"]).any(), "Duplicados"
    assert ps["gameDateTimeEst"].notna().all(), "Fechas vacías"
    sin_ext = ps["jugo"] & ps["usagePercentage"].isna()
    print(f"Jugaron pero sin datos avanzados: {sin_ext.sum()}")

    os.makedirs(OUT, exist_ok=True)
    ps = ps.sort_values(["personId", "gameDateTimeEst"]).reset_index(drop=True)
    ps.to_parquet(f"{OUT}/player_games.parquet", index=False)
    print(ps.shape)
    print(ps.groupby("temporada").size().to_string())


if __name__ == "__main__":
    main()