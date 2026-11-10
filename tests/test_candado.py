"""Un pronóstico publicado antes del salto no se reescribe después."""
import pandas as pd

import predict


def test_ya_empezaron_marca_solo_los_partidos_con_salto_pasado():
    fut = pd.DataFrame({"gameId": [1, 2, 3],
                        "gameDateTimeEst": pd.to_datetime(["2026-11-09 19:00", "2026-11-09 20:30", "2026-11-09 22:00"])})
    ahora = pd.Timestamp("2026-11-09 20:30")
    assert predict.ya_empezaron(fut, ahora).tolist() == [True, True, False]
    assert not predict.ya_empezaron(fut, pd.Timestamp("2026-11-09 12:00")).any()
