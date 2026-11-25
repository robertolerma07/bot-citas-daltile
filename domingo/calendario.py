"""
Calendario del domingo de seguimiento.

Las horas viven en config/domingo.json (nunca en el código) y se interpretan siempre en la
hora de Ciudad de México. Aquí solo se cargan y se calcula a qué domingo pertenece un momento.
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from lib.seguridad import RAIZ, ZONA_CDMX

RUTA_CALENDARIO = RAIZ / "config" / "domingo.json"
DOMINGO = 6  # date.weekday(): lunes = 0
LUNES = 0
HORA_FIN_RESUMEN = time(12, 0)  # el lunes antes de esta hora todavía es "el domingo" para el resumen


def cargar_calendario(ruta=RUTA_CALENDARIO):
    """Lee config/domingo.json y regresa el diccionario. Lanza ValueError si no se puede leer."""
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"No se pudo leer el calendario {ruta}: {e}") from e


def hora_de(texto):
    """'13:00' -> time(13, 0). Lanza ValueError si no es una hora HH:MM."""
    return datetime.strptime(texto, "%H:%M").time()


def _en_cdmx(ahora):
    if ahora.tzinfo is None:
        raise ValueError("La fecha y hora debe traer zona horaria (usa la de CDMX)")
    return ahora.astimezone(ZONA_CDMX)


def domingo_de(ahora):
    """
    El domingo al que pertenece 'ahora': el mismo día si es domingo; el domingo anterior si es
    lunes antes de las 12:00 (para el resumen). En cualquier otro caso, None.
    """
    ahora = _en_cdmx(ahora)
    if ahora.weekday() == DOMINGO:
        return ahora.date()
    if ahora.weekday() == LUNES and ahora.time() < HORA_FIN_RESUMEN:
        return ahora.date() - timedelta(days=1)
    return None


def domingo_para_aprobar(ahora, cal):
    """
    El domingo para el que se puede aprobar una lista: el próximo, o hoy si es domingo antes de
    'aprobar_hasta'. Si es domingo después de esa hora, None (ese día ya no se aprueba).
    """
    ahora = _en_cdmx(ahora)
    if ahora.weekday() == DOMINGO:
        return ahora.date() if ahora.time() < hora_de(cal["aprobar_hasta"]) else None
    return ahora.date() + timedelta(days=DOMINGO - ahora.weekday())
