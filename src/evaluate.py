"""Marco de evaluación walk-forward y modelos baseline.

Decisión de diseño: se evalúa solo en partidos que el jugador SÍ jugó.
Predecir disponibilidad (lesiones, descansos) es otro problema y queda
fuera de esta versión."""
import os
import numpy as np
import pandas as pd

FEAT = "data/features/model_table.parquet"
OUT = "results"
OBJETIVOS = ["numMinutes", "points", "reboundsTotal", "assists",
             "threePointersMade"]
TEMPORADAS_PRUEBA = range(2015, 2026)


def agregar_b1(df: pd.DataFrame) -> pd.DataFrame:
    """Promedio de los últimos 10 partidos JUGADOS (sin contar DNP).
    Las filas futuras (es_futuro) también lo reciben, calculado con el pasado."""
    df = df.sort_values(["personId", "fecha"]).reset_index(drop=True)
    base = df["y_jugo"] == 1
    if "es_futuro" in df.columns:
        base = base | df["es_futuro"].astype(bool)
    jug = df[base]
    for obj in OBJETIVOS:
        prev = jug.groupby("personId")[f"y_{obj}"].shift(1)
        df.loc[jug.index, f"b1_{obj}"] = (
            prev.groupby(jug["personId"]).rolling(10, min_periods=3).mean()
            .reset_index(level=0, drop=True))
    return df


def cargar() -> pd.DataFrame:
    return agregar_b1(pd.read_parquet(FEAT))


def datos_evaluables() -> pd.DataFrame:
    """Filas donde el jugador jugó y todos los baselines tienen historia.
    Mismas filas para todos los modelos: comparación justa."""
    df = cargar()
    columnas_base = ([f"b1_{o}" for o in OBJETIVOS] + ["min_prom_10"]
                     + [f"{o}_pm_10" for o in OBJETIVOS[1:]])
    evaluables = (df["y_jugo"] == 1) & df[columnas_base].notna().all(axis=1)
    df = df[evaluables]
    print(f"Filas evaluables: {len(df):,}")
    return df


# ---------- Modelos baseline ----------

def prom_10_jugados(train, test):
    return pd.DataFrame({obj: test[f"b1_{obj}"] for obj in OBJETIVOS},
                        index=test.index)


def tasa_x_minutos(train, test):
    pred = pd.DataFrame(index=test.index)
    pred["numMinutes"] = test["min_prom_10"]
    for obj in OBJETIVOS[1:]:
        pred[obj] = test[f"{obj}_pm_10"] * test["min_prom_10"]
    return pred


# ---------- Marco walk-forward ----------

def walk_forward(df: pd.DataFrame, modelos: dict,
                 temporadas=TEMPORADAS_PRUEBA) -> pd.DataFrame:
    """Cada modelo recibe (train, test) y devuelve un DataFrame con una
    columna por objetivo. Si además trae '{obj}_q10' y '{obj}_q90',
    se mide la cobertura del intervalo del 80%."""
    filas = []
    for t in temporadas:
        train = df[df["temporada"] < t]
        test = df[df["temporada"] == t]
        for nombre, fn in modelos.items():
            pred = fn(train, test)
            for obj in OBJETIVOS:
                y = test[f"y_{obj}"]
                err = pred[obj] - y
                fila = {
                    "temporada": t, "modelo": nombre, "objetivo": obj,
                    "n": int(err.notna().sum()),
                    "MAE": err.abs().mean(),
                    "RMSE": np.sqrt((err ** 2).mean()),
                    "sesgo": err.mean(),
                }
                if f"{obj}_q10" in pred:
                    lo, hi = pred[f"{obj}_q10"], pred[f"{obj}_q90"]
                    fila["cobertura_80"] = ((y >= lo) & (y <= hi)).mean()
                    fila["ancho_80"] = (hi - lo).mean()
                filas.append(fila)
        print(f"Temporada {t} evaluada")
    return pd.DataFrame(filas)


def main():
    df = datos_evaluables()
    modelos = {"prom_10_jugados": prom_10_jugados,
               "tasa_x_minutos": tasa_x_minutos}
    res = walk_forward(df, modelos)

    os.makedirs(OUT, exist_ok=True)
    res.to_csv(f"{OUT}/metricas_baseline.csv", index=False)

    print("\nMAE promedio 2015-2025:")
    print(res.pivot_table(index="objetivo", columns="modelo",
                          values="MAE").round(2).to_string())
    print("\nSesgo promedio (negativo = subestima):")
    print(res.pivot_table(index="objetivo", columns="modelo",
                          values="sesgo").round(2).to_string())


if __name__ == "__main__":
    main()