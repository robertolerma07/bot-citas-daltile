"""
Convierte los datos de una cita en texto para que el agente los diga de forma natural.

Se formatea en Python ANTES de enviar las variables al agente, para que el modelo no tenga
que convertir fechas ni números (ahí es donde más se equivoca o inventa).

Ejemplos:
    fecha_texto("2026-12-01")   -> "el martes primero de diciembre"
    hora_texto("16:45")         -> "a las cuatro cuarenta y cinco de la tarde"
    folio_texto("458217")       -> "cuatro, cinco, ocho... dos, uno, siete"
    telefono_pares("+528183004500") -> "ochenta y uno... ochenta y tres... cero cero... cuarenta y cinco... cero cero"
"""

import re
from datetime import date

PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PATRON_HORA = re.compile(r"[0-9]{2}:[0-9]{2}")

UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
            "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
            "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
            "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
DECENAS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
           70: "setenta", 80: "ochenta", 90: "noventa"}

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Cómo se dicen las letras si un folio trae letras (p. ej. "DAL-4582")
LETRAS = {"A": "a", "B": "be", "C": "ce", "D": "de", "E": "e", "F": "efe", "G": "ge",
          "H": "hache", "I": "i", "J": "jota", "K": "ka", "L": "ele", "M": "eme", "N": "ene",
          "Ñ": "eñe", "O": "o", "P": "pe", "Q": "cu", "R": "erre", "S": "ese", "T": "te",
          "U": "u", "V": "ve", "W": "doble u", "X": "equis", "Y": "ye", "Z": "zeta",
          "-": "guion", "/": "diagonal"}


def numero_a_texto(n):
    """Número del 0 al 99 en palabras (suficiente para días, horas, minutos y pares de teléfono)."""
    if not 0 <= n <= 99:
        raise ValueError(f"Solo se convierten números de 0 a 99, llegó {n}")
    if n < 30:
        return UNIDADES[n]
    decena, unidad = divmod(n, 10)
    texto = DECENAS[decena * 10]
    return texto if unidad == 0 else f"{texto} y {UNIDADES[unidad]}"


CENTENAS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
            6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos"}


def numero_largo_a_texto(n):
    """
    Número del 0 al 999,999 en palabras, para números de calle:
    1520 -> 'mil quinientos veinte'; 21000 -> 'veintiún mil'; 100 -> 'cien'.
    """
    if not 0 <= n <= 999_999:
        raise ValueError(f"Solo se convierten números de 0 a 999,999, llegó {n}")
    if n < 100:
        return numero_a_texto(n)
    if n < 1000:
        c, resto = divmod(n, 100)
        base = "cien" if n == 100 else CENTENAS[c]
        return base if resto == 0 else f"{base} {numero_a_texto(resto)}"
    miles, resto = divmod(n, 1000)
    if miles == 1:
        prefijo = "mil"
    else:
        # "uno" se acorta antes de "mil": veintiún mil, treinta y un mil, ciento un mil
        texto_miles = numero_largo_a_texto(miles)
        if texto_miles.endswith("veintiuno"):
            texto_miles = texto_miles[:-len("veintiuno")] + "veintiún"
        elif texto_miles.endswith("uno"):
            texto_miles = texto_miles[:-1]
        prefijo = f"{texto_miles} mil"
    return prefijo if resto == 0 else f"{prefijo} {numero_largo_a_texto(resto)}"


def direccion_texto(direccion):
    """
    Escribe en palabras los números de la dirección:
    'Calle Ceramistas 875, colonia Las Huertas' -> 'Calle Ceramistas ochocientos setenta y cinco, colonia Las Huertas'.
    Un número de más de 6 cifras o con cero inicial (p. ej. un código postal '06600') se dice dígito por dígito.
    """
    def convertir(m):
        digitos = m.group()
        if len(digitos) > 6 or (len(digitos) > 1 and digitos[0] == "0"):
            return " ".join(UNIDADES[int(c)] for c in digitos)
        return numero_largo_a_texto(int(digitos))
    return re.sub(r"[0-9]+", convertir, direccion)


def fecha_texto(fecha_iso):
    """'2026-12-01' -> 'el martes primero de diciembre'. El día 1 se dice 'primero'."""
    if not PATRON_FECHA.fullmatch(fecha_iso):
        raise ValueError(f"Fecha inválida: {fecha_iso} (debe ser AAAA-MM-DD)")
    f = date.fromisoformat(fecha_iso)
    dia = "primero" if f.day == 1 else numero_a_texto(f.day)
    return f"el {DIAS_SEMANA[f.weekday()]} {dia} de {MESES[f.month - 1]}"


