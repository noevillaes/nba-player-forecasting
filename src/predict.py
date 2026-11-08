"""Genera pronósticos (con intervalo del 80% calibrado) para una fecha:
jugadores (16 estadísticas) y partidos (marcador, total, diferencia y
probabilidad de victoria del local).

En vivo:    python src/predict.py --fecha 2026-10-20
Backtest:   python src/predict.py --fecha 2026-03-10 --backtest

Los features se calculan con EXACTAMENTE el mismo código que en el
entrenamiento, así que no hay diferencias entre entrenar y pronosticar."""
import argparse
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import disponibilidad
import explicar
import features
import game_model
import mezcla
import registro
import team_features
from clean import temporada as temporada_de
from conformal import entrenar, predecir, NIVEL
from evaluate import datos_evaluables, agregar_b1, cargar, OBJETIVOS
from models import columnas_features, VENTANA_TRAIN
from reconcile import factor_k, clave_k, RECONCILIADAS, VERSION_K

CLEAN = "data/clean/player_games.parquet"
RAW = "data/raw"
MODELOS = Path("models")
SALIDA = Path("predictions")
TIPOS_VALIDOS = ["regular", "playoffs", "playin"]


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

def construir_tabla(hist, fut, fecha):
    """Devuelve (filas futuras de jugador con features, features de equipo)."""
    p = pd.concat([hist.assign(es_futuro=False), fut], ignore_index=True)
    pf = features.construir(p)

    desde = str(hist["gameDateTimeEst"].min().date())
    t = team_features.cargar_equipos(desde=desde)
    t = t[t["gameDateTimeEst"] < fecha]
    eq = team_features.construir_equipos(t, futuros=pf[pf["es_futuro"]])

    tabla = agregar_b1(team_features.unir(pf, eq))
    return tabla[tabla["es_futuro"]].copy(), eq


# ---------- Modelos: se entrenan una vez por temporada y se guardan ----------

def asegurar_k_mediana(paquete: dict, objetivo: int, ruta: Path) -> dict:
    """Referencias para reconciliar puntos, rebotes y asistencias (se calculan una vez)."""
    if paquete.get("version_k") != VERSION_K:          # se calcularon con otra regla: se rehacen
        faltan = list(RECONCILIADAS)
    else:
        faltan = [s for s in RECONCILIADAS if clave_k(s) not in paquete]
    if not faltan:
        return paquete
    print(f"Calculando la referencia para reconciliar {', '.join(faltan)} (solo esta vez)...")
    todo = cargar()
    calib = todo[(todo["temporada"] == objetivo - 1) & todo["min_prom_10"].notna()]
    for s in faltan:
        pc = predecir(paquete["modelos"][s], calib[paquete["cols"]], s)
        paquete[clave_k(s)] = float(factor_k(calib, pc[s], s, disponibilidad.ausentes_historicos(calib)).median())
    paquete["version_k"] = VERSION_K
    joblib.dump(paquete, ruta)
    return paquete


def obtener_modelo(objetivo: int) -> tuple:
    """(paquete, versión) de la versión activa en results/registro_modelos.json.
    La v1 se entrena sola la primera vez; las demás las crea reentrenar.py."""
    version, ruta = registro.version_activa(objetivo)
    if ruta.exists():
        return asegurar_k_mediana(joblib.load(ruta), objetivo, ruta), version
    if version != "v1":
        raise SystemExit(f"Falta {ruta} (versión {version}). "
                         "Créala con: python src/reentrenar.py --inicio")

    print(f"Entrenando modelo de jugadores para {objetivo} (solo esta vez)...")
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
    return asegurar_k_mediana(paquete, objetivo, ruta), version


def obtener_paquete_juegos(objetivo: int) -> dict:
    ruta = MODELOS / f"juegos_{objetivo}.joblib"
    if ruta.exists():
        paq = joblib.load(ruta)
        if "aus_coef" in paq:
            return paq
        print("El modelo de partidos no tiene el ajuste por ausencias: se recalibra (solo esta vez)...")
    print(f"Calibrando el modelo de partidos para {objetivo} (solo esta vez)...")
    paq = game_model.entrenar_paquete(game_model.historico(), objetivo)
    MODELOS.mkdir(exist_ok=True)
    joblib.dump(paq, ruta)
    return paq


# ---------- Pronósticos ----------

def pronosticar(tabla: pd.DataFrame, paquete: dict, recalibracion: dict = None,
                fuera: pd.Series = None) -> pd.DataFrame:
    """recalibracion: {objetivo: puntos} de recalibrar.py; ensancha (o angosta)
    los intervalos ya publicados según los errores recientes en vivo.
    fuera: los que no van a jugar; no cuentan al repartir el total del equipo."""
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

    # Por qué: contribuciones del modelo central, antes de los ajustes de equipo
    for obj in explicar.EXPLICADAS:
        out[f"pq_{obj}"] = explicar.explicar(paquete["modelos"][obj][""], X)

    # Reconciliación con el total esperado del equipo: puntos, rebotes y asistencias
    con_hist = out["con_historial"]
    for stat, lam in RECONCILIADAS.items():
        if clave_k(stat) not in paquete:
            continue
        k = factor_k(tabla[con_hist], out.loc[con_hist, stat], stat, fuera)
        k_rel = (k / paquete[clave_k(stat)]).reindex(out.index).fillna(1.0).clip(0.5, 1.5)
        factor = k_rel ** lam
        if stat == "points":
            out["ajuste_equipo"] = factor
        partes = [stat] + (["reboundsOffensive", "reboundsDefensive"] if stat == "reboundsTotal" else [])
        for p in partes:
            for c in [p, f"{p}_q10", f"{p}_q90"]:
                out[c] = out[c] * factor

    # Recalibración semanal con los errores en vivo (sobre el intervalo final)
    for obj, a in (recalibracion or {}).items():
        lo, hi = (a, a) if isinstance(a, (int, float)) else a     # [abajo, arriba] desde la v3
        out[f"{obj}_q10"] = np.minimum((out[f"{obj}_q10"] - lo).clip(lower=0), out[obj])
        out[f"{obj}_q90"] = np.maximum(out[f"{obj}_q90"] + hi, out[obj])

    columnas_num = [c for c in out.columns if c.startswith(tuple(OBJETIVOS)) and not c.startswith("pq_")]
    out[columnas_num] = out[columnas_num].round(1)
    out["ajuste_equipo"] = out["ajuste_equipo"].round(3)
    return out


