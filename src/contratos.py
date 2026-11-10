"""Contratos de datos: lo que tiene que cumplirse antes de guardar o publicar algo.

Dos niveles:
  errores   el archivo no se escribe y el paso falla (el vigía de GitHub avisa si no hay pronóstico)
  avisos    se escriben en el log y se publica igual

Los límites son anchos a propósito: están para atrapar datos rotos (una columna vacía, un
partido que falta, un equipo con 4 jugadores), no pronósticos raros.

Revisar lo ya publicado:  python src/contratos.py"""
import glob

import pandas as pd

from features import OBJETIVOS

TOL = 0.11          # los pronósticos se guardan con un decimal


def revisar_box_scores(p: pd.DataFrame, t: pd.DataFrame) -> tuple:
    """Box scores recién descargados (formato Kaggle): p jugadores, t equipos."""
    err, av = [], []
    if p.duplicated(["personId", "gameId"]).any():
        err.append("jugadores repetidos en un mismo partido")
    por_partido = t.groupby("gameId").size()
    if (por_partido != 2).any():
        err.append(f"partidos sin sus dos equipos: {list(por_partido[por_partido != 2].index)[:5]}")
    if t["teamScore"].isna().any() or (t["teamScore"] < 50).any() or (t["teamScore"] > 200).any():
        err.append("marcador de equipo vacío o fuera de 50-200")
    suma = p.groupby(["gameId", "playerteamId"])["points"].sum()
    real = t.set_index(["gameId", "teamId"])["teamScore"].reindex(suma.index)
    if (suma != real).any():
        err.append(f"los puntos de los jugadores no suman el marcador en {int((suma != real).sum())} equipos-partido")
    mins = p.groupby(["gameId", "playerteamId"])["numMinutes"].sum()
    if (mins < 235).any():
        err.append(f"equipos con menos de 235 minutos jugados: {int((mins < 235).sum())}")
    jugaron = p[p["numMinutes"] > 0].groupby(["gameId", "playerteamId"]).size()
    if (jugaron < 7).any():
        av.append(f"equipos con menos de 7 jugadores con minutos: {int((jugaron < 7).sum())}")
    return err, av


def revisar_pronosticos(pred: pd.DataFrame, juegos: pd.DataFrame, partidos_esperados: int = None) -> tuple:
    """Lo que predict.py está por escribir: pred (una fila por jugador) y juegos (una por partido)."""
    err, av = [], []

    # ---- partidos
    if partidos_esperados is not None and len(juegos) != partidos_esperados:
        err.append(f"se esperaban {partidos_esperados} partidos y hay {len(juegos)}")
    if juegos["gameId"].duplicated().any():
        err.append("partidos repetidos")
    num = ["pts_local", "pts_visita", "total", "spread", "prob_local"]
    if juegos[num].isna().any().any():
        err.append("partidos con pronóstico vacío")
    else:
        if not juegos["prob_local"].between(0.01, 0.99).all():
            err.append("probabilidad de victoria fuera de 0.01-0.99")
        for lado in ("local", "visita"):
            c = juegos[f"pts_{lado}"]
            if not c.between(70, 160).all():
                err.append(f"puntos del {lado} fuera de 70-160")
            if ((juegos[f"pts_{lado}_q10"] > c + TOL) | (juegos[f"pts_{lado}_q90"] < c - TOL)).any():
                err.append(f"el intervalo de puntos del {lado} no contiene al pronóstico")

    # ---- jugadores
    if pred.duplicated(["personId", "gameId"]).any():
        err.append("jugadores repetidos en un mismo partido")
    sin_jugadores = set(juegos["gameId"].astype("int64")) - set(pred["gameId"].astype("int64"))
    if sin_jugadores:
        err.append(f"partidos sin jugadores: {sorted(sin_jugadores)}")
    for obj in OBJETIVOS:
        c, lo, hi = pred[obj], pred[f"{obj}_q10"], pred[f"{obj}_q90"]
        if c.isna().any() or lo.isna().any() or hi.isna().any():
            err.append(f"{obj}: valores vacíos")
            continue
        if (lo < -TOL).any():
            err.append(f"{obj}: valores negativos")
        if ((lo > c + TOL) | (hi < c - TOL)).any():
            err.append(f"{obj}: el intervalo no contiene al pronóstico en {int(((lo > c + TOL) | (hi < c - TOL)).sum())} filas")
    if (pred["numMinutes"] > 48.5).any():
        err.append("minutos pronosticados arriba de 48")
    por_equipo = pred.groupby(["gameId", "playerteamId"]).agg(n=("personId", "size"), mins=("numMinutes", "sum"),
                                                              pts=("points", "sum"))
    if (pred.groupby("gameId")["playerteamId"].nunique() != 2).any():
        err.append("partidos con jugadores de un solo equipo")
    if (por_equipo["n"] < 8).any():
        err.append(f"equipos con menos de 8 jugadores pronosticados: {int((por_equipo['n'] < 8).sum())}")
    if (por_equipo["n"] > 20).any():
        av.append(f"equipos con más de 20 jugadores pronosticados: {int((por_equipo['n'] > 20).sum())}")
    raros = por_equipo[(por_equipo["mins"] < 200) | (por_equipo["mins"] > 340)]
    if len(raros):
        av.append(f"equipos cuyos minutos pronosticados suman menos de 200 o más de 340: {len(raros)}")
    return err, av


def main():
    total_err = 0
    for ruta in sorted(glob.glob("predictions/????-??-??.csv")):
        fecha = ruta[-14:-4]
        err, av = revisar_pronosticos(pd.read_csv(ruta), pd.read_csv(f"predictions/juegos_{fecha}.csv"))
        total_err += len(err)
        print(fecha, "OK" if not err else f"ERRORES: {err}", f"| avisos: {av}" if av else "")
    raise SystemExit(1 if total_err else 0)


if __name__ == "__main__":
    main()
