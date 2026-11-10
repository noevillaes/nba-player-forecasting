"""Por qué el modelo dice lo que dice: contribuciones de cada feature (SHAP de LightGBM,
pred_contrib) agrupadas en familias que se entienden sin conocer el modelo.

Para un jugador, el pronóstico central = punto de partida + Σ contribuciones. En la v1 y la v2
el pronóstico central es la mediana; desde la v3, la media (el valor esperado).
El punto de partida es lo que el modelo diría de un jugador promedio; cada familia suma o
resta a partir de ahí. Se guarda en el CSV del día como texto compacto, por estadística:

    pq_points = "9.8|forma:+12.1;minutos:+4.2;rival:-0.6"

(antes de los ajustes al total del equipo y a la mezcla con el mercado, que van aparte)."""
import numpy as np
import pandas as pd

EXPLICADAS = ["points", "reboundsTotal", "assists"]
TOP = 4
FAMILIAS = [   # (familia, prefijos o nombres exactos), en orden: gana el primero que coincida
    ("descanso", ("dias_descanso", "back_to_back", "propio_dias_descanso_eq", "propio_b2b_eq",
                  "rival_dias_descanso_eq", "rival_b2b_eq")),
    ("rival", ("rival_",)),
    ("equipo", ("propio_",)),
    ("local", ("local",)),
    ("minutos", ("min_", "titular_", "jugo_", "uso_", "b1_numMinutes")),
    ("forma", ("b1_", "_pm_", "partidos_temp")),
    ("temporada", ("playoffs",)),
]


def familia(col: str) -> str:
    for nombre, claves in FAMILIAS:
        if any(col.startswith(k) or k in col for k in claves):
            return nombre
    return "otros"


def a_escala_natural(contrib: np.ndarray) -> np.ndarray:
    """Contribuciones de un modelo con enlace logarítmico (Poisson), pasadas a las unidades
    de la estadística. El modelo dice log(media) = base + Σ phi, así que
        media - media_base = media_base · (e^Σphi - 1)
    y cada feature recibe la parte de esa diferencia que le toca por su phi. La suma sigue
    siendo exacta: base + Σ contribuciones = media."""
    phi, base = contrib[:, :-1], np.exp(contrib[:, -1])
    s = phi.sum(axis=1)
    chico = np.abs(s) < 1e-9
    escala = base * np.where(chico, 1.0, np.expm1(s) / np.where(chico, 1.0, s))
    return np.column_stack([phi * escala[:, None], base])


def explicar(modelo, X: pd.DataFrame, en_log: bool = False) -> pd.Series:
    """Una cadena por fila: 'base|fam:+x;fam:-y' con las TOP familias de mayor peso.
    en_log: el modelo predice el logaritmo de la media (v3); se convierte a unidades reales."""
    contrib = modelo.predict(X, pred_contrib=True)        # n × (features + 1); la última es la base
    if en_log:
        contrib = a_escala_natural(contrib)
    fam = pd.Series([familia(c) for c in X.columns])
    por_fam = pd.DataFrame(contrib[:, :-1], columns=X.columns).T.groupby(fam.values).sum().T
    base = contrib[:, -1]
    out = []
    for i in range(len(X)):
        fila = por_fam.iloc[i]
        top = fila.reindex(fila.abs().sort_values(ascending=False).index)[:TOP]
        top = top[top.abs() >= 0.05]
        resto = float(fila.sum() - top.sum())            # las familias chicas, juntas: así todo suma
        if abs(resto) >= 0.05:
            top = pd.concat([top.drop("otros", errors="ignore"),
                             pd.Series({"otros": resto + float(top.get("otros", 0.0))})])
        partes = ";".join(f"{k}:{v:+.1f}" for k, v in top.items())
        out.append(f"{base[i]:.1f}|{partes}")
    return pd.Series(out, index=X.index)
