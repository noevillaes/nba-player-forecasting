"""Nuevas versiones del modelo de jugadores, con control de calidad.

Mensual (lo llama run_daily.py; corre si pasaron 28 días desde el último intento):
  1. Retador: se entrena con las 8 temporadas previas + lo que va de esta
     temporada, excepto las últimas 2 semanas.
  2. Esas 2 semanas no las vio ninguno de los dos modelos: ahí se comparan el
     modelo activo (campeón) y el retador, estadística por estadística.
  3. El retador solo se activa si su error promedio es menor. Sus intervalos
     se calibran (conformal) con esas mismas 2 semanas.
  Requiere MIN_PARTIDOS de esta temporada para tener algo que aprender.

Inicio (--inicio): entrena una versión con el protocolo de inicio de temporada
(8 temporadas antes de la anterior, calibración en la anterior) y las
features actuales. Se usa cuando cambian las features, como en la v2.

Cada intento queda en results/reentrenos.csv y cada versión en
results/registro_modelos.json.

Uso:  python src/reentrenar.py              (mensual, respeta la cadencia)
      python src/reentrenar.py --forzar     (mensual, ya)
      python src/reentrenar.py --inicio --descripcion "..." """
import argparse
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd

import disponibilidad
import features
import paquete as paquetes
import registro
from clean import temporada as temporada_de
from evaluate import cargar, solo_evaluables, OBJETIVOS
from models import columnas_features, VENTANA_TRAIN
from reconcile import factor_k, clave_k, RECONCILIADAS, VERSION_K

# Lo que dice el registro (y el sitio) de una versión creada con --inicio, si no se pasa otra cosa
DESCRIPCION = ("La v3 con las features calculadas sobre partidos jugados y el calendario del equipo, en vez de "
               "sobre filas del box score: ya no dependen de cuántas filas de \"no jugó\" trae la fuente (en vivo "
               "trae más que el histórico). En 2025-26 y en 2026-27 (sin verlas) bajó el error en minutos (0.6% y "
               "0.9%) y en puntos (0.3% y 0.4%); en las demás estadísticas el cambio es chico "
               "(ver results/banco_v4.csv).")
DESCRIPCION_EN = ("Same model as v3, but every recent-form number is now computed over games the player actually "
                  "played, and time missed is counted on his team's schedule. Before, a player coming back from an "
                  "injury looked different in live data than in the history the model learned from. On last season "
                  "and this one, neither of which it trained on, it cut the error on minutes by 0.6% and 0.9% and "
                  "on points by 0.3% and 0.4%.")
CADA_DIAS = 28
DIAS_VALIDACION = 14
MIN_PARTIDOS = 300          # ~20 partidos por equipo
LOG = Path("results/reentrenos.csv")


TIPO = "nb"      # qué tipo de paquete se entrena: "nb" (v3, distribución completa) o "cuantiles" (v1 y v2)


def entrenar_paquete(fit, calib, calib_todos, cols, tipo: str = TIPO, heredar: dict = None) -> dict:
    """Entrena el paquete, calibra en `calib` (jugaron) y calcula la referencia de
    reconciliación en `calib_todos` (incluye DNP).
    heredar: paquete "nb" del que se copian la dispersión y el mapa del PIT. Lo usa el reentrenamiento
    mensual: sus 2 semanas de validación alcanzan para comparar errores, no para volver a
    estimar la forma de 15 distribuciones."""
    paquete = paquetes.entrenar(fit, calib, cols, tipo)
    if heredar is not None and paquetes.es_nb(heredar) and paquetes.es_nb(paquete):
        paquete["disp"], paquete["recal"] = dict(heredar["disp"]), dict(heredar["recal"])
    for stat in RECONCILIADAS:       # referencias para reconciliar puntos, rebotes y asistencias
        suma = paquetes.para_sumar(paquete, calib_todos, stat)
        fuera = disponibilidad.ausentes_historicos(calib_todos)
        paquete[clave_k(stat)] = float(factor_k(calib_todos, suma, stat, fuera).median())
    paquete["version_k"] = VERSION_K
    return paquete


def tablas(objetivo):
    """(todas las filas con historial, solo las evaluables) de las temporadas
    que se usan. Se carga una sola vez para no duplicar memoria."""
    todos = cargar(desde=objetivo - 2 - VENTANA_TRAIN)        # una temporada de más, para el baseline b1
    todos = todos[(todos["temporada"] >= objetivo - 1 - VENTANA_TRAIN) & todos["min_prom_10"].notna()]
    return todos, solo_evaluables(todos)


def registrar(reg, t, objetivo, paquete, descripcion, extra=None, subversion=False) -> str:
    v = registro.siguiente_version(t, subversion)
    archivo = f"modelo_{objetivo}_{v}.joblib"
    registro.MODELOS.mkdir(exist_ok=True)
    joblib.dump(paquete, registro.MODELOS / archivo)
    t["versiones"].append({"version": v, "archivo": archivo, "creada": registro.hoy(),
                           "descripcion": descripcion, "features": len(paquete["cols"]),
                           "tipo": paquete.get("tipo", "cuantiles"), **(extra or {})})
    t["activo"] = v
    registro.guardar(reg)
    print(f"\nActiva desde el próximo pronóstico: {v} ({archivo})")
    return v