def hora_texto(hora_hhmm):
    """
    '08:30' -> 'a las ocho y media de la mañana'; '13:00' -> 'a la una de la tarde'.
    Los minutos después de :30 se dicen completos ('cuatro cuarenta y cinco'),
    sin 'cuarto para', para no dejar lugar a confusión.
    """
    if not PATRON_HORA.fullmatch(hora_hhmm):
        raise ValueError(f"Hora inválida: {hora_hhmm} (debe ser HH:MM)")
    h, m = int(hora_hhmm[:2]), int(hora_hhmm[3:])
    if not (h <= 23 and m <= 59):
        raise ValueError(f"Hora inválida: {hora_hhmm}")

    if h == 0:
        periodo = "de la noche"  # medianoche: "a las doce de la noche"
    elif h < 6:
        periodo = "de la madrugada"
    elif h < 12:
        periodo = "de la mañana"
    elif h == 12:
        periodo = "del día"
    elif h < 19:
        periodo = "de la tarde"
    else:
        periodo = "de la noche"

    h12 = h % 12 or 12
    inicio = "a la una" if h12 == 1 else f"a las {numero_a_texto(h12)}"

    if m == 0:
        minutos = ""
    elif m == 15:
        minutos = " y cuarto"
    elif m == 30:
        minutos = " y media"
    elif m == 1:
        minutos = " con un minuto"
    elif m < 10:
        minutos = f" con {numero_a_texto(m)} minutos"
    elif m < 30:
        minutos = f" y {numero_a_texto(m)}"
    else:
        minutos = f" {numero_a_texto(m)}"
    return f"{inicio}{minutos} {periodo}"


def folio_texto(folio):
    """
    Folio carácter por carácter, en grupos de 3 separados por pausas:
    '458217' -> 'cuatro, cinco, ocho... dos, uno, siete'.
    """
    palabras = []
    for c in folio.strip().upper():
        if c in "0123456789":
            palabras.append(UNIDADES[int(c)])
        elif c in LETRAS:
            palabras.append(LETRAS[c])
        elif c == " ":
            continue
        else:
            raise ValueError(f"El folio '{folio}' trae un carácter que no se puede leer: '{c}'")
    if not palabras:
        raise ValueError("El folio está vacío")
    grupos = [", ".join(palabras[i:i + 3]) for i in range(0, len(palabras), 3)]
    return "... ".join(grupos)


def _diez_digitos(telefono):
    """Quita el +52 y deja los 10 dígitos del teléfono."""
    digitos = "".join(c for c in telefono if c.isdigit())
    if digitos.startswith("52") and len(digitos) == 12:
        digitos = digitos[2:]
    if len(digitos) != 10:
        raise ValueError(f"El teléfono '{telefono}' no tiene 10 dígitos")
    return digitos


def telefono_pares(telefono):
    """
    Teléfono en pares, como se dicta en México:
    '+528183004500' -> 'ochenta y uno... ochenta y tres... cero cero... cuarenta y cinco... cero cero'.
    Un par que empieza con 0 se dice dígito por dígito ('cero cinco').
    """
    d = _diez_digitos(telefono)
    pares = []
    for i in range(0, 10, 2):
        par = d[i:i + 2]
        if par[0] == "0":
            pares.append(f"cero {UNIDADES[int(par[1])]}")
        else:
            pares.append(numero_a_texto(int(par)))
    return "... ".join(pares)


def telefono_digitos(telefono):
    """Teléfono dígito por dígito, en grupos 2-4-4, para cuando piden repetir."""
    d = _diez_digitos(telefono)
    grupos = [d[0:2], d[2:6], d[6:10]]
    return "... ".join(", ".join(UNIDADES[int(c)] for c in g) for g in grupos)


def saludo(hora_hhmm):
    """Saludo según la hora de la llamada: 'Buenos días' (antes de 12), 'Buenas tardes' (12 a 19) o 'Buenas noches'."""
    if not PATRON_HORA.fullmatch(hora_hhmm) or int(hora_hhmm[:2]) > 23:
        raise ValueError(f"Hora inválida: {hora_hhmm} (debe ser HH:MM)")
    h = int(hora_hhmm[:2])
    if h < 12:
        return "Buenos días"
    if h < 19:
        return "Buenas tardes"
    return "Buenas noches"


def variables_de_voz(cita):
    """
    Recibe una fila de la tabla de citas (diccionario) y regresa las variables extra
    que se envían al agente, ya escritas como se deben decir.
    """
    return {
        "fecha_cita_texto": fecha_texto(cita["fecha_cita"]),
        "hora_cita_texto": hora_texto(cita["hora_cita"]),
        "direccion_texto": direccion_texto(cita["direccion"]),
        "folio_texto": folio_texto(cita["folio"]),
        "tel_trafico_texto": telefono_pares(cita["tel_trafico"]),
        "tel_trafico_digitos": telefono_digitos(cita["tel_trafico"]),
    }
