"""
Lista de viajes (Excel) del domingo de seguimiento.

Lee el Excel, lo valida con el mismo rigor que validar_citas.py y arma las variables que se
envían al agente. Regresa errores en lugar de detener el proceso: lo usa también la página web.
"""

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from openpyxl import load_workbook

from domingo.calendario import hora_de
from lib.formato_voz import fecha_texto, hora_texto, telefono_por_grupos
from lib.seguridad import PATRON_TELEFONO_MX, RUTA_LISTA_BLANCA, ZONA_CDMX, cargar_lista_blanca
from validar_citas import ABREVIATURAS, PATRON_FECHA, PATRON_HORA, revisar_telefono

COLUMNAS_VIAJE = ["viaje", "linea", "operador", "telefono", "cliente", "destino", "fecha_cita", "tipo_cita",
                  "hora", "correo_monitoreo", "telefono_monitoreo"]
OBLIGATORIAS = [c for c in COLUMNAS_VIAJE if c != "hora"]  # la hora puede ir vacía en las citas de Día
TIPOS_CITA = {"hora": "Hora", "día": "Día", "dia": "Día"}
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PATRON_HORA_CORTA = re.compile(r"^[0-9]:[0-9]{2}$")


def _texto_de_celda(valor):
    """Convierte una celda de Excel en texto normalizado (fechas AAAA-MM-DD, horas HH:MM)."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        # Una celda de fecha viene como datetime; con hora distinta de 00:00 se conserva solo la hora
        return valor.date().isoformat() if valor.time() == time(0, 0) else valor.strftime("%H:%M")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # Excel guarda 104512 como 104512.0
    texto = str(valor).strip()
    if PATRON_HORA_CORTA.match(texto):
        texto = "0" + texto
    return texto


def leer_excel(ruta):
    """
    Lee la primera hoja del Excel y regresa (columnas, filas). Cada fila es un diccionario con
    los textos normalizados y la llave '_fila' con el renglón de Excel (el 1 es el encabezado).
    """
    libro = load_workbook(Path(ruta), read_only=True, data_only=True)
    try:
        hoja = libro.worksheets[0]
        # En modo de solo lectura openpyxl confía en la dimensión guardada en el archivo; si quedó
        # vieja (más chica que los datos) se detendría antes y perdería viajes sin aviso.
        hoja.reset_dimensions()
        renglones = hoja.iter_rows(values_only=True)
        columnas = [_texto_de_celda(c) for c in next(renglones, ())]
        while columnas and not columnas[-1]:
            columnas.pop()  # celdas vacías al final del encabezado
        filas = []
        for num, valores in enumerate(renglones, start=2):
            textos = [_texto_de_celda(v) for v in valores]
            if not any(textos):
                continue  # renglón vacío
            fila = {c: (textos[i] if i < len(textos) else "") for i, c in enumerate(columnas)}
            fila["_fila"] = num
            filas.append(fila)
    finally:
        libro.close()
    return columnas, filas


def _hora_valida(texto):
    return bool(PATRON_HORA.match(texto)) and int(texto[:2]) <= 23 and int(texto[3:]) <= 59


def _en_cdmx(dia, texto_hora):
    return datetime.combine(dia, hora_de(texto_hora), tzinfo=ZONA_CDMX)


def _cargar_permitidos(ruta_lista):
    """Lee la lista blanca sin detener el proceso. Regresa (permitidos, mensaje_de_error)."""
    nombre = Path(ruta_lista).name
    if not Path(ruta_lista).exists():
        return set(), f"No existe la lista blanca {nombre}"
    try:
        permitidos = cargar_lista_blanca(ruta_lista)
    except SystemExit:  # cargar_lista_blanca termina el proceso si un número está mal escrito
        return set(), f"La lista blanca {nombre} no se pudo leer (revisa el formato de los números)"
    if not permitidos:
        return set(), f"La lista blanca {nombre} está vacía: ningún teléfono está autorizado"
    return permitidos, None


def _fuera_de_rango(f_cita, tipo, limite, domingo, cal):
    """
    True si la cita cae fuera de domingo 'desde' a lunes 'hasta' (rango_citas). En Día solo cuenta
    la fecha, porque su límite del día (16:00) puede caer después del lunes a las 13:00.
    """
    rango = cal["rango_citas"]
    lunes = domingo + timedelta(days=1)
    if tipo == "Día":
        return not domingo <= f_cita <= lunes
    return not _en_cdmx(domingo, rango["desde"]) <= _en_cdmx(f_cita, limite) <= _en_cdmx(lunes, rango["hasta"])


def validar_viajes(ruta, domingo, ahora, cal, ruta_lista=RUTA_LISTA_BLANCA):
    """
    Valida el Excel y regresa (errores, advertencias, viajes). Cada mensaje empieza con 'Fila N'
    (el número coincide con el renglón de Excel), salvo los errores de todo el archivo.
    Cada viaje válido trae además 'limite' (HH:MM): la hora en Hora; la hora, o el límite por
    omisión, en Día. 'viajes' trae solo las filas sin error.
    """
    errores, advertencias = [], []
    if not Path(ruta).exists():
        return [f"No existe el archivo {ruta}"], [], []
    try:
        columnas, filas = leer_excel(ruta)
    except Exception as e:  # archivo que no es un Excel, dañado o protegido
        return [f"No se pudo leer {Path(ruta).name} como Excel (.xlsx): {e}"], [], []

    repetidas = sorted({c for c in columnas if c and columnas.count(c) > 1})
    if repetidas:
        return [f"Columnas repetidas en el encabezado: {', '.join(repetidas)}. Deja solo una de cada una."], [], []
    faltan = [c for c in COLUMNAS_VIAJE if c not in columnas]
    if faltan:
        return [f"Faltan columnas en el encabezado: {', '.join(faltan)}"], [], []
    sobran = [c for c in columnas if c and c not in COLUMNAS_VIAJE]
    if sobran:
        advertencias.append(f"Columnas que no se usan (se ignoran): {', '.join(sobran)}")
    if not filas:
        return ["El archivo no tiene viajes"], advertencias, []

    ensayo = bool(cal.get("ensayo"))
    permitidos = set()
    if ensayo:
        permitidos, problema = _cargar_permitidos(ruta_lista)
        if problema:
            errores.append(problema)

    ahora = ahora.astimezone(ZONA_CDMX)
    viajes = []
    vistos, telefonos = {}, {}
    for fila in filas:
        num = fila["_fila"]
        id_viaje = fila.get("viaje", "")
        errores_fila = []

        def error(msg):
            errores_fila.append(f"Fila {num} (viaje {id_viaje or '¿?'}): {msg}")

        vacios = [c for c in OBLIGATORIAS if not fila.get(c)]
        if vacios:
            error(f"campos vacíos: {', '.join(vacios)}")

        if id_viaje:
            clave = id_viaje.upper().replace(" ", "")
            if clave in vistos:
                error(f"viaje repetido (también está en la fila {vistos[clave]})")
            else:
                vistos[clave] = num

        for campo in ("telefono", "telefono_monitoreo"):
            if fila.get(campo):
                problema = revisar_telefono(fila[campo], campo)
                if problema:
                    error(problema)

        tel = fila.get("telefono", "")
        telefono_ok = bool(PATRON_TELEFONO_MX.match(tel))
        if telefono_ok and ensayo and permitidos and tel not in permitidos:
            error(f"el teléfono {tel} NO está en la lista blanca")

        if fila.get("correo_monitoreo") and not PATRON_CORREO.match(fila["correo_monitoreo"]):
            error(f"correo_monitoreo '{fila['correo_monitoreo']}' no es un correo válido")

        tipo = TIPOS_CITA.get(fila.get("tipo_cita", "").lower())
        if fila.get("tipo_cita") and not tipo:
            error(f"tipo_cita '{fila['tipo_cita']}' debe ser Hora o Día")

        f_cita = None
        if fila.get("fecha_cita"):
            try:
                if not PATRON_FECHA.match(fila["fecha_cita"]):
                    raise ValueError
                f_cita = date.fromisoformat(fila["fecha_cita"])
            except ValueError:
                error(f"fecha_cita '{fila['fecha_cita']}' no es una fecha real en formato AAAA-MM-DD")

        hora = fila.get("hora", "")
        hora_ok = bool(hora) and _hora_valida(hora)
        if hora and not hora_ok:
            error(f"hora '{hora}' no es una hora válida en formato HH:MM (24 horas, p. ej. 08:00 o 16:45)")
        if tipo == "Hora" and not hora:
            error("hora vacía: en una cita de tipo Hora hay que escribir la hora de la cita")

        # El límite es la hora de la cita (Hora) o la hora, o la de omisión, en Día
        limite = None
        if tipo == "Hora" and hora_ok:
            limite = hora
        elif tipo == "Día":
            limite = hora if hora_ok else (None if hora else cal["limite_dia_por_omision"])

        if f_cita and limite:
            if _en_cdmx(f_cita, limite) < ahora:
                error(f"la cita ya pasó ({fila['fecha_cita']} {limite}); actualiza la fecha antes de aprobar")
            elif _fuera_de_rango(f_cita, tipo, limite, domingo, cal):
                advertencias.append(
                    f"Fila {num} (viaje {id_viaje}): la cita es el {fila['fecha_cita']} {limite}, fuera de "
                    f"domingo {cal['rango_citas']['desde']} a lunes {cal['rango_citas']['hasta']}; ¿seguro?")

        if ABREVIATURAS.search(fila.get("destino", "")):
            advertencias.append(f"Fila {num} (viaje {id_viaje}): el destino trae abreviaturas; "
                                "escríbelas completas para que Sofía las lea bien")

        if telefono_ok:
            if tel in telefonos:
                advertencias.append(f"Fila {num} (viaje {id_viaje}): el mismo teléfono {tel} ya está en la fila "
                                    f"{telefonos[tel]}; se le llamará una vez por viaje")
            else:
                telefonos[tel] = num

        errores.extend(errores_fila)
        if not errores_fila:
            viajes.append({**{c: fila[c] for c in COLUMNAS_VIAJE}, "tipo_cita": tipo, "limite": limite,
                           "_fila": num})

    return errores, advertencias, viajes


def variables_de_voz_viaje(viaje):
    """Recibe un viaje válido y regresa las variables para el agente, ya escritas como se dicen."""
    return {
        "operador": viaje["operador"],
        "linea": viaje["linea"],
        "cliente": viaje["cliente"],
        "destino": viaje["destino"],
        "fecha_cita_texto": fecha_texto(viaje["fecha_cita"]),
        "tipo_cita": viaje["tipo_cita"],
        "limite_texto": re.sub(r"^a ", "", hora_texto(viaje["limite"])),  # "a las ocho..." -> "las ocho..."
        # 2-2-3-3, como lo pidió Roberto (2026-11-25): "ochenta y uno... ochenta y tres... cero cero cuatro... quinientos"
        "tel_monitoreo_texto": telefono_por_grupos(viaje["telefono_monitoreo"]),
        "tel_monitoreo_digitos": telefono_por_grupos(viaje["telefono_monitoreo"], digito_por_digito=True),
    }
