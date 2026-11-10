"""El paquete del modelo de jugadores: los dos tipos (cuantiles y distribución completa)
responden a la misma interfaz, y la distribución es coherente consigo misma."""
import json

import numpy as np
import pandas as pd
import pytest

import explicar
import paquete as paquetes
import predict

OBJ = ["numMinutes", "points", "steals"]
COLS = ["min_prom_10", "pts_pm", "ruido"]


def datos(n, semilla):
    rng = np.random.default_rng(semilla)
    d = pd.DataFrame({"min_prom_10": rng.uniform(5, 36, n), "pts_pm": rng.uniform(0.2, 0.8, n), "ruido": rng.normal(size=n)})
    mins = np.clip(d["min_prom_10"] + rng.normal(0, 5, n), 1, 48)
    d["y_numMinutes"] = mins
    d["y_points"] = rng.poisson(mins * d["pts_pm"]).astype(float)
    d["y_steals"] = rng.poisson(mins * 0.03).astype(float)
    return d


@pytest.fixture(scope="module")
def nb():
    return paquetes.entrenar(datos(4000, 0), datos(1500, 1), COLS, tipo="nb", objetivos=OBJ)


@pytest.fixture(scope="module")
def cuantiles():
    return paquetes.entrenar(datos(4000, 0), datos(1500, 1), COLS, tipo="cuantiles", objetivos=["points"])


def test_la_v3_da_mediana_entera_dentro_del_intervalo_y_una_media(nb):
    X = datos(300, 2)
    for obj in ["points", "steals"]:
        p = paquetes.pronosticar(nb, X, obj)
        assert set(p.columns) == {obj, f"{obj}_q10", f"{obj}_q90", f"{obj}_media"}
        assert (p[f"{obj}_q10"] <= p[obj]).all() and (p[obj] <= p[f"{obj}_q90"]).all()
        assert np.allclose(p[[obj, f"{obj}_q10", f"{obj}_q90"]], p[[obj, f"{obj}_q10", f"{obj}_q90"]].round())
        assert (p[f"{obj}_media"] > 0).all()
    assert abs(paquetes.pronosticar(nb, X, "points")["points_media"].mean() - X["y_points"].mean()) < 0.6   # sin sesgo


def test_los_minutos_de_la_v3_siguen_saliendo_de_cuantiles(nb):
    p = paquetes.pronosticar(nb, datos(50, 3), "numMinutes")
    assert list(p.columns) == ["numMinutes", "numMinutes_q10", "numMinutes_q90"]
    assert not paquetes.es_conteo(nb, "numMinutes") and paquetes.es_conteo(nb, "points")


def test_un_paquete_de_cuantiles_responde_igual_pero_sin_media(cuantiles):
    X = datos(50, 4)
    p = paquetes.pronosticar(cuantiles, X, "points")
    assert list(p.columns) == ["points", "points_q10", "points_q90"]
    assert not paquetes.es_conteo(cuantiles, "points")
    assert paquetes.para_sumar(cuantiles, X, "points").equals(p["points"])       # se suma la mediana, como antes
    assert paquetes.parametros(cuantiles) == {}


def test_para_sumar_usa_la_media_y_los_parametros_caben_en_json(nb):
    X = datos(50, 5)
    assert paquetes.para_sumar(nb, X, "points").equals(paquetes.pronosticar(nb, X, "points")["points_media"])
    par = json.loads(json.dumps(paquetes.parametros(nb)))
    assert set(par) == {"points", "steals"} and len(par["points"]["recal"]) == 101


def test_escalar_mueve_la_media_y_recalcula_mediana_e_intervalo(nb):
    X = datos(200, 6)
    out = paquetes.pronosticar(nb, X, "points")
    antes = out.copy()
    predict.escalar(out, nb, "points", 1.25)
    assert np.allclose(out["points_media"], antes["points_media"] * 1.25)
    assert (out["points"] >= antes["points"]).all() and (out["points"] > antes["points"]).mean() > 0.5
    assert (out["points_q10"] <= out["points"]).all() and (out["points"] <= out["points_q90"]).all()


def test_el_porque_en_escala_natural_suma_exactamente_la_media(nb):
    X = datos(100, 7)[COLS]
    modelo, en_log = paquetes.modelo_explicable(nb, "points")
    assert en_log
    nat = explicar.a_escala_natural(modelo.predict(X, pred_contrib=True))
    np.testing.assert_allclose(nat.sum(axis=1), modelo.predict(X), rtol=1e-6)
    texto = explicar.explicar(modelo, X, en_log)
    assert texto.str.contains(r"^\d+\.\d\|").all()
