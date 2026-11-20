r"""
Genera los archivos de ejemplo de la Fase 1 (todos los datos son FICTICIOS):
- datos/citas_prueba.csv: 3 citas válidas.
- datos/citas_con_errores.csv: citas con errores a propósito, para probar el validador.
- datos/numeros_demo.txt: lista blanca de los teléfonos ficticios de los ejemplos.

Se guardan en UTF-8 con BOM para que Excel muestre bien los acentos.
Uso: .venv\Scripts\python herramientas\generar_datos_ejemplo.py
"""
import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COLUMNAS_CITA = ["folio", "linea", "contacto", "tipo_contacto", "telefono", "origen", "destino",
                 "direccion", "fecha_cita", "hora_cita", "contacto_destino", "tel_trafico"]
COLUMNAS_RESULTADO = ["estatus", "con_quien_hablo", "motivo", "hora_estimada", "intentos",
                      "ultimo_intento", "duracion_seg", "id_conversacion", "notas"]
TEL_TRAFICO = "+528183004500"  # ficticio

BUENAS = [
    ["458217", "Transportes del Valle Norte", "Juan Pérez", "Despacho", "+525500000001",
     "Planta Monterrey", "Pisos y Azulejos del Bajío",
     "Avenida de los Alfareros 1520, colonia Parque Industrial Norte, León, Guanajuato",
     "2026-12-01", "08:30", "Laura Gómez", TEL_TRAFICO],
    ["458230", "Fletes Rápidos de Occidente", "Miguel Ángel Torres", "Operador", "+525500000002",
     "Planta Monterrey", "Cerámicas y Acabados Tapatíos",
     "Calle Ceramistas 875, colonia Las Huertas, Zapopan, Jalisco",
     "2026-12-02", "10:00", "Sergio Ramírez", TEL_TRAFICO],
    ["458244", "Autotransportes Sierra Alta", "Ernesto Villalobos", "Operador", "+525500000003",
     "Planta Monterrey", "Revestimientos del Golfo",
     "Boulevard de los Mangos 3100, colonia Brisas del Golfo, Veracruz, Veracruz",
     "2026-12-03", "16:45", "Patricia Luna", TEL_TRAFICO],
]

# Cada fila trae un error distinto; el comentario dice cuál.
CON_ERRORES = [
    BUENAS[0],                                                                   # fila 2: correcta
    ["900001"] + BUENAS[1][1:4] + ["+5215500000002"] + BUENAS[1][5:],            # "1" antiguo en teléfono
    ["900002"] + BUENAS[1][1:8] + ["2026-02-30"] + BUENAS[1][9:],                # fecha que no existe
    ["900003"] + BUENAS[1][1:9] + ["25:00"] + BUENAS[1][10:],                    # hora inválida
    ["900004"] + BUENAS[1][1:3] + ["Chofer"] + BUENAS[1][4:],                    # tipo de contacto inválido
    ["900005", BUENAS[1][1], ""] + BUENAS[1][3:],                                # contacto vacío
    ["900002"] + BUENAS[2][1:],                                                  # folio duplicado
    ["900006"] + BUENAS[2][1:4] + ["+525599999999"] + BUENAS[2][5:],             # fuera de la lista blanca
    ["900007"] + BUENAS[2][1:7] + ["Av. Mangos 3100, Col. Brisas"] + BUENAS[2][8:],  # abreviaturas (advertencia)
]
RESULTADO_VACIO = [""] * len(COLUMNAS_RESULTADO)


def escribir(nombre, filas, estatus_extra=None):
    ruta = RAIZ / "datos" / nombre
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS_CITA + COLUMNAS_RESULTADO)
        for fila in filas:
            w.writerow(fila + RESULTADO_VACIO)
        if estatus_extra:
            w.writerow(estatus_extra)
    print(f"Escrito {ruta.relative_to(RAIZ)} ({len(filas) + (1 if estatus_extra else 0)} filas)")


escribir("citas_prueba.csv", BUENAS)
# Última fila: estatus de resultado inválido ("Confirmado" en lugar de "Confirmada")
escribir("citas_con_errores.csv", CON_ERRORES,
         ["900008"] + BUENAS[0][1:] + ["Confirmado"] + RESULTADO_VACIO[1:])

(RAIZ / "datos" / "numeros_demo.txt").write_text(
    "# Lista blanca SOLO para probar el validador con los teléfonos ficticios de los ejemplos.\n"
    "# Para llamadas reales se usa config/numeros_permitidos.txt.\n"
    "+525500000001  # Juan Pérez (ficticio)\n"
    "+525500000002  # Miguel Ángel Torres (ficticio)\n"
    "+525500000003  # Ernesto Villalobos (ficticio)\n",
    encoding="utf-8")
print("Escrito datos/numeros_demo.txt")
