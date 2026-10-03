"""Descarga los box scores de la temporada en curso con nba_api, partido
por partido, y los guarda con el mismo formato que el dataset de Kaggle.

Uso diario:   python src/ingest_live.py
Validación:   python src/ingest_live.py --validar 22501000
              Descarga un partido que Kaggle ya tiene y compara los números."""
import argparse
import os
import re
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3

from schedule import descargar, limpiar, TEMPORADA

RAW = "data/raw"
ARCH_PLAYER = f"{RAW}/vivo_player.parquet"
ARCH_EXT = f"{RAW}/vivo_extended.parquet"
ARCH_TEAM = f"{RAW}/vivo_team.parquet"

# Prefijo del gameId → (gameType, gameSubLabel) con las etiquetas de Kaggle
GAMETYPE = {"2": ("Regular Season", None), "4": ("Playoffs", None),
            "5": ("Play-in Tournament", None),
            "6": ("Emirates NBA Cup", "Championship")}
STATS = ["points", "assists", "blocks", "steals", "fieldGoalsAttempted",
         "fieldGoalsMade", "threePointersAttempted", "threePointersMade",
         "freeThrowsAttempted", "freeThrowsMade", "reboundsDefensive",
         "reboundsOffensive", "reboundsTotal", "foulsPersonal", "turnovers",
         "plusMinusPoints"]
STATS_EQUIPO = ["fieldGoalsAttempted", "freeThrowsAttempted",
                "reboundsOffensive", "reboundsTotal", "turnovers",
                "assists", "threePointersMade"]


