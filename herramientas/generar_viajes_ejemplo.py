r"""
Genera los Excel de ejemplo del domingo de seguimiento (todos los datos son FICTICIOS):
- datos/viajes_prueba.xlsx: 5 viajes válidos (citas del lunes 30 de noviembre de 2026).
- datos/viajes_con_errores.xlsx: una fila correcta y una fila por cada error, para probar el validador.
- plantillas/viajes_domingo.xlsx: plantilla vacía con encabezados, teléfonos como Texto e instrucciones.

Los teléfonos son los de datos/numeros_demo.txt.
Uso: .venv\Scripts\python herramientas\generar_viajes_ejemplo.py
"""
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from domingo.viajes import COLUMNAS_VIAJE  # noqa: E402

TEL_MONITOREO = "+525500000003"  # ficticio
CORREO = "monitoreo@ejemplo.com"  # ficticio
COLUMNAS_TELEFONO = ("telefono", "telefono_monitoreo")
FILAS_PLANTILLA = 300  # renglones de la plantilla con formato Texto en teléfonos


def viaje(id_viaje, operador, telefono, cliente, destino, tipo, hora, linea="Fletes Rápidos de Occidente"):
    return {"viaje": id_viaje, "linea": linea, "operador": operador, "telefono": telefono, "cliente": cliente,
            "destino": destino, "fecha_cita": "2026-11-30", "tipo_cita": tipo, "hora": hora,
            "correo_monitoreo": CORREO, "telefono_monitoreo": TEL_MONITOREO}


BUENOS = [
    viaje("104512", "Miguel Ángel Torres", "+525500000001", "Cerámicas y Acabados Tapatíos",
          "Zapopan, Jalisco", "Hora", "08:00"),
    viaje("104513", "Juan Pérez", "+525500000002", "Pisos y Azulejos del Bajío",
          "León, Guanajuato", "Hora", "10:30", "Transportes del Valle Norte"),
    viaje("104514", "Ernesto Villalobos", "+525500000003", "Revestimientos del Golfo",
          "Veracruz, Veracruz", "Hora", "07:00", "Autotransportes Sierra Alta"),
    viaje("104515", "Sergio Ramírez", "+525500000004", "Materiales de Occidente",
          "Guadalajara, Jalisco", "Día", None),
    viaje("104516", "Patricia Luna", "+525500000005", "Distribuidora del Norte",
          "Monterrey, Nuevo León", "Día", "14:00"),
]

# Cada fila sembrada trae un solo error; el comentario dice cuál.
CON_ERRORES = [
    BUENOS[0],                                                         # fila 2: correcta
    {**BUENOS[1], "viaje": "900001", "telefono": "+5215500000002"},    # "1" antiguo en el teléfono
    {**BUENOS[1], "viaje": "900002", "fecha_cita": "2026-02-30"},      # fecha que no existe
    {**BUENOS[1], "viaje": "900003", "hora": "25:00"},                 # hora inválida
    {**BUENOS[1], "viaje": "900004", "tipo_cita": "Semana"},           # tipo de cita inválido
    {**BUENOS[1], "viaje": "900005", "correo_monitoreo": "monitoreo"},  # correo mal formado
    {**BUENOS[1], "viaje": "900006", "telefono_monitoreo": "55 5000 0003"},  # teléfono de monitoreo mal formado
    {**BUENOS[2], "viaje": "104512"},                                  # viaje repetido (el de la fila 2)
    {**BUENOS[2], "viaje": "900007", "fecha_cita": "2026-11-26"},      # la cita ya pasó
    {**BUENOS[2], "viaje": "900008", "telefono": "+525599999999"},     # fuera de la lista blanca
]

INSTRUCCIONES = [
    "Cómo llenar la lista de viajes del domingo",
    "",
    "Una fila por viaje. No cambies los nombres de las columnas ni las borres.",
    "viaje: identificador único en el archivo (no se puede repetir).",
    "linea, operador, cliente: tal como los dirá Sofía.",
    "telefono: del operador, con +52 y 10 dígitos, sin espacios ni guiones (+525512345678). "
    "La columna ya está como Texto; si Excel quita el '+', el viaje no pasa la revisión.",
    "destino: cómo lo dirá Sofía, sin abreviaturas (escribe Avenida, no Av.).",
    "fecha_cita: AAAA-MM-DD (2026-11-30).",
    "tipo_cita: Hora o Día.",
    "hora: en Hora, la hora fija de la cita (08:00). En Día, el límite del cliente; si queda vacía se usa 16:00.",
    "correo_monitoreo: correo de la persona de monitoreo asignada al cliente.",
    "telefono_monitoreo: WhatsApp de monitoreo que Sofía da al cerrar; +52 y 10 dígitos. "
    "Si es uno solo para todos, repítelo en cada fila.",
    "",
    "A todo viaje de la lista aprobada se le llama.",
    "Errores (impiden aprobar): columnas faltantes o repetidas, campos vacíos (salvo hora en Día), teléfono mal "
    "formado, fecha u hora inválidas, tipo_cita distinto de Hora/Día, correo mal formado, viaje repetido, "
    "cita que ya pasó y, durante el ensayo, teléfono fuera de la lista blanca.",
    "Advertencias (no impiden aprobar): cita fuera de domingo 13:00 a lunes 13:00 (¿seguro?), destino con "
    "abreviaturas y el mismo teléfono en dos viajes.",
    "Se puede subir y aprobar hasta el domingo a las 12:00.",
]


def hoja_con_encabezado(libro):
    hoja = libro.active
    hoja.title = "Viajes"
    hoja.append(COLUMNAS_VIAJE)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for i, nombre in enumerate(COLUMNAS_VIAJE, start=1):
        hoja.column_dimensions[hoja.cell(1, i).column_letter].width = max(14, len(nombre) + 4)
    hoja.freeze_panes = "A2"
    return hoja


def texto_en_telefonos(hoja, hasta):
    """Pone las columnas de teléfono como Texto para que Excel no quite el '+'."""
    for nombre in COLUMNAS_TELEFONO:
        col = COLUMNAS_VIAJE.index(nombre) + 1
        for fila in range(2, hasta + 1):
            hoja.cell(fila, col).number_format = "@"


def escribir(nombre, filas):
    ruta = RAIZ / "datos" / nombre
    libro = Workbook()
    hoja = hoja_con_encabezado(libro)
    for fila in filas:
        hoja.append([fila[c] for c in COLUMNAS_VIAJE])
    texto_en_telefonos(hoja, len(filas) + 1)
    libro.save(ruta)
    print(f"Escrito {ruta.relative_to(RAIZ)} ({len(filas)} filas)")


def escribir_plantilla():
    ruta = RAIZ / "plantillas" / "viajes_domingo.xlsx"
    ruta.parent.mkdir(exist_ok=True)
    libro = Workbook()
    hoja = hoja_con_encabezado(libro)
    texto_en_telefonos(hoja, FILAS_PLANTILLA)
    ayuda = libro.create_sheet("Instrucciones")
    ayuda.column_dimensions["A"].width = 110
    for texto in INSTRUCCIONES:
        ayuda.append([texto])
    ayuda["A1"].font = Font(bold=True, size=14)
    for fila in ayuda.iter_rows(min_row=2):
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")
    libro.save(ruta)
    print(f"Escrito {ruta.relative_to(RAIZ)} (plantilla vacía)")


escribir("viajes_prueba.xlsx", BUENOS)
escribir("viajes_con_errores.xlsx", CON_ERRORES)
escribir_plantilla()
