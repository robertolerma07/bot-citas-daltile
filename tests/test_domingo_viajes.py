r"""
Pruebas del calendario del domingo y de la lista de viajes en Excel.

Uso:
    .venv\Scripts\python -m pytest tests/test_domingo_viajes.py -q
"""

import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest
from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from domingo.calendario import cargar_calendario, domingo_de, domingo_para_aprobar  # noqa: E402
from domingo.viajes import COLUMNAS_VIAJE, leer_excel, validar_viajes, variables_de_voz_viaje  # noqa: E402
from lib.seguridad import ZONA_CDMX  # noqa: E402

LISTA = RAIZ / "datos" / "numeros_demo.txt"
DOMINGO = date(2026, 11, 29)
AHORA = datetime(2026, 11, 27, 18, 0, tzinfo=ZONA_CDMX)


@pytest.fixture
def cal():
    return cargar_calendario()


def validar(ruta, cal):
    return validar_viajes(ruta, DOMINGO, AHORA, cal, LISTA)


def fila_valida(**cambios):
    fila = {"viaje": "100001", "linea": "Fletes Rápidos de Occidente", "operador": "Miguel Ángel Torres",
            "telefono": "+525500000001", "cliente": "Cerámicas y Acabados Tapatíos",
            "destino": "Zapopan, Jalisco", "fecha_cita": "2026-11-30", "tipo_cita": "Hora", "hora": "08:00",
            "correo_monitoreo": "monitoreo@ejemplo.com", "telefono_monitoreo": "+525500000003"}
    fila.update(cambios)
    return fila


def escribir_excel(ruta, filas, columnas=COLUMNAS_VIAJE):
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(columnas))
    for fila in filas:
        hoja.append([fila.get(c) for c in columnas])
    libro.save(ruta)
    return ruta


def test_calendario_trae_los_valores_del_piloto(cal):
    assert cal["ensayo"] is True
    assert cal["max_llamadas_por_viaje"] == 3
    assert cal["tope_llamadas_por_domingo"] == 150
    assert cal["limite_dia_por_omision"] == "16:00"
    assert cal["reintentos"] == ["19:00", "19:30"]


def test_viajes_prueba_pasan(cal):
    errores, advertencias, viajes = validar(RAIZ / "datos" / "viajes_prueba.xlsx", cal)
    assert errores == [] and advertencias == []
    assert len(viajes) == 5
    dia = [v for v in viajes if v["tipo_cita"] == "Día"]
    assert sorted(v["hora"] for v in dia) == ["", "14:00"]
    assert sum(v["tipo_cita"] == "Hora" for v in viajes) == 3


def test_viajes_con_errores_fallan(cal):
    errores, _, viajes = validar(RAIZ / "datos" / "viajes_con_errores.xlsx", cal)
    esperado = ["telefono", "fecha_cita", "hora", "tipo_cita", "correo_monitoreo", "telefono_monitoreo",
                "viaje repetido", "ya pasó", "lista blanca"]
    assert len(errores) == len(esperado), errores
    for texto, mensaje in zip(esperado, errores):
        assert texto in mensaje, (texto, mensaje)
    assert len({e.split(" ")[1] for e in errores}) == len(esperado)  # un error por fila distinta
    assert all(e.startswith("Fila ") for e in errores)
    assert len(viajes) == 1  # solo la fila correcta


def test_columna_faltante_es_error_de_archivo(cal, tmp_path):
    columnas = [c for c in COLUMNAS_VIAJE if c != "cliente"]
    ruta = escribir_excel(tmp_path / "v.xlsx", [fila_valida()], columnas)
    errores, _, viajes = validar(ruta, cal)
    assert len(errores) == 1 and "columna" in errores[0] and "cliente" in errores[0]
    assert viajes == []


def test_columna_repetida_es_error_de_archivo(cal, tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [fila_valida()], COLUMNAS_VIAJE + ["telefono"])
    errores, _, viajes = validar(ruta, cal)
    assert len(errores) == 1 and "repetidas" in errores[0]


def test_archivo_inexistente(cal, tmp_path):
    errores, _, viajes = validar(tmp_path / "no_hay.xlsx", cal)
    assert len(errores) == 1 and "No existe" in errores[0]


