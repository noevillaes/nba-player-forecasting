"""La regla de oro del proyecto: ningún feature usa información del partido que pronostica."""
import numpy as np
import pandas as pd

import features


def jugadores(n_jug=4, n_part=30, semilla=0) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    filas = []
    for p in range(n_jug):
        for g in range(n_part):
            mins = float(rng.integers(0, 38))
            f = {"personId": 100 + p, "firstName": "J", "lastName": str(p), "gameId": 1000 + g,
                 "gameDateTimeEst": pd.Timestamp("2025-10-21") + pd.Timedelta(days=2 * g),
                 "temporada": 2025, "tipo": "regular", "playerteamId": 1 + p % 2, "opponentteamId": 2 - p % 2,
                 "home": g % 2, "numMinutes": mins, "jugo": mins > 0, "titular": mins > 25,
                 "usagePercentage": rng.uniform(0.1, 0.3)}
            for s in features.STATS:
                f[s] = float(rng.poisson(mins / 6)) if mins else 0.0
            filas.append(f)
    return pd.DataFrame(filas)


def columnas_de_features(t: pd.DataFrame) -> list:
    return [c for c in t.columns if c not in features.IDS and not c.startswith("y_") and c != "es_futuro"]


def test_cambiar_un_partido_no_cambia_sus_propios_features():
    base = jugadores()
    cambiado = base.copy()
    objetivo = (cambiado["personId"] == 101) & (cambiado["gameId"] == 1015)
    cambiado.loc[objetivo, ["numMinutes", "points", "assists", "reboundsTotal", "usagePercentage"]] = [48.0, 60.0, 20.0, 25.0, 0.9]
    cambiado.loc[objetivo, ["jugo", "titular"]] = True

    a, b = features.construir(base), features.construir(cambiado)
    cols = columnas_de_features(a)
    fila = lambda t: t[(t["personId"] == 101) & (t["gameId"] == 1015)][cols].to_numpy(float)
    np.testing.assert_allclose(fila(a), fila(b), equal_nan=True)

    # y sí cambia los del partido siguiente (el feature existe y mira hacia atrás)
    sig = lambda t: t[(t["personId"] == 101) & (t["gameId"] == 1016)]["min_ultimo"].iloc[0]
    assert sig(a) != sig(b) and sig(b) == 48.0


def test_fila_futura_recibe_features_solo_del_pasado():
    hist = jugadores()
    fut = hist[hist["gameId"] == 1029].copy()
    pasado = hist[hist["gameId"] < 1029].assign(es_futuro=False)
    fut[features.STATS + ["usagePercentage", "jugo", "titular"]] = np.nan
    fut["numMinutes"], fut["es_futuro"] = 0.0, True

    con_futuro = features.construir(pd.concat([pasado, fut], ignore_index=True))
    real = features.construir(hist)
    cols = columnas_de_features(real)
    f = con_futuro[con_futuro["es_futuro"]].sort_values("personId")
    r = real[real["gameId"] == 1029].sort_values("personId")
    np.testing.assert_allclose(f[cols].to_numpy(float), r[cols].to_numpy(float), equal_nan=True)
    assert f[[c for c in f.columns if c.startswith("y_")]].isna().all().all()     # sin objetivos
