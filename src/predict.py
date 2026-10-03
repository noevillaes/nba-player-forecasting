"""Genera pronósticos (con intervalo del 80% calibrado) para una fecha.

En vivo:    python src/predict.py --fecha 2026-10-20
            Partidos del calendario × plantillas actuales.
Backtest:   python src/predict.py --fecha 2026-03-10 --backtest
            Finge que es esa fecha usando solo la historia previa y
            compara contra lo que realmente pasó.

Los features se calculan con EXACTAMENTE el mismo código que en el
entrenamiento (features.construir y team_features), así que no hay
diferencias entre cómo se entrena y cómo se pronostica."""
import argparse
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import features
import team_features
from clean import temporada as temporada_de
from conformal import entrenar, predecir, NIVEL
from evaluate import datos_evaluables, agregar_b1, cargar, OBJETIVOS
from reconcile import factor_k
from models import columnas_features, VENTANA_TRAIN

CLEAN = "data/clean/player_games.parquet"
RAW = "data/raw"
MODELOS = Path("models")
SALIDA = Path("predictions")
TIPOS_VALIDOS = ["regular", "playoffs", "playin"]
LAMBDA_RECONCILIACION = 0.5  # elegido en validación 2015-2018


# ---------- Filas futuras ----------

def filas_vivo(fecha: pd.Timestamp) -> pd.DataFrame:
    """Partidos del calendario en esa fecha × plantilla actual de cada equipo."""
    cal = pd.read_parquet(f"{RAW}/schedule_2026_27.parquet")
    ros = pd.read_parquet(f"{RAW}/rosters_2026_27.parquet")
    juegos = cal[(cal["fecha"] == fecha) & cal["tipo"].isin(TIPOS_VALIDOS)]
    if juegos.empty:
        raise SystemExit(f"No hay partidos de temporada el {fecha.date()}")

    partes = []
    for local, eq, riv in [(1, "homeTeamId", "awayTeamId"),
                           (0, "awayTeamId", "homeTeamId")]:
        j = juegos[["gameId", "gameDateTimeEst", "tipo", eq, riv]].rename(
            columns={eq: "playerteamId", riv: "opponentteamId"})
        j["home"] = local
        j = j.merge(ros[["teamId", "personId", "jugador"]],
                    left_on="playerteamId", right_on="teamId").drop(columns="teamId")
        partes.append(j)
    fut = pd.concat(partes, ignore_index=True)
    nombre = fut["jugador"].str.split(" ", n=1)
    fut["firstName"], fut["lastName"] = nombre.str[0], nombre.str[1]
    return fut.drop(columns="jugador")


def vaciar(fut: pd.DataFrame) -> pd.DataFrame:
    """Borra todo lo que no se conoce antes del partido."""
    fut = fut.copy()
    fut["temporada"] = temporada_de(fut["gameDateTimeEst"])
    fut["numMinutes"] = 0.0  # marcador: el valor propio nunca se usa (shift(1))
    for c in features.STATS + ["usagePercentage"]:
        fut[c] = np.nan
    fut["jugo"] = np.nan
    fut["titular"] = np.nan
    fut["es_futuro"] = True
    return fut


# ---------- Tabla de features ----------

def construir_tabla(hist, fut, fecha) -> pd.DataFrame:
    p = pd.concat([hist.assign(es_futuro=False), fut], ignore_index=True)
    pf = features.construir(p)

    desde = str(hist["gameDateTimeEst"].min().date())
    t = team_features.cargar_equipos(desde=desde)
    t = t[t["gameDateTimeEst"] < fecha]
    eq = team_features.construir_equipos(t, futuros=pf[pf["es_futuro"]])

    tabla = agregar_b1(team_features.unir(pf, eq))
    return tabla[tabla["es_futuro"]].copy()


# ---------- Modelo: se entrena una vez por temporada y se guarda ----------

def asegurar_k_mediana(paquete: dict, objetivo: int, ruta: Path) -> dict:
    """Mediana de k en la temporada de calibración, para la reconciliación.
    Se calcula una vez y se guarda junto al modelo."""
    if "k_mediana" in paquete:
        return paquete
    print("Calculando la referencia para la reconciliación (solo esta vez)...")
    todo = cargar()
    calib = todo[(todo["temporada"] == objetivo - 1) & todo["min_prom_10"].notna()]
    pc = predecir(paquete["modelos"]["points"], calib[paquete["cols"]], "points")
    paquete["k_mediana"] = float(factor_k(calib, pc["points"]).median())
    print(f"  k mediana: {paquete['k_mediana']:.3f}")
    joblib.dump(paquete, ruta)
    return paquete


