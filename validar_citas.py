r"""
Fase 1 — Valida la tabla de citas ANTES de usarla para llamar.

Revisa:
- que estén todas las columnas;
- que no haya campos vacíos en los datos de la cita;
- teléfonos en formato +52 y 10 dígitos (sin el "1" antiguo de celulares);
- fechas reales en formato AAAA-MM-DD y horas en formato HH:MM;
- tipo de contacto: Operador o Despacho;
- folios duplicados;
- teléfonos que no estén en la lista blanca;
- estatus de resultado válido (si ya tiene uno).

- citas con fecha que ya pasó, columnas repetidas y filas con valores de más.

También avisa (sin fallar) de direcciones con abreviaturas.

Uso:
    .venv\Scripts\python validar_citas.py                                   (valida datos\citas_prueba.csv
                                                                             contra config\numeros_permitidos.txt;
                                                                             falla mientras los teléfonos de las
                                                                             citas no estén en esa lista)
    .venv\Scripts\python validar_citas.py datos\otro.csv --lista datos\numeros_demo.txt
    .venv\Scripts\python validar_citas.py --mostrar-voz                     (muestra cómo lo dirá el bot)

Sale con código 0 si no hay errores y 1 si hay al menos uno.
"""

import argparse
import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

from lib.formato_voz import variables_de_voz
from lib.seguridad import PATRON_TELEFONO_MX, RAIZ, RUTA_LISTA_BLANCA, ZONA_CDMX, cargar_lista_blanca

COLUMNAS_CITA = ["folio", "linea", "contacto", "tipo_contacto", "telefono", "origen", "destino",
                 "direccion", "fecha_cita", "hora_cita", "contacto_destino", "tel_trafico"]
COLUMNAS_RESULTADO = ["estatus", "con_quien_hablo", "motivo", "hora_estimada", "intentos",
                      "ultimo_intento", "duracion_seg", "id_conversacion", "notas"]
TIPOS_CONTACTO = {"Operador", "Despacho"}
ESTATUS_VALIDOS = {"Confirmada", "No puede", "Sin respuesta", "Reintentar"}
PATRON_HORA = re.compile(r"^[0-9]{2}:[0-9]{2}$")
PATRON_FECHA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
# Abreviaturas que el bot podría leer mal ("Av." -> "a uve")
ABREVIATURAS = re.compile(r"\b(Av|Col|No|Blvd|Calz|Fracc|Carr|Km)\.", re.IGNORECASE)


def revisar_telefono(valor, campo):
    """Regresa un mensaje de error si el teléfono no tiene el formato correcto, o None."""
    if PATRON_TELEFONO_MX.match(valor):
        return None
    pista = ""
    digitos = re.sub(r"[^0-9]", "", valor)
    if valor.startswith("+521") and len(digitos) == 13:
        pista = " (quita el '1' después del +52)"
    elif not valor.startswith("+") and len(digitos) == 12:
        pista = " (falta el '+'; en Excel pon la columna como Texto)"
    elif " " in valor or "-" in valor:
        pista = " (sin espacios ni guiones)"
    return f"{campo} '{valor}' no tiene formato +52 y 10 dígitos{pista}"


def leer_citas(ruta_csv):
    """
    Lee el CSV y regresa (columnas, filas). Cada fila es un diccionario con los textos sin
    espacios sobrantes. Si una fila trae más valores que columnas, se guardan en la llave
    '_sobrantes' para que el validador lo marque como error.
    """
    # utf-8-sig acepta archivos guardados desde Excel como "CSV UTF-8"
    with Path(ruta_csv).open(encoding="utf-8-sig", newline="") as f:
        lector = csv.reader(f)
        encabezado = next(lector, [])
        columnas = [c.strip() for c in encabezado]
        filas = []
        for valores in lector:
            if not any(v.strip() for v in valores):
                continue  # renglón vacío
            fila = {c: (valores[i].strip() if i < len(valores) else "") for i, c in enumerate(columnas)}
            fila["_fila"] = lector.line_num  # renglón real del archivo, para los mensajes
            if len(valores) > len(columnas):
                fila["_sobrantes"] = [v for v in valores[len(columnas):] if v.strip()]
            filas.append(fila)
    return columnas, filas


