"""Plantillas actuales de los 30 equipos vía nba_api: quién juega dónde hoy.
Resuelve traspasos, fichajes y novatos del verano."""
import os
import time
import pandas as pd
from nba_api.stats.endpoints import commonteamroster

TEMPORADA = "2026-27"
RAW = "data/raw"
CLEAN = "data/clean"


def roster_equipo(team_id: int, temporada: str) -> pd.DataFrame:
    for intento in range(3):
        try:
            return commonteamroster.CommonTeamRoster(
                team_id=team_id, season=temporada, timeout=60
            ).get_data_frames()[0]
        except Exception as e:
            print(f"  equipo {team_id}, intento {intento + 1} falló: {e}")
            time.sleep(3)
    raise RuntimeError(f"No se pudo descargar la plantilla del equipo {team_id}")


def main():
    cal = pd.read_parquet(f"{RAW}/schedule_{TEMPORADA.replace('-', '_')}.parquet")
    reg = cal[cal["tipo"] == "regular"]
    equipos = sorted(set(reg["homeTeamId"]) | set(reg["awayTeamId"]))
    print(f"Descargando {len(equipos)} plantillas...")

    partes = []
    for tid in equipos:
        partes.append(roster_equipo(tid, TEMPORADA))
        time.sleep(0.7)  # pausa para no saturar la API

    ros = pd.concat(partes, ignore_index=True).rename(columns={
        "TeamID": "teamId", "PLAYER_ID": "personId", "PLAYER": "jugador",
        "POSITION": "posicion", "AGE": "edad", "EXP": "experiencia"})
    ros = ros[["teamId", "personId", "jugador", "posicion", "edad", "experiencia"]]
    ros["teamId"] = ros["teamId"].astype("int64")
    ros["personId"] = ros["personId"].astype("int64")

    dup = ros["personId"].duplicated().sum()
    if dup:
        print(f"Aviso: {dup} jugadores aparecen en más de un equipo")

    # Comparar con el último equipo de cada jugador en el historial
    hist = pd.read_parquet(f"{CLEAN}/player_games.parquet",
                           columns=["personId", "playerteamId", "gameDateTimeEst"])
    hist["personId"] = hist["personId"].astype("int64")
    ultimo = (hist.sort_values("gameDateTimeEst")
                  .groupby("personId")["playerteamId"].last().astype("int64"))
    ros["ultimo_equipo"] = ros["personId"].map(ultimo)
    ros["tiene_historial"] = ros["ultimo_equipo"].notna()
    ros["cambio_equipo"] = ros["tiene_historial"] & (ros["ultimo_equipo"] != ros["teamId"])

    os.makedirs(RAW, exist_ok=True)
    ros.to_parquet(f"{RAW}/rosters_{TEMPORADA.replace('-', '_')}.parquet", index=False)

    print(f"\n{len(ros)} jugadores en {ros['teamId'].nunique()} equipos "
          f"({ros.groupby('teamId').size().min()}-{ros.groupby('teamId').size().max()} por equipo)")
    print(f"Con historial: {ros['tiene_historial'].sum()} | "
          f"sin historial (novatos u otras ligas): {(~ros['tiene_historial']).sum()}")
    print(f"Cambiaron de equipo en el verano: {ros['cambio_equipo'].sum()}")
    print("\nAlgunos sin historial:")
    print(ros.loc[~ros["tiene_historial"], ["jugador", "posicion", "edad", "experiencia"]]
             .head(8).to_string(index=False))


if __name__ == "__main__":
    main()