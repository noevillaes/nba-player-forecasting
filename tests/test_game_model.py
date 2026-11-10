"""El rating de equipos solo aprende de partidos anteriores."""
import numpy as np
import pandas as pd

import game_model as gm


def partidos(n=60, semilla=1) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    fuerza = {1: 6.0, 2: 2.0, 3: -2.0, 4: -6.0}
    filas = []
    for g in range(n):
        l, v = rng.choice(list(fuerza), 2, replace=False)
        fecha = pd.Timestamp("2025-10-21") + pd.Timedelta(days=g)
        ritmo = rng.normal(98, 3)
        for eq, riv, casa in ((l, v, 1), (v, l, 0)):
            filas.append({"gameId": 5000 + g, "teamId": int(eq), "opponentTeamId": int(riv), "home": casa,
                          "gameDateTimeEst": fecha, "pace": ritmo,
                          "ortg": 112 + fuerza[eq] - fuerza[riv] / 2 + (1.5 if casa else -1.5) + rng.normal(0, 8)})
    t = pd.DataFrame(filas)
    t["local"], t["temporada"] = t["home"], 2025
    return t


def test_el_rating_previo_no_ve_el_partido_ni_los_posteriores():
    t = partidos()
    a = gm.con_rating(t, t)
    t2 = t.copy()
    t2.loc[t2["gameId"] >= 5030, "ortg"] += 40          # se cambian los resultados de la segunda mitad
    b = gm.con_rating(t2, t2)
    antes = a["gameId"] <= 5030                          # el 5030 incluido: su rating es de antes del partido
    np.testing.assert_allclose(a.loc[antes, "rating_pts"], b.loc[antes, "rating_pts"])
    assert not np.allclose(a.loc[~antes, "rating_pts"], b.loc[~antes, "rating_pts"])


def test_aprende_quien_es_mejor_y_pronostica_partidos_por_jugar():
    t = partidos(400)
    futuro = pd.DataFrame({"gameId": [9001, 9001], "teamId": [1, 4], "opponentTeamId": [4, 1],
                           "local": [1, 0], "temporada": [2025, 2025]})
    d = gm.con_rating(futuro, t)
    assert d["rating_pts"].notna().all()
    assert d["rating_pts"].iloc[0] - d["rating_pts"].iloc[1] > 5      # el mejor equipo, en casa, es favorito claro


def test_temporada_nueva_regresa_a_la_media():
    r = gm.Rating()
    r.nueva_temporada(2024)
    r.ataque[1] = 10.0
    r.nueva_temporada(2025)
    assert np.isclose(r.ataque[1], 10.0 * (1 - gm.REGRESO))