def test_limite_de_dia_por_omision(cal, tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [
        fila_valida(viaje="1", tipo_cita="Día", hora=None),
        fila_valida(viaje="2", tipo_cita="Día", hora="14:00", telefono="+525500000002"),
        fila_valida(viaje="3", tipo_cita="Hora", hora=None, telefono="+525500000003"),
    ])
    errores, _, viajes = validar(ruta, cal)
    assert [v["limite"] for v in viajes] == ["16:00", "14:00"]
    assert len(errores) == 1 and errores[0].startswith("Fila 4") and "hora" in errores[0]


@pytest.mark.parametrize("celda", [525512345678, 5.25512E+11])
def test_telefono_como_numero(cal, tmp_path, celda):
    ruta = escribir_excel(tmp_path / "v.xlsx", [fila_valida(telefono=celda)])
    errores, _, viajes = validar(ruta, cal)
    assert len(errores) == 1
    assert "falta el '+'" in errores[0]
    assert viajes == []


def test_celdas_de_fecha_y_hora_de_excel(tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [
        fila_valida(fecha_cita=datetime(2026, 11, 30), hora=time(8, 0)),
        fila_valida(viaje="2", hora="8:00"),
        fila_valida(viaje="3", hora=" 17:30 "),
    ])
    columnas, filas = leer_excel(ruta)
    assert columnas == COLUMNAS_VIAJE
    assert filas[0]["fecha_cita"] == "2026-11-30" and filas[0]["hora"] == "08:00"
    assert filas[1]["hora"] == "08:00"
    assert filas[2]["hora"] == "17:30"
    assert [f["_fila"] for f in filas] == [2, 3, 4]


def test_advertencias(cal, tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [
        fila_valida(viaje="1", fecha_cita="2026-12-01"),  # martes
        fila_valida(viaje="2", telefono="+525500000002"),
        fila_valida(viaje="3", telefono="+525500000002"),  # mismo teléfono que el viaje 2
        fila_valida(viaje="4", telefono="+525500000003", destino="Av. Mangos 3100, Zapopan"),
    ])
    errores, advertencias, viajes = validar(ruta, cal)
    assert errores == []
    assert len(viajes) == 4  # las advertencias no sacan viajes
    assert any(a.startswith("Fila 2") and "¿seguro?" in a for a in advertencias)
    assert any("mismo teléfono" in a for a in advertencias)
    assert any(a.startswith("Fila 5") and "destino" in a for a in advertencias)


def test_sin_lista_blanca_fuera_de_ensayo(cal, tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [fila_valida(telefono="+525599999999")])
    errores, _, _ = validar(ruta, cal)
    assert len(errores) == 1 and "lista blanca" in errores[0]
    errores, _, viajes = validar(ruta, {**cal, "ensayo": False})
    assert errores == [] and len(viajes) == 1


def test_domingo_para_aprobar(cal):
    def cdmx(*args):
        return datetime(*args, tzinfo=ZONA_CDMX)
    assert domingo_para_aprobar(cdmx(2026, 11, 27, 18, 0), cal) == date(2026, 11, 29)
    assert domingo_para_aprobar(cdmx(2026, 11, 29, 11, 59), cal) == date(2026, 11, 29)
    assert domingo_para_aprobar(cdmx(2026, 11, 29, 12, 0), cal) is None
    assert domingo_para_aprobar(cdmx(2026, 11, 30, 9, 0), cal) == date(2026, 12, 6)


def test_domingo_de():
    def cdmx(*args):
        return datetime(*args, tzinfo=ZONA_CDMX)
    assert domingo_de(cdmx(2026, 11, 29, 15, 0)) == date(2026, 11, 29)
    assert domingo_de(cdmx(2026, 11, 30, 7, 0)) == date(2026, 11, 29)
    assert domingo_de(cdmx(2026, 11, 30, 12, 0)) is None
    assert domingo_de(cdmx(2026, 11, 27, 18, 0)) is None


def test_variables_de_voz_viaje(cal, tmp_path):
    ruta = escribir_excel(tmp_path / "v.xlsx", [fila_valida()])
    _, _, viajes = validar(ruta, cal)
    v = variables_de_voz_viaje(viajes[0])
    assert v["fecha_cita_texto"] == "el lunes treinta de noviembre"
    assert v["limite_texto"] == "las ocho de la mañana"
    assert v["operador"] == "Miguel Ángel Torres"
    assert v["tel_monitoreo_texto"] and v["tel_monitoreo_digitos"]