def pronosticar_juegos(fut, eq, objetivo, nombres, ausencias=None) -> pd.DataFrame:
    t = (fut[["gameId", "playerteamId", "opponentteamId", "home", "gameDateTimeEst"]]
         .drop_duplicates(["gameId", "playerteamId"])
         .rename(columns={"playerteamId": "teamId", "opponentteamId": "opponentTeamId"}))
    d = game_model.con_ausencias(game_model.tabla_equipos(t, eq), ausencias)
    j = game_model.pronosticar_partidos(d, obtener_paquete_juegos(objetivo))
    out = pd.DataFrame({
        "fecha": j["gameDateTimeEst_local"].dt.normalize(),
        "gameId": j["gameId"],
        "local": j["teamId_local"].map(nombres),
        "visitante": j["teamId_visita"].map(nombres),
        "pts_local": j["pts_local"],
        "pts_local_q10": j["pts_q10_local"],
        "pts_local_q90": j["pts_q90_local"],
        "pts_visita": j["pts_visita"],
        "pts_visita_q10": j["pts_q10_visita"],
        "pts_visita_q90": j["pts_q90_visita"],
        "total": j["total"],
        "spread": j["spread"],
        "prob_local": j["prob_local"],
    })
    num = [c for c in out.columns if c.startswith(("pts_", "total", "spread"))]
    out[num] = out[num].round(1)
    out["prob_local"] = out["prob_local"].round(3)
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
    ap = argparse.ArgumentParser(description="Pronósticos de jugadores y partidos")
    ap.add_argument("--fecha", required=True, help="AAAA-MM-DD")
    ap.add_argument("--backtest", action="store_true",
                    help="fingir que es esa fecha y comparar con lo real")
    args = ap.parse_args()

    fecha = pd.Timestamp(args.fecha)
    objetivo = int(temporada_de(pd.Series([fecha])).iloc[0])
    sufijo = "_backtest" if args.backtest else ""

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

    tabla, eq = construir_tabla(hist, fut, fecha)
    # Quién falta: en vivo, los Out del reporte de la mañana; en backtest, los de rotación que no jugaron
    if args.backtest:
        no_jugo = set(reales.loc[~reales["jugo"].astype(bool), "personId"])
        fuera = tabla["personId"].isin(no_jugo) & (tabla["min_prom_10"] >= disponibilidad.MINUTOS_ROTACION)
    else:
        fuera = disponibilidad.ausentes_vivo(tabla, str(fecha.date()))
    ausencias = disponibilidad.por_equipo(tabla, fuera)
    print(f"Fuera según el reporte: {int(fuera.sum())} jugadores")
    nombres = nombres_equipos()
    generado = datetime.now().strftime("%Y-%m-%d %H:%M")
    SALIDA.mkdir(exist_ok=True)

    # Jugadores
    paquete, version = obtener_modelo(objetivo)
    recal = {} if args.backtest else registro.ajuste_vigente(
        registro.temporada(registro.cargar(), objetivo), version, str(fecha.date()))
    print(f"Modelo {version}" + (f" con recalibración de {len(recal)} estadísticas" if recal else ""))
    pred = pronosticar(tabla, paquete, recal, fuera)
    pred = pred[~fuera.reindex(pred.index, fill_value=False)]   # los que no van a jugar no se pronostican
    sin_hist = int((~pred["con_historial"]).sum())
    pred = pred[pred["con_historial"]].drop(columns="con_historial")
    pred.insert(5, "equipo", pred["playerteamId"].astype("int64").map(nombres))
    pred.insert(6, "rival", pred["opponentteamId"].astype("int64").map(nombres))
    pred["modelo"] = version
    pred["generado"] = generado

    # Partidos
    juegos = pronosticar_juegos(fut, eq, objetivo, nombres, ausencias)
    juegos["generado"] = generado

    # El modelo mezclado con el mercado de apuestas (solo en vivo; ver mezcla.py)
    if not args.backtest:
        juegos, pred = mezcla.mezclar(juegos, pred, str(fecha.date()))

    ruta = SALIDA / f"{fecha.date()}{sufijo}.csv"
    pred.to_csv(ruta, index=False)
    print(f"\nGuardado: {ruta} ({len(pred)} jugadores; {sin_hist} sin historial omitidos)")
    ruta_j = SALIDA / f"juegos_{fecha.date()}{sufijo}.csv"
    juegos.to_csv(ruta_j, index=False)
    print(f"Guardado: {ruta_j} ({len(juegos)} partidos)")
    print(juegos[["visitante", "local", "pts_visita", "pts_local", "total",
                  "spread", "prob_local"]].to_string(index=False))

    if reales is not None:
        comparar(pred, reales)


if __name__ == "__main__":
    main()