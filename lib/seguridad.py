"""
Candados de seguridad que usan TODOS los scripts del proyecto.

- cargar_env(): lee las credenciales del archivo .env sin imprimirlas.
- enmascarar(): muestra solo los últimos 4 caracteres de una key.
- cargar_lista_blanca() / verificar_lista_blanca(): impiden llamar a números no autorizados.
- verificar_horario(): solo permite llamadas entre 9:00 y 20:00 hora de Ciudad de México.
- confirmar_gasto(): pide confirmación explícita antes de cualquier llamada con costo.

Cualquier candado que falle detiene el script con sys.exit() ANTES de llamar.
"""

import re
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

# La consola de Windows usa una codificación que no acepta emojis; si un mensaje de ALTO
# fallara al imprimirse, el script podría no detenerse. Esto lo evita en todos los scripts.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Carpeta raíz del proyecto (un nivel arriba de lib/)
RAIZ = Path(__file__).resolve().parent.parent
RUTA_ENV = RAIZ / ".env"
RUTA_LISTA_BLANCA = RAIZ / "config" / "numeros_permitidos.txt"

# Formato de celular mexicano: +52 y 10 dígitos (sin el "1" antiguo de móviles)
PATRON_TELEFONO_MX = re.compile(r"^\+52[0-9]{10}\Z")

ZONA_CDMX = ZoneInfo("America/Mexico_City")
HORA_INICIO = time(9, 0)
HORA_FIN = time(20, 0)


def detener(mensaje):
    """Imprime el error y termina el script con código 1."""
    try:
        print(f"\n❌ ALTO: {mensaje}\n")
    finally:
        sys.exit(1)


def enmascarar(valor):
    """Devuelve la key oculta, p. ej. '••••••••a1b2'. Nunca muestra la key completa."""
    if not valor:
        return "(vacío)"
    if len(valor) <= 8:
        return "••••"
    return "••••••••" + valor[-4:]


def cargar_env(requeridas):
    """
    Lee el archivo .env y devuelve (encontradas, faltantes).
    No detiene el script: quien llama decide qué hacer con lo que falte.
    """
    if not RUTA_ENV.exists():
        return {}, list(requeridas)
    valores = dotenv_values(RUTA_ENV)
    encontradas = {}
    faltantes = []
    for nombre in requeridas:
        valor = (valores.get(nombre) or "").strip()
        if valor:
            encontradas[nombre] = valor
        else:
            faltantes.append(nombre)
    return encontradas, faltantes


def cargar_lista_blanca(ruta=RUTA_LISTA_BLANCA):
    """
    Lee config/numeros_permitidos.txt: un número por línea; lo que va después de '#'
    es comentario. Detiene el script si el archivo no existe o trae un número mal escrito.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        detener(f"No existe la lista blanca {ruta}. Copia numeros_permitidos.ejemplo.txt y llénala.")
    try:
        # utf-8-sig acepta archivos guardados con el Bloc de notas (que agrega una marca invisible)
        texto = ruta.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        detener(f"No se pudo leer {ruta.name}. Guárdalo en el Bloc de notas con codificación UTF-8.")
    permitidos = set()
    for num_linea, linea in enumerate(texto.splitlines(), start=1):
        numero = linea.split("#", 1)[0].strip()
        if not numero:
            continue
        if not PATRON_TELEFONO_MX.match(numero):
            detener(f"Lista blanca, línea {num_linea}: '{numero}' no tiene formato +52 y 10 dígitos.")
        permitidos.add(numero)
    return permitidos


def verificar_lista_blanca(telefonos, ruta=RUTA_LISTA_BLANCA):
    """Detiene el script si CUALQUIER teléfono de la lista no está autorizado."""
    if isinstance(telefonos, str):
        telefonos = [telefonos]
    if not telefonos:
        detener("No hay teléfonos que revisar.")
    permitidos = cargar_lista_blanca(ruta)
    if not permitidos:
        detener("La lista blanca está vacía. Agrega al menos un número autorizado.")
    fuera = [t for t in telefonos if t not in permitidos]
    if fuera:
        detener("Estos teléfonos NO están en la lista blanca: " + ", ".join(fuera))


def verificar_horario(forzar=False, ahora=None):
    """
    Solo permite llamadas entre 9:00 y 20:00 hora de Ciudad de México.
    Con forzar=True (bandera --forzar) se permite fuera de horario, con aviso.
    """
    # Siempre se convierte a hora de CDMX, aunque llegue en otra zona horaria
    ahora = (ahora or datetime.now(ZONA_CDMX)).astimezone(ZONA_CDMX)
    if HORA_INICIO <= ahora.time() <= HORA_FIN:
        return
    if forzar:
        print(f"⚠️  Fuera de horario ({ahora:%H:%M} CDMX), pero se usó --forzar.")
        return
    detener(f"Son las {ahora:%H:%M} en CDMX. Solo se llama entre 9:00 y 20:00 (usa --forzar si es necesario).")


def confirmar_gasto(llamadas, entrada=input):
    """
    Muestra cuántas llamadas se harán y a quién, y pide escribir SI para continuar.
    'llamadas' es una lista de diccionarios con folio, contacto y telefono.
    """
    if not llamadas:
        detener("No hay llamadas que hacer.")
    print(f"\nSe van a hacer {len(llamadas)} llamada(s) con costo:")
    for ll in llamadas:
        print(f"  - Folio {ll['folio']}: {ll['contacto']} al {ll['telefono']}")
    try:
        respuesta = entrada("\nEscribe SI (en mayúsculas) para continuar: ").strip()
    except EOFError:
        respuesta = ""  # sin consola interactiva no hay confirmación: se cancela
    if respuesta != "SI":
        detener("Cancelado por el usuario. No se hizo ninguna llamada.")
