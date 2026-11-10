"""El diseño "jugados" (jugadores v4): los features no cambian si la fuente trae o no
filas de 0 minutos. El box score en vivo trae más de esas filas que el histórico."""
import numpy as np
import pytest

import features
from test_features_sin_fuga import jugadores

NUEVAS = lambda t: [c for c in t.columns if c.startswith(features.PREFIJOS_JUGADOS)]


def test_quitar_las_filas_de_cero_minutos_no_cambia_los_features_jugados():
    con = jugadores(semilla=3)
    con.loc[(con["personId"] == 101) & con["gameId"].isin([1010, 1011, 1012, 1020]), ["numMinutes", "jugo", "titular"]] = [0.0, False, False]
    con.loc[(con["personId"] == 101) & ~con["jugo"], features.STATS] = 0.0
    sin = con[~((con["personId"] == 101) & ~con["jugo"])]          # la misma historia, sin sus filas de "no jugó"

    a, b = features.construir(con), features.construir(sin)
    llave = lambda t: t[(t["personId"] == 101) & (t["y_jugo"] == 1)].sort_values("gameId")
    a, b = llave(a), llave(b)
    assert len(a) == len(b) > 20
    np.testing.assert_allclose(a[NUEVAS(a)].to_numpy(float), b[NUEVAS(b)].to_numpy(float), equal_nan=True)
    # y los features "por filas" sí cambian: es justo lo que el diseño nuevo evita
    assert not np.allclose(a["min_prom_10"].to_numpy(float), b["min_prom_10"].to_numpy(float), equal_nan=True)


def test_la_ausencia_se_cuenta_con_el_calendario_del_equipo():
    d = jugadores(semilla=4)
    d["numMinutes"] = d["numMinutes"].clip(lower=5.0); d["jugo"] = True          # todos juegan todo...
    falta = (d["personId"] == 102) & d["gameId"].between(1015, 1018)            # ...menos el 102, cuatro partidos
    d = d[~falta]                                                               # sin fila, como un lesionado en Kaggle
    t = features.construir(d)
    regreso = t[(t["personId"] == 102) & (t["gameId"] == 1019)].iloc[0]
    assert regreso["cal_partidos_eq_perdidos"] == 4
    assert np.isclose(regreso["cal_jugo_prop_eq_10"], 0.6)
    assert regreso["cal_dias_sin_jugar"] == 10                                   # un partido cada 2 días
    antes = t[(t["personId"] == 102) & (t["gameId"] == 1014)].iloc[0]
    assert antes["cal_partidos_eq_perdidos"] == 0 and antes["cal_jugo_prop_eq_10"] == 1.0


def test_cada_diseno_usa_sus_columnas():
    t = features.construir(jugadores())
    cols = [c for c in t.columns if c not in features.IDS and not c.startswith("y_")]
    filas, jug = features.columnas_del_diseno(cols, "filas"), features.columnas_del_diseno(cols, "jugados")
    assert "min_prom_10" in filas and not any(c.startswith(("j_", "cal_")) for c in filas)
    assert "j_min_prom_10" in jug and "cal_partidos_eq_perdidos" in jug and "min_prom_10" not in jug and "dias_descanso" not in jug
    assert "local" in filas and "local" in jug                                   # lo que no depende de filas sigue en los dos


def test_una_tabla_vieja_no_puede_entrenar_el_diseno_jugados():
    viejas = ["min_prom_10", "points_pm_10", "local", "b1_points"]
    assert features.diseno_de(viejas) == "filas" and features.diseno_de(viejas + ["j_min_prom_10"]) == "jugados"
    with pytest.raises(ValueError, match="features.py"):
        features.columnas_del_diseno(viejas, "jugados")
