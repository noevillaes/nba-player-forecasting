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

    # Final de la Copa NBA: la etiqueta cambia cada año (e incluso entre
    # equipos del mismo partido), pero el gameId siempre empieza con 6.
    es_final = d["gameId"].astype(str).str.startswith("6")

    # Validación cruzada: todo 'Championship' fuera del All-Star
    # (ej. la final del Rising Stars) debe tener prefijo 6
    champ = d["gameSubLabel"].eq("Championship") & tipo.ne("allstar")
    if (champ & ~es_final).any():
        raise ValueError("Hay partidos 'Championship' sin gameId con prefijo 6")

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


def rellenar_equipos(ps: pd.DataFrame) -> pd.DataFrame:
    """Recupera playerteamId/opponentteamId vacíos cruzando (gameId, home)
    con TeamStatistics. En 2021-22 casi toda la temporada viene sin ID."""
    t = pd.read_parquet(f"{RAW}/TeamStatistics.parquet",
                        columns=["gameId", "home", "teamId", "opponentTeamId"])
    t = t.dropna(subset=["home"]).copy()
    t["gameId"] = t["gameId"].astype("int64")
    t["home"] = t["home"].astype(int)

    dup = t.duplicated(["gameId", "home"]).sum()
    if dup:
        print(f"Aviso: {dup} partidos con (gameId, home) repetido en TeamStatistics")
        t = t.drop_duplicates(["gameId", "home"])

    ps["gameId"] = ps["gameId"].astype("int64")
    ps["home"] = ps["home"].astype(int)
    m = ps[["gameId", "home"]].merge(t, on=["gameId", "home"],
                                     how="left", validate="m:1")
    m.index = ps.index

    # Control de consistencia: donde ya había ID, debe coincidir
    hay = ps["playerteamId"].notna() & m["teamId"].notna()
    distintos = (ps.loc[hay, "playerteamId"].astype("int64")
                 != m.loc[hay, "teamId"].astype("int64")).sum()
    print(f"IDs existentes que NO coinciden con TeamStatistics: {distintos}")

    antes = ps["playerteamId"].isna().sum()
    ps["playerteamId"] = ps["playerteamId"].fillna(m["teamId"])
    ps["opponentteamId"] = ps["opponentteamId"].fillna(m["opponentTeamId"])
    print(f"Sin equipo: {antes} antes → {ps['playerteamId'].isna().sum()} después")
    return ps


def main(desde=1996):
    ps = pd.read_parquet(f"{RAW}/PlayerStatistics.parquet")
    ext = pd.read_parquet(f"{RAW}/PlayerStatisticsExtended.parquet")

    # 1. Tipo de partido y temporada
    ps["tipo"] = normalizar_gametype(ps)
    ps = ps[ps["tipo"].isin(["regular", "playoffs", "playin"])].copy()
    ps["temporada"] = temporada(ps["gameDateTimeEst"])
    ps = ps[ps["temporada"] >= desde]
    ps = rellenar_equipos(ps)

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