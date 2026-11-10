"""Versiones del modelo de jugadores: un diseño nuevo sube el número; un reentreno es una subversión."""
import registro


def temporada(versiones, activo):
    return {"versiones": [{"version": v} for v in versiones], "activo": activo}


def test_un_diseno_nuevo_sube_el_numero():
    assert registro.siguiente_version(temporada(["v1", "v2", "v3"], "v3")) == "v4"
    assert registro.siguiente_version(temporada(["v1", "v2", "v3", "v3.1"], "v3.1")) == "v4"


def test_un_reentreno_es_una_subversion_del_activo():
    assert registro.siguiente_version(temporada(["v1", "v2", "v3"], "v3"), subversion=True) == "v3.1"
    assert registro.siguiente_version(temporada(["v1", "v2", "v3", "v3.1"], "v3.1"), subversion=True) == "v3.2"
    # el retador perdió una vez y el campeón sigue siendo la v3: la siguiente subversión no pisa a la v3.1
    assert registro.siguiente_version(temporada(["v1", "v2", "v3", "v3.1", "v4"], "v4"), subversion=True) == "v4.1"


def test_partes_version():
    assert registro.partes_version("v3") == (3, 0) and registro.partes_version("v3.12") == (3, 12)
