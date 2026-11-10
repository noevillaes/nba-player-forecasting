"""Features por jugador-partido.
Regla de oro: cada feature usa solo información disponible ANTES del
partido. Por eso todo pasa por shift(1) antes de cualquier ventana.

construir() sirve para el histórico y para filas futuras (es_futuro=True):
como todo mira hacia atrás, una fila futura recibe sus features del pasado.

Hay dos diseños de features en la misma tabla ("filas" y "jugados"); ver DISENO más abajo."""
import os
import numpy as np
import pandas as pd

CLEAN = "data/clean"
OUT = "data/features"
VENTANAS = [5, 10, 20]
STATS = ["points", "reboundsTotal", "reboundsOffensive", "reboundsDefensive",
         "assists", "steals", "blocks", "turnovers", "foulsPersonal",
         "fieldGoalsMade", "fieldGoalsAttempted",
         "threePointersMade", "threePointersAttempted",
         "freeThrowsMade", "freeThrowsAttempted"]
OBJETIVOS = ["numMinutes"] + STATS
IDS = ["personId", "firstName", "lastName", "gameId", "fecha",
       "temporada", "tipo", "playerteamId", "opponentteamId"]


def previo(df: pd.DataFrame, col: str) -> pd.Series:
    """Valor del partido anterior del mismo jugador."""
    return df.groupby("personId")[col].shift(1)


def ventana(df: pd.DataFrame, col: str, n: int, func: str = "mean") -> pd.Series:
    """Estadística de los n partidos ANTERIORES del mismo jugador."""
    r = previo(df, col).groupby(df["personId"]).rolling(n, min_periods=1)
    return getattr(r, func)().reset_index(level=0, drop=True)


def suavizado(df: pd.DataFrame, col: str, vida_media: float) -> pd.Series:
    """Promedio exponencial de los partidos ANTERIORES: cada partido pesa la mitad
    que uno jugado `vida_media` partidos después. Sin cortes bruscos de ventana."""
    r = previo(df, col).groupby(df["personId"]).ewm(halflife=vida_media, min_periods=1)
    return r.mean().reset_index(level=0, drop=True)


# Grupos de features agregados en la v2 (octubre 2026). Se pueden activar o
# desactivar como bloque para compararlos en evaluate_features.py
ROL = ["min_prom_3", "min_tendencia", "min_suav_3", "min_suav_10",
       "titular_ultimo", "jugo_ultimo"]
LARGO = ([f"{s}_pm_82" for s in STATS] + [f"{s}_pm_suav_10" for s in STATS])

# Dos diseños de features (jugadores v4, noviembre 2026).
#   "filas"    (v1 a v3) las ventanas recorren filas del box score: últimas 10 filas, días desde la
#              fila anterior. Depende de qué filas de 0 minutos trae la fuente, y el box score en
#              vivo trae ~1.4 más por equipo-partido que el histórico: el mismo jugador se veía
#              distinto al entrenar que al pronosticar.
#   "jugados"  (v4) las mismas ideas sobre partidos JUGADOS (j_*) y la ausencia medida con el
#              calendario del equipo (cal_*). No cambian si aparecen o desaparecen filas de 0 minutos.
# La tabla guarda los dos juegos de columnas: cada paquete de modelo usa las suyas.
DISENO = "jugados"
POR_FILAS = (["min_prom_3", "min_prom_5", "min_prom_10", "min_prom_20", "min_ultimo", "titular_prop_10",
              "jugo_prop_10", "uso_prom_10", "partidos_temp", "dias_descanso", "back_to_back",
              "min_tendencia", "min_suav_3", "min_suav_10", "titular_ultimo", "jugo_ultimo"]
             + [f"{s}_pm_{n}" for s in STATS for n in (10, 20, 82)] + [f"{s}_pm_suav_10" for s in STATS])
PREFIJOS_JUGADOS = ("j_", "cal_")


def columnas_del_diseno(cols: list, diseno: str = None) -> list:
    """De todas las columnas de features, las que usa ese diseño."""
    diseno = diseno or DISENO
    if diseno == "filas":
        return [c for c in cols if not c.startswith(PREFIJOS_JUGADOS)]
    if diseno == "jugados":
        if not any(c.startswith(PREFIJOS_JUGADOS) for c in cols):
            raise ValueError("La tabla de features no tiene las columnas del diseño \"jugados\" (j_*, cal_*). "
                             "Vuelve a generarla: python src/features.py y luego python src/team_features.py")
        return [c for c in cols if c not in POR_FILAS]
    raise ValueError(f"Diseño de features desconocido: {diseno}")


def diseno_de(cols: list) -> str:
    """El diseño con que se entrenó un paquete, a partir de sus columnas."""
    return "jugados" if any(c.startswith(PREFIJOS_JUGADOS) for c in cols) else "filas"


