r"""
Pruebas automáticas de la Fase 1 (formato de voz y validador de citas).

Uso:
    .venv\Scripts\python -m pytest -q
"""

import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from lib.formato_voz import (direccion_texto, fecha_texto, folio_texto, hora_texto,  # noqa: E402
                             numero_a_texto, numero_largo_a_texto, saludo, telefono_digitos,
                             telefono_pares)
from validar_citas import validar  # noqa: E402

DEMO = RAIZ / "datos" / "numeros_demo.txt"
HOY = date(2026, 11, 19)


# ---------- Formato de voz ----------

@pytest.mark.parametrize("n, texto", [
    (0, "cero"), (1, "uno"), (16, "dieciséis"), (21, "veintiuno"), (22, "veintidós"),
    (30, "treinta"), (31, "treinta y uno"), (45, "cuarenta y cinco"), (99, "noventa y nueve"),
])
def test_numero_a_texto(n, texto):
    assert numero_a_texto(n) == texto


@pytest.mark.parametrize("fecha, texto", [
    ("2026-12-01", "el martes primero de diciembre"),
    ("2026-12-02", "el miércoles dos de diciembre"),
    ("2026-12-31", "el jueves treinta y uno de diciembre"),
    ("2027-01-23", "el sábado veintitrés de enero"),
])
def test_fecha_texto(fecha, texto):
    assert fecha_texto(fecha) == texto


@pytest.mark.parametrize("hora, texto", [
    ("08:30", "a las ocho y media de la mañana"),
    ("10:00", "a las diez de la mañana"),
    ("07:15", "a las siete y cuarto de la mañana"),
    ("09:05", "a las nueve con cinco minutos de la mañana"),
    ("11:20", "a las once y veinte de la mañana"),
    ("12:00", "a las doce del día"),
    ("12:30", "a las doce y media del día"),
    ("13:00", "a la una de la tarde"),
    ("16:45", "a las cuatro cuarenta y cinco de la tarde"),
    ("19:00", "a las siete de la noche"),
    ("00:00", "a las doce de la noche"),
    ("00:30", "a las doce y media de la noche"),
    ("05:50", "a las cinco cincuenta de la madrugada"),
    ("01:01", "a la una con un minuto de la madrugada"),
    ("13:01", "a la una con un minuto de la tarde"),
    ("09:02", "a las nueve con dos minutos de la mañana"),
])
def test_hora_texto(hora, texto):
    assert hora_texto(hora) == texto


def test_todas_las_horas_se_pueden_decir():
    for h in range(24):
        for m in range(60):
            texto = hora_texto(f"{h:02d}:{m:02d}")
            assert texto.startswith("a l")
            assert "uno minuto" not in texto  # debe ser "un minuto"


@pytest.mark.parametrize("hora", ["24:00", "8:30", "-0:30", "08:60", "0830"])
def test_hora_invalida(hora):
    with pytest.raises(ValueError):
        hora_texto(hora)


@pytest.mark.parametrize("fecha", ["20261201", "2026-W49-2", "2026-02-30"])
def test_fecha_invalida(fecha):
    with pytest.raises(ValueError):
        fecha_texto(fecha)


def test_folio_texto():
    assert folio_texto("458217") == "cuatro, cinco, ocho... dos, uno, siete"
    assert folio_texto("DAL-45") == "de, a, ele... guion, cuatro, cinco"
    assert folio_texto("VW1") == "ve, doble u, uno"
    for malo in ["45#8", "", "３４"]:
        with pytest.raises(ValueError):
            folio_texto(malo)


@pytest.mark.parametrize("n, texto", [
    (100, "cien"), (101, "ciento uno"), (115, "ciento quince"), (500, "quinientos"),
    (875, "ochocientos setenta y cinco"), (1000, "mil"), (1520, "mil quinientos veinte"),
    (2001, "dos mil uno"), (3100, "tres mil cien"), (21000, "veintiún mil"),
    (31500, "treinta y un mil quinientos"), (101000, "ciento un mil"), (999999,
     "novecientos noventa y nueve mil novecientos noventa y nueve"),
])
def test_numero_largo(n, texto):
    assert numero_largo_a_texto(n) == texto


def test_direccion_texto():
    assert direccion_texto("Calle Ceramistas 875, colonia Las Huertas") == \
        "Calle Ceramistas ochocientos setenta y cinco, colonia Las Huertas"
    assert direccion_texto("Calle 5 de Mayo 12, código postal 06600") == \
        "Calle cinco de Mayo doce, código postal cero seis seis cero cero"
    assert direccion_texto("Sin número") == "Sin número"


def test_saludo_hora_invalida():
    with pytest.raises(ValueError):
        saludo("9:00")


@pytest.mark.parametrize("hora, texto", [
    ("09:00", "Buenos días"), ("11:59", "Buenos días"), ("12:00", "Buenas tardes"),
    ("18:59", "Buenas tardes"), ("19:00", "Buenas noches"),
])
def test_saludo(hora, texto):
    assert saludo(hora) == texto