def validar(ruta_csv, ruta_lista=RUTA_LISTA_BLANCA, hoy=None):
    """
    Valida el archivo y regresa (errores, advertencias, filas).
    Cada error/advertencia empieza con 'Fila N'. La fila 1 es el encabezado,
    así que el número coincide con el renglón que ves en Excel.
    """
    hoy = hoy or datetime.now(ZONA_CDMX).date()
    errores, advertencias = [], []

    if not Path(ruta_csv).exists():
        return [f"No existe el archivo {ruta_csv}"], [], []
    try:
        columnas, filas = leer_citas(ruta_csv)
    except UnicodeDecodeError:
        return [f"No se pudo leer {Path(ruta_csv).name}. En Excel guárdalo como 'CSV UTF-8 (delimitado por comas)'."], [], []

    # Una columna repetida (p. ej. dos "telefono") podría hacer que se valide un número
    # y se llame a otro. Se rechaza el archivo completo.
    repetidas = sorted({c for c in columnas if c and columnas.count(c) > 1})
    if repetidas:
        return [f"Columnas repetidas en el encabezado: {', '.join(repetidas)}. Deja solo una de cada una."], [], []

    faltan = [c for c in COLUMNAS_CITA + COLUMNAS_RESULTADO if c not in columnas]
    if faltan:
        return [f"Faltan columnas en el encabezado: {', '.join(faltan)}"], [], filas
    sobran = [c for c in columnas if c not in COLUMNAS_CITA + COLUMNAS_RESULTADO]
    if sobran:
        advertencias.append(f"Columnas que no se usan (se ignoran): {', '.join(sobran)}")
    if not filas:
        return ["El archivo no tiene citas"], advertencias, filas

    permitidos = cargar_lista_blanca(ruta_lista)
    if not permitidos:
        errores.append(f"La lista blanca {Path(ruta_lista).name} está vacía: ningún teléfono está autorizado")

    vistos = {}
    for fila in filas:
        num = fila["_fila"]
        folio = fila.get("folio", "")

        def error(msg):
            errores.append(f"Fila {num} (folio {folio or '¿?'}): {msg}")

        if fila.get("_sobrantes"):
            error(f"la fila trae más valores que columnas ({', '.join(fila['_sobrantes'])}); "
                  "revisa comas sin comillas")

        vacios = [c for c in COLUMNAS_CITA if not fila.get(c)]
        if vacios:
            error(f"campos vacíos: {', '.join(vacios)}")

        if folio:
            # "dal-1", "DAL-1" y "DAL 1" suenan igual al decirlos: se tratan como el mismo folio
            clave = folio.upper().replace(" ", "")
            if clave in vistos:
                error(f"folio repetido (también está en la fila {vistos[clave]})")
            else:
                vistos[clave] = num

        tipo = fila.get("tipo_contacto", "")
        if tipo and tipo not in TIPOS_CONTACTO:
            error(f"tipo_contacto '{tipo}' debe ser Operador o Despacho")

        for campo in ("telefono", "tel_trafico"):
            if fila.get(campo):
                problema = revisar_telefono(fila[campo], campo)
                if problema:
                    error(problema)

        tel = fila.get("telefono", "")
        if tel and PATRON_TELEFONO_MX.match(tel) and permitidos and tel not in permitidos:
            error(f"el teléfono {tel} NO está en la lista blanca")

        fecha_ok = False
        if fila.get("fecha_cita"):
            try:
                if not PATRON_FECHA.match(fila["fecha_cita"]):
                    raise ValueError
                f_cita = date.fromisoformat(fila["fecha_cita"])
                fecha_ok = True
                if f_cita < hoy:
                    error(f"la cita ya pasó ({fila['fecha_cita']}); actualiza la fecha antes de llamar")
            except ValueError:
                error(f"fecha_cita '{fila['fecha_cita']}' no es una fecha real en formato AAAA-MM-DD")

        hora_ok = False
        if fila.get("hora_cita"):
            h = fila["hora_cita"]
            if PATRON_HORA.match(h) and int(h[:2]) <= 23 and int(h[3:]) <= 59:
                hora_ok = True
            else:
                error(f"hora_cita '{h}' no es una hora válida en formato HH:MM (24 horas, p. ej. 08:30 o 16:45)")

        if ABREVIATURAS.search(fila.get("direccion", "")):
            advertencias.append(f"Fila {num} (folio {folio}): la dirección trae abreviaturas; "
                                "escríbelas completas (Avenida, colonia...) para que el bot las lea bien")

        estatus = fila.get("estatus", "")
        if estatus and estatus not in ESTATUS_VALIDOS:
            error(f"estatus '{estatus}' debe ser uno de: {', '.join(sorted(ESTATUS_VALIDOS))}")

        intentos = fila.get("intentos", "")
        if intentos and not re.fullmatch(r"[0-9]+", intentos):
            error(f"intentos '{intentos}' debe ser un número entero")

        # Si los datos básicos están bien, revisamos que el texto para el bot se pueda armar.
        if fecha_ok and hora_ok and folio and not revisar_telefono(fila.get("tel_trafico", ""), "tel_trafico"):
            try:
                variables_de_voz(fila)
            except ValueError as e:
                error(f"no se puede preparar el texto para el bot: {e}")

    return errores, advertencias, filas


def main():
    parser = argparse.ArgumentParser(description="Valida la tabla de citas de prueba.")
    parser.add_argument("archivo", nargs="?", default=str(RAIZ / "datos" / "citas_prueba.csv"))
    parser.add_argument("--lista", default=str(RUTA_LISTA_BLANCA),
                        help="lista blanca a usar (por defecto config/numeros_permitidos.txt)")
    parser.add_argument("--mostrar-voz", action="store_true",
                        help="muestra cómo dirá el bot la fecha, hora, folio y teléfono de cada cita")
    args = parser.parse_args()

    print(f"Validando {args.archivo}")
    print(f"Lista blanca: {args.lista}\n")
    errores, advertencias, filas = validar(args.archivo, args.lista)

    for a in advertencias:
        print(f"⚠️  {a}")
    for e in errores:
        print(f"❌ {e}")

    if args.mostrar_voz and not errores:
        print("\nAsí lo dirá el bot:")
        for fila in filas:
            v = variables_de_voz(fila)
            print(f"\n  Folio {fila['folio']} ({fila['tipo_contacto']}, {fila['contacto']})")
            print(f"    Folio:    {v['folio_texto']}")
            print(f"    Cita:     {v['fecha_cita_texto']}, {v['hora_cita_texto']}")
            print(f"    Tráfico:  {v['tel_trafico_texto']}")
            print(f"    Repetir:  {v['tel_trafico_digitos']}")

    print(f"\nResumen: {len(filas)} cita(s), {len(errores)} error(es), {len(advertencias)} advertencia(s)")
    if errores:
        print("❌ El archivo NO pasa la validación. Corrige los errores antes de llamar.")
        sys.exit(1)
    print("✅ El archivo pasa la validación.")


if __name__ == "__main__":
    main()