def sobre_jugados(df: pd.DataFrame) -> pd.DataFrame:
    """Features j_* y la fecha del último partido jugado, para TODAS las filas de df (jugó, no
    jugó o por jugar): cada fila recibe el estado del jugador después de su último partido jugado
    estrictamente anterior. df viene ordenado por jugador y fecha, con índice 0..n-1.

    Cada columna se calcula en precisión doble y se guarda en float32 en cuanto está lista: la
    tabla completa (1996 a hoy) son ~80 columnas por ~800 mil partidos jugados, y en doble
    precisión duplicaba la memoria de la corrida diaria."""
    pj = df[df["jugo"] == 1]
    g = pj.groupby("personId")
    rm = lambda col, n, f="mean": getattr(g[col].rolling(n, min_periods=1), f)().reset_index(level=0, drop=True)
    ew = lambda col, h: g[col].ewm(halflife=h, min_periods=1).mean().reset_index(level=0, drop=True)

    e = {}                                                   # nombre -> arreglo float32, alineado con pj

    def guardar(nombre, serie):
        e[nombre] = serie.reindex(pj.index).to_numpy("float32")

    proms = {n: rm("numMinutes", n) for n in [3, 5, 10, 20]}
    for n, p in proms.items():
        guardar(f"j_min_prom_{n}", p)
    guardar("j_min_ultimo", pj["numMinutes"])
    guardar("j_min_desv_10", g["numMinutes"].rolling(10, min_periods=3).std().reset_index(level=0, drop=True))
    guardar("j_titular_prop_10", rm("titular", 10))
    guardar("j_titular_ultimo", pj["titular"])
    guardar("j_uso_prom_10", rm("usagePercentage", 10))
    suav_10 = ew("numMinutes", 10)
    guardar("j_min_suav_3", ew("numMinutes", 3))
    guardar("j_min_suav_10", suav_10)
    guardar("j_min_tendencia", proms[3] - proms[20])
    mins = {n: rm("numMinutes", n, "sum").replace(0, np.nan) for n in [10, 20, 82]}
    mins_suav = suav_10.replace(0, np.nan)
    for stat in STATS:
        for n in [10, 20, 82]:
            guardar(f"j_{stat}_pm_{n}", rm(stat, n, "sum") / mins[n])
        guardar(f"j_{stat}_pm_suav_10", ew(stat, 10) / mins_suav)
    guardar("j_partidos_temp", pj.groupby(["personId", "temporada"]).cumcount() + 1)

    # a cada fila, la posición (en pj) de su último partido jugado estrictamente anterior
    der = pd.DataFrame({"personId": pj["personId"].to_numpy(), "gameDateTimeEst": pj["gameDateTimeEst"].to_numpy(),
                        "pos": np.arange(len(pj))}).sort_values("gameDateTimeEst")
    izq = df[["personId", "gameDateTimeEst"]].reset_index().sort_values("gameDateTimeEst")
    pos = pd.merge_asof(izq, der, on="gameDateTimeEst", by="personId", allow_exact_matches=False)
    pos = pos.set_index("index")["pos"].reindex(df.index)
    hay = pos.notna().to_numpy()
    p = pos.fillna(0).to_numpy("int64")

    x = pd.DataFrame({k: np.where(hay, v[p], np.float32(np.nan)) for k, v in e.items()}, index=df.index)
    # los partidos de esta temporada: si su último partido fue de otra, lleva 0
    misma = hay & (pj["temporada"].to_numpy()[p] == df["temporada"].to_numpy())
    x["j_partidos_temp"] = x["j_partidos_temp"].where(misma, 0)
    dias = (df["fecha"].to_numpy() - pj["fecha"].to_numpy()[p]) / np.timedelta64(1, "D")
    x["cal_dias_sin_jugar"] = np.where(hay, np.clip(dias, None, 60), np.nan).astype("float32")
    x["cal_b2b"] = (x["cal_dias_sin_jugar"] == 1).astype("float32")
    return x