def test_telefono():
    assert telefono_pares("+528183004500") == \
        "ochenta y uno... ochenta y tres... cero cero... cuarenta y cinco... cero cero"
    assert telefono_pares("+525505123456") == \
        "cincuenta y cinco... cero cinco... doce... treinta y cuatro... cincuenta y seis"
    assert telefono_digitos("+528183004500") == "ocho, uno... ocho, tres, cero, cero... cuatro, cinco, cero, cero"


# ---------- Validador ----------

def escribir_csv(tmp_path, filas_texto):
    """Crea un CSV de prueba con el encabezado completo y las filas dadas."""
    encabezado = ("folio,linea,contacto,tipo_contacto,telefono,origen,destino,direccion,fecha_cita,"
                  "hora_cita,contacto_destino,tel_trafico,estatus,con_quien_hablo,motivo,hora_estimada,"
                  "intentos,ultimo_intento,duracion_seg,id_conversacion,notas")
    ruta = tmp_path / "citas.csv"
    ruta.write_text(encabezado + "\n" + "\n".join(filas_texto) + "\n", encoding="utf-8-sig")
    return ruta


FILA_OK = ("111,Línea,Ana,Despacho,+525500000001,Planta,Cliente,\"Calle Uno 1, colonia Centro\","
           "2026-12-01,08:30,Luis,+528183004500,,,,,,,,,")


def test_archivo_bueno_pasa():
    errores, advertencias, filas = validar(RAIZ / "datos" / "citas_prueba.csv", DEMO, hoy=HOY)
    assert errores == [] and advertencias == [] and len(filas) == 3


def test_archivo_con_errores_falla_con_cada_error():
    errores, advertencias, _ = validar(RAIZ / "datos" / "citas_con_errores.csv", DEMO, hoy=HOY)
    texto = "\n".join(errores)
    assert len(errores) == 8
    for esperado in ["quita el '1'", "2026-02-30", "25:00", "Chofer", "campos vacíos: contacto",
                     "folio repetido", "NO está en la lista blanca", "Confirmado"]:
        assert esperado in texto
    assert len(advertencias) == 1 and "abreviaturas" in advertencias[0]


def test_lista_blanca_vacia_bloquea(tmp_path):
    vacia = tmp_path / "vacia.txt"
    vacia.write_text("# sin números\n", encoding="utf-8")
    errores, _, _ = validar(RAIZ / "datos" / "citas_prueba.csv", vacia, hoy=HOY)
    assert any("vacía" in e for e in errores)


def test_fecha_pasada_es_error(tmp_path):
    ruta = escribir_csv(tmp_path, [FILA_OK.replace("2026-12-01", "2026-11-01")])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("ya pasó" in e for e in errores)


def test_columna_telefono_repetida_bloquea(tmp_path):
    """Si hay dos columnas 'telefono', se podría validar un número y llamar a otro."""
    ruta = escribir_csv(tmp_path, [FILA_OK + ",+525500000001"])
    texto = ruta.read_text(encoding="utf-8-sig").replace("notas\n", "notas, telefono \n", 1)
    texto = texto.replace("+525500000001", "+525599999999", 1)
    ruta.write_text(texto, encoding="utf-8-sig")
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert errores and "repetidas" in errores[0]


def test_valores_de_mas_es_error(tmp_path):
    ruta = escribir_csv(tmp_path, [FILA_OK + ",+525599999999"])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("más valores que columnas" in e for e in errores)


def test_folio_repetido_con_otra_escritura(tmp_path):
    fila2 = FILA_OK.replace("111,", "DAL 1,").replace("+525500000001", "+525500000002")
    ruta = escribir_csv(tmp_path, [FILA_OK.replace("111,", "dal-1,"), fila2.replace("DAL 1", "DAL-1")])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("folio repetido" in e for e in errores)


def test_renglon_vacio_no_mueve_numero_de_fila(tmp_path):
    ruta = escribir_csv(tmp_path, ["", FILA_OK.replace("Despacho", "Chofer")])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert errores[0].startswith("Fila 3 ")


def test_intentos_con_digitos_raros(tmp_path):
    # 4 columnas vacías (estatus..hora_estimada) y luego intentos="²"
    ruta = escribir_csv(tmp_path, [FILA_OK[:-9] + ",,,,,²,,,,"])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("intentos" in e for e in errores)


def test_hora_sin_cero_inicial_falla(tmp_path):
    ruta = escribir_csv(tmp_path, [FILA_OK.replace("08:30", "8:30")])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("8:30" in e for e in errores)


def test_telefono_sin_mas_da_pista(tmp_path):
    ruta = escribir_csv(tmp_path, [FILA_OK.replace("+525500000001", "525500000001")])
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert any("falta el '+'" in e for e in errores)


def test_falta_columna(tmp_path):
    ruta = tmp_path / "citas.csv"
    ruta.write_text("folio,linea\n1,x\n", encoding="utf-8")
    errores, _, _ = validar(ruta, DEMO, hoy=HOY)
    assert "Faltan columnas" in errores[0]


def test_archivo_inexistente():
    errores, _, _ = validar(RAIZ / "datos" / "no_existe.csv", DEMO, hoy=HOY)
    assert "No existe" in errores[0]
