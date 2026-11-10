"""La mezcla con el mercado nunca debe tirar el pronóstico del día."""
import json

import pandas as pd

import mezcla


def juegos_y_jugadores():
    juegos = pd.DataFrame({"fecha": ["2026-11-08"] * 2, "gameId": [1, 2], "local": ["Hawks", "Suns"],
                           "visitante": ["Lakers", "Spurs"], "pts_local": [115.0, 108.0], "pts_local_q10": [100.0, 93.0],
                           "pts_local_q90": [130.0, 123.0], "pts_visita": [112.0, 117.0], "pts_visita_q10": [97.0, 102.0],
                           "pts_visita_q90": [127.0, 132.0], "total": [227.0, 225.0], "spread": [3.0, -9.0],
                           "prob_local": [0.58, 0.27]})
    pred = pd.DataFrame({"gameId": [1, 1, 2, 2], "local": [1, 0, 1, 0], "points": [20.0, 18.0, 15.0, 25.0],
                         "points_q10": [10.0, 9.0, 7.0, 14.0], "points_q90": [30.0, 28.0, 24.0, 36.0]})
    return juegos, pred


def preparar(tmp_path, monkeypatch, lineas: str = None):
    monkeypatch.setattr(mezcla, "PRED", tmp_path)
    monkeypatch.setattr(mezcla, "SALIDA", tmp_path / "mezcla.json")
    (tmp_path / "mezcla.json").write_text(json.dumps(
        {"peso_modelo": {"spread": 0.25, "total": 0.5, "prob": 0.4}, "lambda_jugadores": 1.0}), encoding="utf-8")
    if lineas is not None:
        (tmp_path / "lineas.csv").write_text(lineas, encoding="utf-8")


CABECERA = "fecha,gameId,espn_id,local,visitante,hora_utc,casa,spread_local,total,ml_local,ml_visita,prob_local_casa,captura,actualizado\n"


def test_un_dia_sin_ninguna_linea_publica_el_modelo_solo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, CABECERA + "2026-11-08,1,401,Hawks,Lakers,2026-11-09T00:00Z,,,,,,,sin momios,2026-11-08T09:00\n")
    juegos, pred = juegos_y_jugadores()
    j, p = mezcla.mezclar(juegos, pred, "2026-11-08")
    assert j["spread"].tolist() == juegos["spread"].tolist() and j["prob_local"].tolist() == juegos["prob_local"].tolist()
    assert (p["ajuste_mercado"] == 1.0).all() and p["points"].tolist() == pred["points"].tolist()


def test_con_linea_en_un_partido_solo_ese_se_mezcla(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, CABECERA + "2026-11-08,1,401,Hawks,Lakers,2026-11-09T00:00Z,DraftKings,-7.0,231.0,-280,230,0.71,previa,2026-11-08T09:00\n")
    juegos, pred = juegos_y_jugadores()
    j, p = mezcla.mezclar(juegos, pred, "2026-11-08")
    a, b = j.set_index("gameId").loc[1], j.set_index("gameId").loc[2]
    assert abs(a["spread"] - (7.0 + 0.25 * (3.0 - 7.0))) < 0.11          # mercado 7, modelo 3, peso del modelo 0.25
    assert abs(a["total"] - (231.0 + 0.5 * (227.0 - 231.0))) < 0.21
    assert 0.58 < a["prob_local"] < 0.71
    assert b["spread"] == -9.0 and b["prob_local"] == 0.27                # sin línea: el modelo solo
    pp = p.set_index(["gameId", "local"])
    assert pp.loc[(1, 1), "ajuste_mercado"] > 1 and pp.loc[(2, 1), "ajuste_mercado"] == 1.0