def inicio(objetivo, descripcion, descripcion_en=None):
    reg = registro.cargar()
    t = registro.temporada(reg, objetivo)
    todos, df = tablas(objetivo)
    fit = df[(df["temporada"] < objetivo - 1) & (df["temporada"] >= objetivo - 1 - VENTANA_TRAIN)]
    calib = df[df["temporada"] == objetivo - 1]
    calib_todos = todos[todos["temporada"] == objetivo - 1]
    cols = columnas_features(fit)
    print(f"Entrenando con {len(fit):,} filas y {len(cols)} features "
          f"(calibración: temporada {objetivo - 1})")
    paquete = entrenar_paquete(fit, calib, calib_todos, cols)
    extra = {"protocolo": "inicio de temporada"}
    if descripcion_en:
        extra["descripcion_en"] = descripcion_en  # la que muestra el sitio web
    registrar(reg, t, objetivo, paquete, descripcion, extra)


def mensual(objetivo, hoy, forzar):
    reg = registro.cargar()
    t = registro.temporada(reg, objetivo)
    ultimo = t.get("ultimo_intento")
    if ultimo and not forzar and (hoy - pd.Timestamp(ultimo)).days < CADA_DIAS:
        print(f"Último intento de reentrenamiento: {ultimo}. Toca cada {CADA_DIAS} días.")
        return

    todos, df = tablas(objetivo)
    actual = df[df["temporada"] == objetivo]
    partidos = actual["gameId"].nunique()
    if partidos < MIN_PARTIDOS and not forzar:
        print(f"Reentrenamiento: {partidos} partidos de esta temporada; espera a {MIN_PARTIDOS}.")
        return

    corte = hoy - timedelta(days=DIAS_VALIDACION)
    val = actual[(actual["fecha"] >= corte) & (actual["fecha"] < hoy)]
    fit = df[(df["temporada"] >= objetivo - VENTANA_TRAIN)
             & ((df["temporada"] < objetivo) | (df["fecha"] < corte))]
    val_todos = todos[(todos["temporada"] == objetivo) & (todos["fecha"] >= corte)
                      & (todos["fecha"] < hoy)]
    print(f"Retador: {len(fit):,} filas hasta {corte.date()} | validación: {len(val):,} "
          f"jugadores-partido del {corte.date()} al {(hoy - timedelta(days=1)).date()}")

    version, ruta = registro.version_activa(objetivo)
    campeon = joblib.load(ruta)
    # un reentreno es del mismo diseño que el campeón: mismas features, datos más recientes
    cols = columnas_features(fit, features.diseno_de(campeon["cols"]))
    retador = entrenar_paquete(fit, val, val_todos, cols, heredar=campeon)

    filas = []
    for obj in OBJETIVOS:
        y = val[f"y_{obj}"]
        mae_c = (paquetes.central(campeon, val, obj) - y).abs().mean()
        mae_r = (paquetes.central(retador, val, obj) - y).abs().mean()
        filas.append({"fecha": hoy.strftime("%Y-%m-%d"), "campeon": version, "objetivo": obj,
                      "jugadores": len(y), "MAE_campeon": mae_c, "MAE_retador": mae_r,
                      "cambio_pct": (mae_r / mae_c - 1) * 100})
    res = pd.DataFrame(filas)
    cambio = res["cambio_pct"].mean()
    gana = cambio < 0
    res["promovido"] = gana
    print(res[["objetivo", "MAE_campeon", "MAE_retador", "cambio_pct"]].round(3).to_string(index=False))
    print(f"\nCambio promedio del error: {cambio:+.2f}% -> "
          f"{'el retador gana' if gana else 'se queda el modelo actual'}")

    res.round(4).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    t["ultimo_intento"] = hoy.strftime("%Y-%m-%d")
    if gana:
        registrar(reg, t, objetivo, retador,
                  f"Reentrenamiento mensual con datos hasta el {corte.date()}; "
                  f"{abs(cambio):.1f}% menos error que la {version} en las 2 semanas de validación.",
                  {"protocolo": "mensual", "datos_hasta": str(corte.date()),
                   "cambio_vs_anterior_pct": round(cambio, 2)}, subversion=True)
    else:
        registro.guardar(reg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--descripcion", default=DESCRIPCION)
    ap.add_argument("--descripcion-en", default=DESCRIPCION_EN, help="texto en inglés para el sitio web")
    args = ap.parse_args()
    hoy = pd.Timestamp(args.fecha)
    objetivo = int(temporada_de(pd.Series([hoy])).iloc[0])
    if args.inicio:
        inicio(objetivo, args.descripcion, args.descripcion_en)
    else:
        mensual(objetivo, hoy, args.forzar)


if __name__ == "__main__":
    main()
