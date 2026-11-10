#!/usr/bin/env python3
"""Vigía: ¿ya se publicó el pronóstico del próximo día con partidos?

Corre en GitHub Actions cada hora (.github/workflows/vigia.yml). No descarga nada: lee
results/estado.json, que la corrida diaria deja en el repo con la fecha y la hora del
siguiente día con partidos. Si falta poco para el primer salto y predictions/<fecha>.csv
no está en el repo, termina con error: GitHub manda un correo por el workflow fallido y el
workflow abre un issue.

Avisa una sola vez por día: solo en la ventana de AVISO_ANTES a AVISO_ANTES - 60 minutos
antes del salto (el workflow corre cada hora). Si la corrida lleva días sin actualizar el
estado, avisa una vez al día a las HORA_ATRASO (hora del Este).

Solo usa la biblioteca estándar.   Prueba:  python tools/vigia.py --ahora 2026-11-05T18:10
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ESTE = ZoneInfo("America/New_York")
AVISO_ANTES = 90       # minutos antes del primer salto
HORA_ATRASO = 15       # 3 p.m. del Este


def revisar(estado: dict, ahora: datetime, existe) -> str | None:
    """Devuelve el mensaje de alerta, o None si todo está bien. existe(fecha) -> bool."""
    hoy = ahora.date().isoformat()
    if estado.get("fecha") == hoy and estado.get("partidos_hoy", 0) > 0:
        dia, hora = hoy, estado.get("hora_hoy")
    else:
        dia, hora = estado.get("siguiente"), estado.get("hora_siguiente")
    if not dia or dia > hoy:
        return None                                    # el siguiente día con partidos todavía no llega
    if existe(dia):
        return None
    if dia < hoy:                                      # la corrida no ha pasado desde antes de ese día
        if ahora.hour == HORA_ATRASO:
            return (f"La corrida diaria no actualiza desde el {estado.get('fecha')}: "
                    f"el {dia} había partidos y no hay pronóstico publicado.")
        return None
    salto = datetime.fromisoformat(hora).astimezone(ESTE) if hora else ahora.replace(hour=19, minute=0)
    falta = (salto - ahora).total_seconds() / 60
    if AVISO_ANTES - 60 < falta <= AVISO_ANTES:
        return (f"Faltan {falta:.0f} minutos para el primer partido de hoy ({salto:%H:%M} del Este) "
                f"y predictions/{dia}.csv no está en el repo.")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ahora", help="AAAA-MM-DDTHH:MM, hora del Este (para pruebas)")
    args = ap.parse_args()
    ahora = datetime.fromisoformat(args.ahora).replace(tzinfo=ESTE) if args.ahora else datetime.now(ESTE)
    raiz = Path(__file__).resolve().parent.parent
    estado = json.loads((raiz / "results/estado.json").read_text(encoding="utf-8"))
    alerta = revisar(estado, ahora, lambda f: (raiz / f"predictions/{f}.csv").exists())
    if alerta:
        print(alerta)
        sys.exit(1)
    print(f"Todo bien ({ahora:%Y-%m-%d %H:%M} del Este). Última corrida: {estado.get('corrida')}.")


if __name__ == "__main__":
    main()