def obtener_modelo(objetivo: int) -> dict:
    ruta = MODELOS / f"modelo_{objetivo}.joblib"
    if ruta.exists():
        return asegurar_k_mediana(joblib.load(ruta), objetivo, ruta)

    print(f"Entrenando modelo para la temporada {objetivo} (solo esta vez)...")
    df = datos_evaluables()
    calib = df[df["temporada"] == objetivo - 1]
    fit = df[(df["temporada"] < objetivo - 1)
             & (df["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    cols = columnas_features(fit)

    paquete = {"cols": cols, "modelos": {}, "ajuste": {}}
    for obj in OBJETIVOS:
        mods = entrenar(fit, cols, obj)
        pc = predecir(mods, calib[cols], obj)
        y = calib[f"y_{obj}"]
        E = np.maximum(pc[f"{obj}_q10"] - y, y - pc[f"{obj}_q90"])
        q = float(np.quantile(E, min(1.0, NIVEL * (1 + 1 / len(E)))))
        paquete["modelos"][obj] = mods
        paquete["ajuste"][obj] = q
        print(f"  {obj}: ajuste conformal {q:+.2f}")

    MODELOS.mkdir(exist_ok=True)
    joblib.dump(paquete, ruta)
    return asegurar_k_mediana(paquete, objetivo, ruta)


def pronosticar(tabla: pd.DataFrame, paquete: dict) -> pd.DataFrame:
    X = tabla[paquete["cols"]]
    out = tabla[["fecha", "gameId", "personId", "firstName", "lastName",
                 "playerteamId", "opponentteamId", "local"]].copy()
    out["con_historial"] = tabla["min_prom_10"].notna()
    for obj in OBJETIVOS:
        p = predecir(paquete["modelos"][obj], X, obj)
        q = paquete["ajuste"][obj]
        out[obj] = p[obj]
        out[f"{obj}_q10"] = (p[f"{obj}_q10"] - q).clip(lower=0)
        out[f"{obj}_q90"] = p[f"{obj}_q90"] + q
        out[f"{obj}_base"] = tabla[f"b1_{obj}"]

    # Reconciliación de puntos con el total esperado del equipo
    con_hist = out["con_historial"]
    k = factor_k(tabla[con_hist], out.loc[con_hist, "points"])
    k_rel = (k / paquete["k_mediana"]).reindex(out.index).fillna(1.0).clip(0.5, 1.5)
    out["ajuste_equipo"] = k_rel ** LAMBDA_RECONCILIACION
    for c in ["points", "points_q10", "points_q90"]:
        out[c] = out[c] * out["ajuste_equipo"]

    columnas_num = [c for c in out.columns if c.startswith(tuple(OBJETIVOS))]
    out[columnas_num] = out[columnas_num].round(1)
    out["ajuste_equipo"] = out["ajuste_equipo"].round(3)
    return out


def nombres_equipos() -> pd.Series:
    t = pd.read_parquet(f"{RAW}/TeamStatistics.parquet",
                        columns=["teamId", "teamName", "gameDateTimeEst"])
    n = t.sort_values("gameDateTimeEst").groupby("teamId")["teamName"].last()
    n.index = n.index.astype("int64")
    return n


def comparar(pred: pd.DataFrame, reales: pd.DataFrame):
    r = reales[reales["jugo"].astype(bool)]
    m = pred.merge(r, on=["personId", "gameId"], suffixes=("", "_real"))
    filas = []
    for obj in OBJETIVOS:
        y = m[f"{obj}_real"]
        filas.append({
            "objetivo": obj,
            "MAE": (m[obj] - y).abs().mean(),
            "cobertura_80": ((y >= m[f"{obj}_q10"]) & (y <= m[f"{obj}_q90"])).mean(),
        })
    print(f"\nComparación con lo que pasó ({len(m)} jugadores que jugaron):")
    print(pd.DataFrame(filas).round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser(description="Pronósticos por jugador para una fecha")
    ap.add_argument("--fecha", required=True, help="AAAA-MM-DD")
    ap.add_argument("--backtest", action="store_true",
                    help="fingir que es esa fecha y comparar con lo real")
    args = ap.parse_args()

    fecha = pd.Timestamp(args.fecha)
    objetivo = int(temporada_de(pd.Series([fecha])).iloc[0])

    hist = pd.read_parquet(CLEAN)
    hist = hist[hist["temporada"] >= objetivo - 2]
    es_dia = hist["gameDateTimeEst"].dt.normalize() == fecha

    reales = None
    if args.backtest:
        if not es_dia.any():
            raise SystemExit(f"No hubo partidos el {fecha.date()}")
        dia = hist[es_dia]
        reales = dia[["personId", "gameId", "jugo"] + OBJETIVOS].copy()
        fut = vaciar(dia)
    else:
        fut = vaciar(filas_vivo(fecha))
    hist = hist[hist["gameDateTimeEst"].dt.normalize() < fecha]
    print(f"Temporada {objetivo} | {fut['gameId'].nunique()} partidos | "
          f"{len(fut)} jugadores en plantilla")

    tabla = construir_tabla(hist, fut, fecha)
    paquete = obtener_modelo(objetivo)
    pred = pronosticar(tabla, paquete)

    sin_hist = int((~pred["con_historial"]).sum())
    pred = pred[pred["con_historial"]].drop(columns="con_historial")
    nombres = nombres_equipos()
    pred.insert(5, "equipo", pred["playerteamId"].astype("int64").map(nombres))
    pred.insert(6, "rival", pred["opponentteamId"].astype("int64").map(nombres))
    pred["generado"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    SALIDA.mkdir(exist_ok=True)
    ruta = SALIDA / f"{fecha.date()}{'_backtest' if args.backtest else ''}.csv"
    pred.to_csv(ruta, index=False)
    print(f"\nGuardado: {ruta} ({len(pred)} jugadores; "
          f"{sin_hist} sin historial omitidos)")
    print(pred.sort_values("points", ascending=False)[
        ["firstName", "lastName", "equipo", "rival", "numMinutes",
         "points", "points_q10", "points_q90"]].head(10).to_string(index=False))

    if reales is not None:
        comparar(pred, reales)


if __name__ == "__main__":
    main()