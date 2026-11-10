"""El vigía avisa una vez, antes del partido, y solo si falta el pronóstico."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import vigia

ESTADO = {"fecha": "2026-11-04", "partidos_hoy": 14, "hora_hoy": "2026-11-04T19:00:00-05:00",
          "siguiente": "2026-11-05", "hora_siguiente": "2026-11-05T19:30:00-05:00"}
a = lambda s: datetime.fromisoformat(s).replace(tzinfo=vigia.ESTE)


def test_el_5_de_nov_hubiera_avisado():          # ese día la laptop no corrió y nadie se enteró
    assert vigia.revisar(ESTADO, a("2026-11-05T18:10"), lambda f: False)


def test_no_avisa_si_ya_esta_publicado_ni_fuera_de_la_ventana():
    assert vigia.revisar(ESTADO, a("2026-11-05T18:10"), lambda f: True) is None
    assert vigia.revisar(ESTADO, a("2026-11-05T12:00"), lambda f: False) is None     # todavía es temprano
    assert vigia.revisar(ESTADO, a("2026-11-05T19:10"), lambda f: False) is None     # ya avisó la hora anterior


def test_avisa_una_vez_al_dia_si_la_corrida_lleva_dias_sin_pasar():
    assert vigia.revisar(ESTADO, a("2026-11-07T15:10"), lambda f: False)
    assert vigia.revisar(ESTADO, a("2026-11-07T16:10"), lambda f: False) is None


def test_dia_sin_partidos_no_avisa():
    sin = {"fecha": "2026-11-03", "partidos_hoy": 0, "siguiente": "2026-11-04", "hora_siguiente": "2026-11-04T19:00:00-05:00"}
    assert vigia.revisar(sin, a("2026-11-03T18:00"), lambda f: False) is None
