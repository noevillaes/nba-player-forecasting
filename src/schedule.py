"""Descarga el calendario oficial de la temporada con nba_api y lo guarda limpio.
Fuente independiente de Kaggle: el dataset no se actualiza en el verano."""
import os
import pandas as pd
from nba_api.stats.endpoints import scheduleleaguev2

TEMPORADA = "2026-27"
RAW = "data/raw"
TIPO_POR_PREFIJO = {"1": "preseason", "2": "regular", "3": "allstar",
                    "4": "playoffs", "5": "playin", "6": "cup_final"}


def descargar(temporada: str = TEMPORADA) -> pd.DataFrame:
    for intento in range(3):
        try:
            return scheduleleaguev2.ScheduleLeagueV2(
                league_id="00", season=temporada, timeout=60
            ).get_data_frames()[0]
        except Exception as e:
            print(f"Intento {intento + 1} falló: {e}")
    raise RuntimeError("No se pudo descargar el calendario")


def a_fecha(s: pd.Series) -> pd.Series:
    """Fechas en cualquier formato → fecha sin zona horaria."""
    return pd.to_datetime(s, utc=True, format="mixed").dt.tz_localize(None)


def limpiar(s: pd.DataFrame) -> pd.DataFrame:
    cal = pd.DataFrame({
        "gameId": s["gameId"].astype("int64"),
        "gameDateTimeEst": a_fecha(s["gameDateTimeEst"]),
        "homeTeamId": s["homeTeam_teamId"].astype("int64"),
        "awayTeamId": s["awayTeam_teamId"].astype("int64"),
        "homeTeamName": s["homeTeam_teamName"],
        "awayTeamName": s["awayTeam_teamName"],
        "gameLabel": s["gameLabel"],
        "gameSubLabel": s["gameSubLabel"],
        "isNeutral": s["isNeutral"],
        "gameStatus": s["gameStatus"],  # 1 = programado, 2 = en curso, 3 = final
    })
    cal["fecha"] = cal["gameDateTimeEst"].dt.normalize()
    cal["tipo"] = cal["gameId"].astype(str).str[0].map(TIPO_POR_PREFIJO)
    # Partidos con rival aún por definir (eliminatorias) traen teamId = 0
    cal = cal[(cal["homeTeamId"] > 0) & (cal["awayTeamId"] > 0)]
    return cal.sort_values("gameDateTimeEst").reset_index(drop=True)


def verificar_equipos(cal: pd.DataFrame):
    """Los teamId de la NBA deben ser los mismos que en el dataset de Kaggle."""
    t = pd.read_parquet(f"{RAW}/TeamStatistics.parquet", columns=["teamId", "gameDateTimeEst"])
    recientes = set(t.loc[t["gameDateTimeEst"] >= "2025-10-01", "teamId"].astype("int64"))
    en_calendario = set(cal["homeTeamId"]) | set(cal["awayTeamId"])
    faltan = en_calendario - recientes
    print(f"Equipos en el calendario: {len(en_calendario)} | sin match en Kaggle: {faltan or 'ninguno'}")


def main():
    cal = limpiar(descargar())
    os.makedirs(RAW, exist_ok=True)
    cal.to_parquet(f"{RAW}/schedule_{TEMPORADA.replace('-', '_')}.parquet", index=False)

    print(cal.shape)
    print(cal.groupby("tipo")["fecha"].agg(["count", "min", "max"]).to_string())
    verificar_equipos(cal)
    print("\nPrimeros partidos de temporada regular:")
    print(cal[cal["tipo"] == "regular"][["fecha", "awayTeamName", "homeTeamName"]].head(5).to_string())


if __name__ == "__main__":
    main()