def por_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Ausencia medida con los partidos del equipo, no con filas del jugador:
      cal_partidos_eq_perdidos   partidos del equipo desde el último que jugó con él
      cal_jugo_prop_eq_10        de los últimos 10 partidos del equipo, cuántos jugó
      cal_partidos_con_equipo    partidos jugados con este equipo (tope 82): recién llegado o no
    El calendario del equipo sale de las propias filas (todo partido tiene alguna)."""
    out = pd.DataFrame(np.nan, index=df.index, columns=["cal_partidos_eq_perdidos", "cal_jugo_prop_eq_10"])
    out["cal_partidos_con_equipo"] = 0.0
    d = df.loc[df["playerteamId"].notna(), ["personId", "playerteamId", "gameId", "gameDateTimeEst", "jugo"]]
    eq = d.drop_duplicates(["playerteamId", "gameId"]).sort_values(["playerteamId", "gameDateTimeEst"])
    eq["i"] = eq.groupby("playerteamId").cumcount()
    i = d.merge(eq[["playerteamId", "gameId", "i"]], on=["playerteamId", "gameId"], how="left")["i"].to_numpy()
    jugo = (d["jugo"] == 1).to_numpy()
    perd, prop, con = np.full(len(d), np.nan), np.full(len(d), np.nan), np.zeros(len(d))
    for filas in d.groupby(["personId", "playerteamId"]).indices.values():
        ii = i[filas]
        P = np.sort(ii[jugo[filas]])
        if not len(P):
            prop[filas] = 0.0
            continue
        n = np.searchsorted(P, ii, "left")
        hay = n > 0
        perd[filas[hay]] = ii[hay] - 1 - P[n[hay] - 1]
        prop[filas] = (n - np.searchsorted(P, ii - 10, "left")) / np.clip(np.minimum(10, ii), 1, None)
        con[filas] = np.minimum(n, 82)
    out.loc[d.index, "cal_partidos_eq_perdidos"] = np.clip(perd, None, 30)
    out.loc[d.index, "cal_jugo_prop_eq_10"] = prop
    out.loc[d.index, "cal_partidos_con_equipo"] = con
    return out


def construir(df: pd.DataFrame) -> pd.DataFrame:
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

    # 2. Producción por minuto: suma(stat) / suma(minutos) en la ventana
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

    # 4. Descanso (fechas sin hora: 22:00 → 19:00 del día siguiente = 1 día)
    dias = df.groupby("personId")["fecha"].diff().dt.days
    f["dias_descanso"] = dias.clip(upper=10)
    f["back_to_back"] = dias.eq(1).astype(int)

    # 5. Contexto del partido (se conoce antes de jugarlo)
    f["local"] = df["home"].astype(int)
    f["playoffs"] = df["tipo"].eq("playoffs").astype(int)

    # 6. Cambios de rol: reaccionan en días, no en semanas
    #    (un jugador que pasa a la banca o regresa de lesión)
    f["min_prom_3"] = ventana(df, "numMinutes", 3)
    f["min_tendencia"] = f["min_prom_3"] - f["min_prom_20"]
    f["min_suav_3"] = suavizado(df, "numMinutes", 3)
    f["min_suav_10"] = suavizado(df, "numMinutes", 10)
    f["titular_ultimo"] = previo(df, "titular")
    f["jugo_ultimo"] = previo(df, "jugo")

    # 7. Nivel de largo plazo: producción por minuto con memoria larga.
    #    82 partidos ≈ una temporada; el suavizado no tiene cortes bruscos
    mins_82 = ventana(df, "numMinutes", 82, "sum").replace(0, np.nan)
    mins_suav = suavizado(df, "numMinutes", 10).replace(0, np.nan)
    for stat in STATS:
        f[f"{stat}_pm_82"] = ventana(df, stat, 82, "sum") / mins_82
        f[f"{stat}_pm_suav_10"] = suavizado(df, stat, 10) / mins_suav

    # 8. Lo mismo sobre partidos jugados, y la ausencia por calendario (diseño "jugados", v4)
    nuevas = pd.concat([sobre_jugados(df), por_calendario(df)], axis=1).astype("float32")

    # Prueba anti-fuga: el primer partido de cada jugador no tiene historia
    primeros = df.groupby("personId").cumcount().eq(0)
    assert f.loc[primeros, "min_prom_5"].isna().all(), "Fuga de información"
    assert nuevas.loc[primeros, "j_min_prom_5"].isna().all(), "Fuga de información"

    ids = IDS + (["es_futuro"] if "es_futuro" in df.columns else [])
    objetivos = df[OBJETIVOS + ["jugo"]].add_prefix("y_")
    out = pd.concat([df[ids], f, nuevas, objetivos], axis=1)
    if "es_futuro" in out.columns:
        out.loc[out["es_futuro"], objetivos.columns] = np.nan
    return out


# Lo único que construir() lee de la tabla limpia (que trae ~60 columnas más)
ENTRADA = ["personId", "firstName", "lastName", "gameId", "gameDateTimeEst", "temporada", "tipo",
           "playerteamId", "opponentteamId", "home", "numMinutes", "jugo", "titular", "usagePercentage"] + STATS


def main():
    out = construir(pd.read_parquet(f"{CLEAN}/player_games.parquet", columns=ENTRADA))
    os.makedirs(OUT, exist_ok=True)
    out.to_parquet(f"{OUT}/player_features.parquet", index=False)
    print(out.shape)
    feats = [c for c in out.columns if c not in IDS and not c.startswith("y_")]
    print(out[feats].isna().mean().round(3).sort_values(ascending=False).head(10).to_string())


if __name__ == "__main__":
    main()