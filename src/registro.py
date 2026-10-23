"""Registro público de versiones del modelo de jugadores.

Vive en results/registro_modelos.json, que se sube a GitHub con el marcador,
así que cada cambio de modelo queda fechado junto a los pronósticos.

Por temporada guarda:
  activo            versión que usa predict.py
  versiones         [{version, archivo, creada, descripcion, ...}]
  recalibraciones   [{desde, version, filas, ajustes{objetivo: puntos}}]
  ultimo_intento    última vez que corrió el reentrenamiento mensual

Si una temporada no está registrada, se usa la v1: models/modelo_<año>.joblib,
entrenado al inicio de la temporada como siempre."""
import json
from datetime import date
from pathlib import Path

RUTA = Path("results/registro_modelos.json")
MODELOS = Path("models")


def cargar() -> dict:
    if RUTA.exists():
        with open(RUTA, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar(reg: dict):
    RUTA.parent.mkdir(exist_ok=True)
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def temporada(reg: dict, objetivo: int) -> dict:
    """Entrada de la temporada; la crea con la v1 si no existe (no guarda)."""
    t = reg.setdefault(str(objetivo), {})
    t.setdefault("versiones", [{
        "version": "v1", "archivo": f"modelo_{objetivo}.joblib",
        "creada": None,
        "descripcion": "Modelo de inicio de temporada (77 features).",
    }])
    t.setdefault("activo", "v1")
    t.setdefault("recalibraciones", [])
    return t


def version_activa(objetivo: int) -> tuple:
    """(nombre de la versión, ruta del archivo)."""
    t = temporada(cargar(), objetivo)
    v = next(x for x in t["versiones"] if x["version"] == t["activo"])
    return v["version"], MODELOS / v["archivo"]


def siguiente_version(t: dict) -> str:
    return f"v{max(int(v['version'][1:]) for v in t['versiones']) + 1}"


def ajuste_vigente(t: dict, version: str, fecha: str) -> dict:
    """Recalibración en efecto para esa versión en esa fecha ({} si ninguna)."""
    vigentes = [r for r in t.get("recalibraciones", [])
                if r["version"] == version and r["desde"] <= fecha]
    return max(vigentes, key=lambda r: r["desde"])["ajustes"] if vigentes else {}


def hoy() -> str:
    return date.today().isoformat()
