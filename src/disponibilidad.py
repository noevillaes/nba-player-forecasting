"""Disponibilidad: quién no va a jugar y qué pasa con eso.

En vivo, los que el reporte de lesiones de la mañana da como Out o Doubtful
(predictions/lesiones_<fecha>.csv, de lineas.py). En el histórico, los de rotación
(MINUTOS_ROTACION o más minutos por partido en sus últimos 10) que no jugaron.

Se usa en tres lugares:
  1. No se pronostica a los que no van a jugar.
  2. Al reconciliar con el total del equipo no suman (reconcile.factor_k): lo que
     iban a producir se reparte entre los que sí juegan.
     Temporada 2026-27, modelo v2 sin verla, λ 0.5: puntos 4.393 -> 4.380.
  3. El marcador de cada equipo resta a·(puntos esperados de sus ausentes) y suma
     b·(los del rival) (game_model.py). Margen 12.570 -> 12.514 en 2026-27; mejor
     en 6 de 7 temporadas de validación.

Lo que NO funcionó (8 nov 2026): usarlas como features del modelo de jugadores (v3).
Ayudaba en 2025 (minutos 4.77 -> 4.69) pero no en la temporada en vivo (4.738 -> 4.739),
con ninguna definición de ausencia: en vivo la plantilla trae filas de 0 minutos para
los lesionados, que en el box score histórico casi nunca aparecen."""
import re
import unicodedata
from pathlib import Path

import pandas as pd

MINUTOS_ROTACION = 10.0
LESIONES = "predictions/lesiones_{fecha}.csv"
SUFIJO = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def ausentes_historicos(t: pd.DataFrame) -> pd.Series:
    return (t["y_jugo"] == 0) & (t["min_prom_10"] >= MINUTOS_ROTACION)


def por_equipo(t: pd.DataFrame, ausente: pd.Series = None) -> pd.DataFrame:
    """Puntos esperados que faltan por equipo-partido (para el modelo de partidos)."""
    if ausente is None:
        ausente = ausentes_historicos(t)
    x = t[["gameId", "playerteamId"]].copy()
    x["aus_pts"] = ausente.fillna(False).astype(float) * t["points_pm_10"].fillna(0) * t["min_prom_10"].fillna(0)
    g = x.groupby(["gameId", "playerteamId"])["aus_pts"].sum().reset_index()
    g = g.rename(columns={"playerteamId": "teamId"})
    g[["gameId", "teamId"]] = g[["gameId", "teamId"]].astype("int64")
    return g


# ---------------------------------------------------------------- en vivo
def clave(nombre: str) -> str:
    n = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    n = SUFIJO.sub("", re.sub(r"[^a-z ]", "", n.replace("-", " ")))
    return " ".join(n.split())


def reporte(fecha: str) -> pd.DataFrame:
    """El reporte de lesiones de esa mañana (vacío si no lo hay)."""
    ruta = Path(LESIONES.format(fecha=fecha))
    if not ruta.exists():
        return pd.DataFrame(columns=["jugador", "equipo", "estado"])
    r = pd.read_csv(ruta)
    r["clave"] = r["jugador"].map(clave)
    return r


def ausentes_vivo(tabla: pd.DataFrame, fecha: str) -> pd.Series:
    """True para los jugadores de hoy que el reporte de la mañana da como Out o Doubtful."""
    r = reporte(fecha)
    fuera = set(r.loc[r["estado"].isin(["Out", "Doubtful"]), "clave"])
    nombres = (tabla["firstName"].fillna("") + " " + tabla["lastName"].fillna("")).map(clave)
    return nombres.isin(fuera)