def a_minutos(x) -> float:
    """'34:12', 'PT34M12.00S', '34' o vacío → minutos en decimal."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    s = str(x).strip()
    if s == "":
        return 0.0
    m = re.match(r"PT(\d+)M([\d.]+)S", s)
    if m:
        return int(m[1]) + float(m[2]) / 60
    if ":" in s:
        mm, ss = s.split(":")
        return int(mm) + float(ss) / 60
    return float(s)


def descargar_box(game_id: int):
    for intento in range(3):
        try:
            frames = boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=f"{game_id:010d}", timeout=60).get_data_frames()
            break
        except Exception as e:
            print(f"  partido {game_id}, intento {intento + 1} falló: {e}")
            time.sleep(3)
    else:
        raise RuntimeError(f"No se pudo descargar el partido {game_id}")

    jug = next(f for f in frames if "personId" in f.columns)
    eq = next(f for f in frames if "personId" not in f.columns
              and "teamId" in f.columns and len(f) == 2)
    necesarias = {"personId", "firstName", "familyName", "minutes",
                  "position", "teamId"} | set(STATS)
    faltan = necesarias - set(jug.columns)
    if faltan:
        raise ValueError(f"Columnas inesperadas. Faltan {faltan}. "
                         f"Vienen: {list(jug.columns)}")
    return jug, eq


def a_formato_kaggle(jug, eq, juego):
    """Convierte el box score de nba_api a las tablas de Kaggle."""
    gid = int(juego.gameId)
    local, visita = int(juego.homeTeamId), int(juego.awayTeamId)
    tipo, sub = GAMETYPE[str(gid)[0]]

    jug = jug.copy()
    jug["teamId"] = jug["teamId"].astype("int64")
    p = pd.DataFrame({
        "firstName": jug["firstName"],
        "lastName": jug["familyName"],
        "personId": jug["personId"].astype("int64"),
        "gameId": gid,
        "gameDateTimeEst": juego.gameDateTimeEst,
        "gameType": tipo,
        "gameSubLabel": sub,
        "playerteamId": jug["teamId"],
        "opponentteamId": np.where(jug["teamId"] == local, visita, local),
        "home": (jug["teamId"] == local).astype(int),
        "numMinutes": jug["minutes"].map(a_minutos),
        "startingPosition": jug["position"].replace("", np.nan),
    })
    for c in STATS:
        p[c] = pd.to_numeric(jug[c], errors="coerce")

    # Totales de equipo
    eq = eq.copy()
    eq["teamId"] = eq["teamId"].astype("int64")
    t = pd.DataFrame({
        "gameId": gid,
        "gameDateTimeEst": juego.gameDateTimeEst,
        "gameType": tipo,
        "teamId": eq["teamId"],
        "opponentTeamId": np.where(eq["teamId"] == local, visita, local),
        "home": (eq["teamId"] == local).astype(int),
        "teamScore": pd.to_numeric(eq["points"]),
    })
    for c in STATS_EQUIPO:
        t[c] = pd.to_numeric(eq[c], errors="coerce").to_numpy()
    t["opponentScore"] = t["teamScore"].iloc[::-1].to_numpy()
    t["win"] = (t["teamScore"] > t["opponentScore"]).astype(int)
    t["numMinutes"] = (p.groupby("playerteamId")["numMinutes"].sum()
                       .reindex(t["teamId"]).to_numpy())

    # Uso del jugador (fórmula estándar), igual escala que Kaggle (0-1)
    te = t.set_index("teamId")
    min_eq = p["playerteamId"].map(te["numMinutes"])
    pos_eq = p["playerteamId"].map(te["fieldGoalsAttempted"]
                                   + 0.44 * te["freeThrowsAttempted"]
                                   + te["turnovers"])
    pos_jug = (p["fieldGoalsAttempted"] + 0.44 * p["freeThrowsAttempted"]
               + p["turnovers"])
    uso = (pos_jug * (min_eq / 5)) / (p["numMinutes"] * pos_eq)
    jugaron = p["numMinutes"] > 0
    e = pd.DataFrame({"personId": p.loc[jugaron, "personId"],
                      "gameId": gid,
                      "usagePercentage": uso[jugaron]})
    return p, e, t


def anexar(nuevo: pd.DataFrame, ruta: str, llave: list):
    if os.path.exists(ruta):
        nuevo = pd.concat([pd.read_parquet(ruta), nuevo], ignore_index=True)
    nuevo.drop_duplicates(llave, keep="last").to_parquet(ruta, index=False)


def actualizar():
    cal = limpiar(descargar())
    cal.to_parquet(f"{RAW}/schedule_{TEMPORADA.replace('-', '_')}.parquet", index=False)

    ya = set()
    if os.path.exists(ARCH_PLAYER):
        ya = set(pd.read_parquet(ARCH_PLAYER, columns=["gameId"])["gameId"])
    validos = ["regular", "playoffs", "playin", "cup_final"]
    pendientes = cal[(cal["gameStatus"] == 3) & cal["tipo"].isin(validos)
                     & ~cal["gameId"].isin(ya)]
    print(f"Partidos terminados por descargar: {len(pendientes)}")
    if pendientes.empty:
        return

    ps, es, ts = [], [], []
    for juego in pendientes.itertuples():
        jug, eq = descargar_box(juego.gameId)
        p, e, t = a_formato_kaggle(jug, eq, juego)
        ps.append(p)
        es.append(e)
        ts.append(t)
        print(f"  {juego.fecha.date()} {juego.awayTeamName} @ {juego.homeTeamName}")
        time.sleep(0.7)

    anexar(pd.concat(ps), ARCH_PLAYER, ["personId", "gameId"])
    anexar(pd.concat(es), ARCH_EXT, ["personId", "gameId"])
    anexar(pd.concat(ts), ARCH_TEAM, ["teamId", "gameId"])
    print("Box scores en vivo actualizados.")


def validar(game_id: int):
    """Descarga un partido que Kaggle ya tiene y compara número por número."""
    from clean import parsear_minutos

    ps = pd.read_parquet(f"{RAW}/PlayerStatistics.parquet")
    ext = pd.read_parquet(f"{RAW}/PlayerStatisticsExtended.parquet",
                          columns=["personId", "gameId", "usagePercentage"])
    ts = pd.read_parquet(f"{RAW}/TeamStatistics.parquet")
    k = ps[ps["gameId"].astype("int64") == game_id].copy()
    kt = ts[ts["gameId"].astype("int64") == game_id]
    if k.empty:
        raise SystemExit(f"Kaggle no tiene el partido {game_id}")

    juego = SimpleNamespace(
        gameId=game_id,
        homeTeamId=int(kt.loc[kt["home"] == 1, "teamId"].iloc[0]),
        awayTeamId=int(kt.loc[kt["home"] == 0, "teamId"].iloc[0]),
        gameDateTimeEst=kt["gameDateTimeEst"].iloc[0])
    jug, eq = descargar_box(game_id)
    p, e, t = a_formato_kaggle(jug, eq, juego)

    k["personId"] = k["personId"].astype("int64")
    k["numMinutes"] = parsear_minutos(k["numMinutes"]).fillna(0)
    m = p.merge(k, on="personId", suffixes=("_api", "_kaggle"))
    print(f"Jugadores: nba_api {len(p)} | Kaggle {len(k)} | en ambos {len(m)}")
    for c in ["numMinutes", "points", "reboundsTotal", "assists",
              "threePointersMade", "turnovers"]:
        dif = (m[f"{c}_api"].fillna(0) - m[f"{c}_kaggle"].fillna(0)).abs()
        print(f"  {c:20s} diferencia máxima: {dif.max():.2f}")
    titulares = (m["startingPosition_api"].notna() == m["startingPosition_kaggle"].notna()).mean()
    print(f"  titulares coinciden: {titulares:.0%}")

    ext["personId"] = ext["personId"].astype("int64")
    u = e.merge(ext[ext["gameId"].astype("int64") == game_id],
                on="personId", suffixes=("_api", "_kaggle"))
    dif_u = (u["usagePercentage_api"] - u["usagePercentage_kaggle"]).abs()
    print(f"  uso (usagePercentage)  diferencia media: {dif_u.mean():.3f} "
          f"| máxima: {dif_u.max():.3f}")

    tm = t.merge(kt.assign(teamId=kt["teamId"].astype("int64")),
                 on="teamId", suffixes=("_api", "_kaggle"))
    for c in ["teamScore", "fieldGoalsAttempted", "turnovers"]:
        dif = (tm[f"{c}_api"] - pd.to_numeric(tm[f"{c}_kaggle"])).abs().max()
        print(f"  equipo {c:20s} diferencia máxima: {dif:.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validar", type=int, help="gameId que Kaggle ya tenga")
    args = ap.parse_args()
    if args.validar:
        validar(args.validar)
    else:
        actualizar()


if __name__ == "__main__":
    main()