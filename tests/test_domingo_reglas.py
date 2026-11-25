r"""
Pruebas de las reglas del domingo: a quién se llama y qué significa cada resultado.

Uso:
    .venv\Scripts\python -m pytest tests/test_domingo_reglas.py -q
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from domingo.calendario import cargar_calendario  # noqa: E402
from domingo.reglas import ESTADOS, aplicar, cita_ya_paso, decidir, estado_inicial, toca_llamar  # noqa: E402
from lib.seguridad import ZONA_CDMX  # noqa: E402

VIAJE = {"viaje": "V1", "telefono": "+5215500000001", "fecha_cita": "2026-11-30", "tipo_cita": "Hora", "limite": "08:00"}


@pytest.fixture
def cal():
    return cargar_calendario()


def cdmx(dia, h, m=0):
    return datetime(2026, 11, dia, h, m, tzinfo=ZONA_CDMX)


def estado(nombre="pendiente", intentos=0, ultimo=None):
    e = estado_inicial()
    e.update(estado=nombre, intentos=intentos, ultimo_intento=ultimo)
    return e


def resultado(**campos):
    base = {
        "hablo_con_operador": True,
        "llega_antes_de_la_cita": "no sabe",
        "entrega_realizada": "no aplica",
        "hora_estimada_dicha": "",
        "hora_estimada": "",
        "fecha_estimada": "",
        "motivo": "",
    }
    base.update(campos)
    return base


# --- estado inicial y cita ---

def test_estado_inicial():
    assert estado_inicial() == {
        "estado": "pendiente", "intentos": 0, "ultimo_intento": None, "en_curso": None,
        "historial": [], "aviso_pendiente": False, "fallas_api": 0,
    }
    assert "monitoreo" in ESTADOS and len(ESTADOS) == 6


def test_cita_ya_paso():
    assert not cita_ya_paso(VIAJE, cdmx(30, 8, 0))
    assert cita_ya_paso(VIAJE, cdmx(30, 8, 1))
    with pytest.raises(ValueError):
        cita_ya_paso(VIAJE, datetime(2026, 11, 30, 9, 0))


# --- toca_llamar ---

def test_ronda_1300(cal):
    e = estado()
    assert not toca_llamar(VIAJE, e, cdmx(29, 12, 59), cal, None)
    assert toca_llamar(VIAJE, e, cdmx(29, 13, 0), cal, None)
    assert toca_llamar(VIAJE, e, cdmx(29, 20, 59), cal, None)
    assert not toca_llamar(VIAJE, e, cdmx(29, 21, 0), cal, None)


def test_reintentos(cal):
    e1 = estado("sin_respuesta", 1, cdmx(29, 13, 0))
    assert not toca_llamar(VIAJE, e1, cdmx(29, 18, 59), cal, None)
    assert toca_llamar(VIAJE, e1, cdmx(29, 19, 0), cal, None)
    e2 = estado("sin_respuesta", 2, cdmx(29, 19, 0))
    assert not toca_llamar(VIAJE, e2, cdmx(29, 19, 29), cal, None)
    assert toca_llamar(VIAJE, e2, cdmx(29, 19, 30), cal, None)
    assert not toca_llamar(VIAJE, estado("sin_respuesta", 3, cdmx(29, 19, 30)), cdmx(29, 20, 0), cal, None)


@pytest.mark.parametrize("nombre", ["a_tiempo", "entregado", "monitoreo", "en_curso"])
def test_finales_no_se_llaman(cal, nombre):
    for h in (13, 19, 20):
        assert not toca_llamar(VIAJE, estado(nombre, 1), cdmx(29, h, 30), cal, None)


def test_solo_en_domingo(cal):
    assert not toca_llamar(VIAJE, estado(), cdmx(30, 13, 0), cal, None)
    assert not toca_llamar(VIAJE, estado(), cdmx(28, 13, 0), cal, None)


def test_mismo_telefono_10_minutos(cal):
    ahora = cdmx(29, 13, 30)
    assert not toca_llamar(VIAJE, estado(), ahora, cal, ahora - timedelta(minutes=9))
    assert toca_llamar(VIAJE, estado(), ahora, cal, ahora - timedelta(minutes=10))


def test_toca_llamar_exige_zona(cal):
    with pytest.raises(ValueError):
        toca_llamar(VIAJE, estado(), datetime(2026, 11, 29, 13, 0), cal, None)


# --- decidir ---

LLAMADA = cdmx(29, 13, 5)


def test_no_hablo_es_sin_respuesta():
    assert decidir(VIAJE, resultado(hablo_con_operador=False, llega_antes_de_la_cita="sí"), LLAMADA) == "sin_respuesta"


@pytest.mark.parametrize("hora,fecha,esperado", [
    ("", "", "a_tiempo"),
    ("08:00", "2026-11-30", "a_tiempo"),
    ("08:01", "2026-11-30", "monitoreo"),
    ("23:30", "2026-11-29", "a_tiempo"),
    ("07:00", "2026-12-01", "monitoreo"),
    ("", "2026-12-01", "monitoreo"),
    ("09:00", "", "monitoreo"),          # hora tarde sin fecha: se asume el día de la cita
    ("07:30", "", "a_tiempo"),
    ("basura", "tampoco", "a_tiempo"),   # cifras mal formadas = sin cifra, no contradicen
    ("25:99", "2026-13-45", "a_tiempo"),
])
def test_si_llega_antes(hora, fecha, esperado):
    r = resultado(llega_antes_de_la_cita="sí", hora_estimada=hora, fecha_estimada=fecha)
    assert decidir(VIAJE, r, LLAMADA) == esperado


@pytest.mark.parametrize("valor", ["no", "no sabe", "", "SI?", None, 1, True])
def test_no_es_si_es_monitoreo(valor):
    assert decidir(VIAJE, resultado(llega_antes_de_la_cita=valor), LLAMADA) == "monitoreo"


def test_faltan_campos_nunca_a_tiempo():
    assert decidir(VIAJE, {"hablo_con_operador": True}, LLAMADA) == "monitoreo"
    assert decidir(VIAJE, {}, LLAMADA) == "sin_respuesta"
    assert decidir(VIAJE, {"hablo_con_operador": "sí"}, LLAMADA) == "sin_respuesta"


def test_cita_pasada_segun_entrega():
    tarde = cdmx(30, 9, 0)
    assert decidir(VIAJE, resultado(entrega_realizada="sí", llega_antes_de_la_cita="no"), tarde) == "entregado"
    assert decidir(VIAJE, resultado(entrega_realizada="no", llega_antes_de_la_cita="sí"), tarde) == "monitoreo"
    assert decidir(VIAJE, resultado(entrega_realizada="no aplica", llega_antes_de_la_cita="sí"), tarde) == "monitoreo"


def test_decidir_exige_zona():
    with pytest.raises(ValueError):
        decidir(VIAJE, resultado(), datetime(2026, 11, 29, 13, 5))


# --- aplicar ---

def test_sin_respuesta_suma_intento(cal):
    ahora = cdmx(29, 13, 5)
    nuevo = aplicar(estado(), "sin_respuesta", resultado(hablo_con_operador=False), ahora, cal, "conv_1")
    assert nuevo["estado"] == "sin_respuesta"
    assert nuevo["intentos"] == 1
    assert nuevo["ultimo_intento"] == ahora
    assert nuevo["aviso_pendiente"] is False


def test_tercer_sin_respuesta_pasa_a_monitoreo(cal):
    nuevo = aplicar(estado("sin_respuesta", 2), "sin_respuesta", resultado(hablo_con_operador=False), cdmx(29, 19, 30), cal, "c")
    assert nuevo["estado"] == "monitoreo"
    assert nuevo["intentos"] == 3
    assert nuevo["aviso_pendiente"] is True


@pytest.mark.parametrize("decision", ["a_tiempo", "entregado"])
def test_a_tiempo_y_entregado_cierran_sin_aviso(cal, decision):
    nuevo = aplicar(estado("en_curso", 0), decision, resultado(), cdmx(29, 13, 5), cal, "c")
    assert nuevo["estado"] == decision
    assert nuevo["aviso_pendiente"] is False
    assert nuevo["en_curso"] is None


def test_monitoreo_marca_aviso(cal):
    nuevo = aplicar(estado(), "monitoreo", resultado(), cdmx(29, 13, 5), cal, "c")
    assert nuevo["estado"] == "monitoreo"
    assert nuevo["aviso_pendiente"] is True


def test_historial(cal):
    ahora = cdmx(29, 13, 5)
    r = resultado(llega_antes_de_la_cita="no", hora_estimada_dicha="como a las nueve", hora_estimada="09:00",
                  fecha_estimada="2026-11-30", motivo="tráfico")
    nuevo = aplicar(estado(), "monitoreo", r, ahora, cal, "conv_9")
    assert len(nuevo["historial"]) == 1
    h = nuevo["historial"][0]
    assert h["fecha"] == ahora.isoformat()
    assert h["decision"] == "monitoreo"
    assert h["conversacion_id"] == "conv_9"
    for campo in r:
        assert h[campo] == r[campo]


def test_no_modifica_el_anterior(cal):
    antes = estado("sin_respuesta", 1)
    copia = {**antes, "historial": list(antes["historial"])}
    aplicar(antes, "monitoreo", resultado(), cdmx(29, 19, 0), cal, "c")
    assert antes == copia
    assert antes["historial"] == []
