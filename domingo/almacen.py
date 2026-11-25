"""
Aprobación y estado guardados del domingo de seguimiento.

Todo vive en resultados/domingo/AAAA-MM-DD/ (ignorado por git) y lo comparten la página de
aprobación y el latido programado. Cada escritura es atómica (archivo temporal en la misma carpeta
y os.replace) para que quien lea nunca vea un archivo a medias. Las fechas se guardan en ISO 8601
con zona. Funciona igual en Linux y en Windows: nada de fcntl ni msvcrt.
"""

import contextlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from domingo.reglas import estado_inicial
from lib.seguridad import RAIZ

RAIZ_DOMINGO = RAIZ / "resultados" / "domingo"
EDAD_MAXIMA_CANDADO = 2 * 3600  # segundos: un candado más viejo se considera abandonado
_ETIQUETA_FECHA = "__datetime__"


class CandadoOcupado(Exception):
    """Otro proceso tiene el candado del latido."""


def carpeta(domingo, raiz=RAIZ_DOMINGO):
    """Carpeta de ese domingo: raiz/AAAA-MM-DD."""
    return Path(raiz) / domingo.isoformat()


# --- escritura y lectura de JSON ---------------------------------------------------------------

def _a_json(obj):
    """Los datetime se guardan con una etiqueta para recuperarlos como datetime al leer."""
    if isinstance(obj, datetime):
        return {_ETIQUETA_FECHA: obj.isoformat()}
    raise TypeError(f"No se puede guardar un {type(obj).__name__} en JSON")


def _de_json(dato):
    if len(dato) == 1 and _ETIQUETA_FECHA in dato:
        return datetime.fromisoformat(dato[_ETIQUETA_FECHA])
    return dato


def _escribir_bytes(ruta, contenido):
    """Escribe en un temporal de la misma carpeta y lo cambia de lugar de golpe."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporal)
        raise


def _escribir_json(ruta, datos):
    # Se serializa completo antes de tocar el disco: si falla, el archivo anterior queda intacto.
    texto = json.dumps(datos, default=_a_json, ensure_ascii=False, indent=2)
    _escribir_bytes(ruta, texto.encode("utf-8"))


def _leer_json(ruta, por_omision=None):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f, object_hook=_de_json)
    except FileNotFoundError:
        return por_omision


# --- aprobación --------------------------------------------------------------------------------

def guardar_aprobacion(domingo, viajes, archivo_excel, quien, ahora, raiz=RAIZ_DOMINGO):
    """Guarda el Excel aprobado y la lista de viajes; reemplaza la aprobación anterior."""
    base = carpeta(domingo, raiz)
    _escribir_bytes(base / "viajes.xlsx", archivo_excel)
    _escribir_json(base / "aprobacion.json", {"quien": quien, "cuando": ahora.isoformat(), "viajes": viajes})


def leer_aprobacion(domingo, raiz=RAIZ_DOMINGO):
    """La aprobación guardada (quien, cuando, viajes) o None si no hay."""
    return _leer_json(carpeta(domingo, raiz) / "aprobacion.json")


# --- estado de cada viaje ----------------------------------------------------------------------

def cargar_estados(domingo, raiz=RAIZ_DOMINGO):
    """Estados guardados por viaje (vacío si aún no hay)."""
    return _leer_json(carpeta(domingo, raiz) / "estados.json", {})


def guardar_estados(domingo, estados, raiz=RAIZ_DOMINGO):
    _escribir_json(carpeta(domingo, raiz) / "estados.json", estados)


def estados_de(domingo, viajes, raiz=RAIZ_DOMINGO):
    """Estados guardados más un estado inicial para cada viaje aprobado que aún no tenga."""
    estados = cargar_estados(domingo, raiz)
    for viaje in viajes:
        estados.setdefault(viaje["viaje"], estado_inicial())
    return estados


# --- paro de emergencia y envíos de una sola vez ------------------------------------------------

def detener(domingo, quien, ahora, raiz=RAIZ_DOMINGO):
    """Marca el domingo como detenido: el latido ya no debe llamar."""
    _escribir_json(carpeta(domingo, raiz) / "detenido.json", {"quien": quien, "cuando": ahora.isoformat()})


def detenido(domingo, raiz=RAIZ_DOMINGO):
    """Quién y cuándo detuvo el domingo, o None si no está detenido."""
    return _leer_json(carpeta(domingo, raiz) / "detenido.json")


def marcar_hecho(domingo, clave, ahora, raiz=RAIZ_DOMINGO):
    """Anota que un envío de una sola vez (correo, resumen, aviso) ya se hizo."""
    ruta = carpeta(domingo, raiz) / "hechos.json"
    hechos = _leer_json(ruta, {})
    hechos[clave] = ahora.isoformat()
    _escribir_json(ruta, hechos)


def ya_hecho(domingo, clave, raiz=RAIZ_DOMINGO):
    return clave in _leer_json(carpeta(domingo, raiz) / "hechos.json", {})


# --- candado -----------------------------------------------------------------------------------

@contextlib.contextmanager
def candado(raiz=RAIZ_DOMINGO):
    """
    Candado entre procesos con un archivo creado de forma exclusiva. Si ya existe y tiene menos de
    2 horas lanza CandadoOcupado; si es más viejo se considera abandonado y se reemplaza. El
    archivo propio siempre se borra al salir, aunque el cuerpo falle.
    """
    ruta = Path(raiz) / "latido.lock"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            edad = time.time() - ruta.stat().st_mtime
        except FileNotFoundError:
            edad = None  # lo soltaron justo ahora
        if edad is not None and edad < EDAD_MAXIMA_CANDADO:
            raise CandadoOcupado(f"Otro proceso tiene el candado ({ruta.name}, de hace {int(edad)} s)")
        with contextlib.suppress(FileNotFoundError):
            ruta.unlink()
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise CandadoOcupado("Otro proceso tomó el candado primero") from None
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            ruta.unlink()
