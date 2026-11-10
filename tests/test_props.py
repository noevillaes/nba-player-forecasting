"""La medición contra las líneas de jugadores: línea, lado, pago y ventaja."""
import numpy as np
import pandas as pd

import props


def fotos():
    base = {"fecha": "2026-11-10", "inicio_utc": "2026-11-11T00:40:00Z", "local": "Knicks", "visitante": "Bucks",
            "mercado": "player_points", "capturado": "2026-11-10T16:33+00:00"}
    filas = [("Jalen Brunson", "a", 25.5, -110, -110, 0.5), ("Jalen Brunson", "b", 25.5, +105, -125, 0.467),
             ("Jalen Brunson", "c", 26.5, +130, -160, 0.41),            # otra línea: sus precios no cuentan
             ("Myles Turner", "a", 9.5, -115, -105, 0.51), ("Myles Turner", "b", 10.5, +100, -120, 0.48)]
    return pd.DataFrame([{**base, "jugador": j, "casa": c, "linea": l, "over": o, "under": u, "prob_over": p}
                         for j, c, l, o, u, p in filas])


def test_la_linea_es_la_que_ofrecen_mas_casas_y_los_precios_son_de_esa_linea():
    m = props.mercado(fotos()).set_index("clave")
    b = m.loc["jalen brunson"]
    assert b["linea"] == 25.5 and b["casas"] == 2
    assert b["mejor_over"] == 105 and b["mejor_under"] == -110          # el +130 es de la línea 26.5
    assert np.isclose(b["prob_mercado"], (0.5 + 0.467) / 2)
    assert m.loc["myles turner", "linea"] in (9.5, 10.5)                 # empate de casas: se queda una que sí existe


def test_una_foto_tomada_despues_del_salto_no_cuenta():
    f = fotos()
    f.loc[f["jugador"] == "Myles Turner", "capturado"] = "2026-11-11T01:00+00:00"
    assert "myles turner" not in set(props.mercado(f)["clave"])


def fila(**k):
    base = {"fecha": "2026-11-10", "linea": 25.5, "pronostico": 27.0, "media": 27.4, "real": 30.0,
            "prob_modelo": 0.60, "prob_mercado": 0.50, "mejor_over": 100.0, "mejor_under": -120.0}
    return {**base, **k}


def test_lado_pago_y_ventaja():
    d = props.apostar(pd.DataFrame([
        fila(),                                                          # over, acierta, paga +100
        fila(prob_modelo=0.30, real=30.0),                               # under, falla
        fila(prob_modelo=0.30, real=20.0),                               # under, acierta, paga -120
        fila(linea=25.0, real=25.0),                                     # empate: se devuelve
        fila(prob_modelo=np.nan, pronostico=24.0, real=20.0),            # sin distribución (v2): manda la mediana
    ]))
    assert d["lado"].tolist() == ["over", "under", "under", "over", "under"]
    assert np.allclose(d["pago"].to_numpy(float), [1.0, -1.0, 100 / 120, np.nan, 100 / 120], equal_nan=True)
    assert np.allclose(d["ventaja"].iloc[:3], [0.10, 0.20, 0.20])
    assert np.isnan(d["ventaja"].iloc[4])


def test_resumen_y_kelly():
    d = props.apostar(pd.DataFrame([fila(), fila(prob_modelo=0.30, real=30.0)]))
    r = props.resumen(d)
    assert r["apuestas"] == 2 and r["aciertos"] == 1 and r["rendimiento"] == 0.0
    assert r["apuestas_ventaja_10"] == 2 and r["apuestas_ventaja_5"] == 2
    assert np.isclose(r["brier_modelo"], ((0.6 - 1) ** 2 + (0.3 - 1) ** 2) / 2)
    assert np.isclose(r["brier_mercado"], 0.25)
    # un cuarto de Kelly con tope de 5%: over gana +5%; under (p 0.7, paga 0.833) pierde su 5%; van el mismo día
    assert np.isclose(r["kelly"], 1 + 0.05 * 1.0 - 0.05)
