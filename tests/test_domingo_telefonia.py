r"""
Pruebas de domingo/telefonia.py y de herramientas/registrar_numero.py con un http falso (sin red).

Uso:
    .venv\Scripts\python -m pytest tests/test_domingo_telefonia.py -q
"""

import sys
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "herramientas"))

from domingo import telefonia  # noqa: E402
from domingo.reglas import CAMPOS_EXTRAIDOS  # noqa: E402
import registrar_numero  # noqa: E402

KEY = "xi-key-secreta-1234567890"
ENV = {"ELEVENLABS_API_KEY": KEY, "ELEVENLABS_AGENT_ID_SEGUIMIENTO": "agent_abc",
       "ELEVENLABS_PHONE_NUMBER_ID": "phnum_xyz"}
VIAJE = {"viaje": "V-1", "telefono": "+525512345678"}
VARIABLES = {"operador": "Juan Pérez", "saludo": "Buenas tardes"}


class Respuesta:
    def __init__(self, codigo=200, cuerpo=None, texto=""):
        self.status_code = codigo
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.text = texto

    def json(self):
        return self._cuerpo


class HttpFalso:
    """Registra las peticiones y devuelve las respuestas en orden (o lanza si es una excepción)."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []

    def _responder(self, metodo, url, **kw):
        self.peticiones.append((metodo, url, kw))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def post(self, url, **kw):
        return self._responder("POST", url, **kw)

    def get(self, url, **kw):
        return self._responder("GET", url, **kw)


def test_llamar_arma_la_peticion():
    http = HttpFalso(Respuesta(200, {"success": True, "message": "ok", "conversation_id": "conv_1",
                                     "callSid": "CA123"}))
    assert telefonia.llamar(VIAJE, VARIABLES, ENV, http=http) == "conv_1"
    metodo, url, kw = http.peticiones[0]
    assert (metodo, url) == ("POST", "https://api.elevenlabs.io/v1/convai/twilio/outbound-call")
    assert kw["headers"] == {"xi-api-key": KEY}
    assert kw["json"] == {
        "agent_id": "agent_abc",
        "agent_phone_number_id": "phnum_xyz",
        "to_number": "+525512345678",
        "conversation_initiation_client_data": {"dynamic_variables": VARIABLES},
    }
    assert kw["timeout"]


def test_llamar_sin_configuracion():
    env = {k: v for k, v in ENV.items() if k != "ELEVENLABS_PHONE_NUMBER_ID"}
    with pytest.raises(telefonia.ErrorTelefonia, match="ELEVENLABS_PHONE_NUMBER_ID"):
        telefonia.llamar(VIAJE, VARIABLES, env, http=HttpFalso())


@pytest.mark.parametrize("codigo", [400, 402, 500])
def test_llamar_error_http(codigo):
    # El cuerpo del error trae la key y el teléfono: el mensaje no debe repetirlos
    http = HttpFalso(Respuesta(codigo, texto=f"fallo con {KEY} y +525512345678"))
    with pytest.raises(telefonia.ErrorTelefonia) as e:
        telefonia.llamar(VIAJE, VARIABLES, ENV, http=http)
    assert str(codigo) in str(e.value)
    assert KEY not in str(e.value)
    assert "5512345678" not in str(e.value)


def test_llamar_respuesta_sin_conversacion():
    http = HttpFalso(Respuesta(200, {"success": False, "message": "no", "conversation_id": None}))
    with pytest.raises(telefonia.ErrorTelefonia):
        telefonia.llamar(VIAJE, VARIABLES, ENV, http=http)


def test_llamar_sin_red():
    http = HttpFalso(requests.ConnectionError(f"fallo https://x/{KEY} +525512345678"))
    with pytest.raises(telefonia.ErrorTelefonia) as e:
        telefonia.llamar(VIAJE, VARIABLES, ENV, http=http)
    assert KEY not in str(e.value)
    assert "5512345678" not in str(e.value)


def _conv(estado, datos=None, duracion=None):
    c = {"status": estado, "metadata": {"call_duration_secs": duracion} if duracion is not None else {}}
    if datos is not None:
        c["analysis"] = {"data_collection_results": {k: {"value": v} for k, v in datos.items()}}
    return c


def test_esperar_resultado_hasta_done():
    datos = {"hablo_con_operador": True, "llega_antes_de_la_cita": "sí", "entrega_realizada": "no aplica",
             "hora_estimada_dicha": "como a las cuatro", "hora_estimada": "16:00",
             "fecha_estimada": "2026-11-29", "motivo": ""}
    http = HttpFalso(Respuesta(200, _conv("in-progress")), Respuesta(200, _conv("processing")),
                     Respuesta(200, _conv("done", datos, 95)))
    pausas = []
    r = telefonia.esperar_resultado("conv_1", ENV, http=http, dormir=pausas.append)
    assert pausas == [10, 10]
    assert {k: r[k] for k in CAMPOS_EXTRAIDOS} == datos
    assert r["duracion_seg"] == 95
    assert r["estado_conversacion"] == "done"
    assert set(r) == set(CAMPOS_EXTRAIDOS) | {"duracion_seg", "estado_conversacion"}
    metodo, url, kw = http.peticiones[0]
    assert (metodo, url) == ("GET", "https://api.elevenlabs.io/v1/convai/conversations/conv_1")
    assert kw["headers"] == {"xi-api-key": KEY}


def test_esperar_resultado_failed():
    http = HttpFalso(Respuesta(200, _conv("failed")))
    r = telefonia.esperar_resultado("conv_1", ENV, http=http, dormir=lambda s: None)
    assert r["hablo_con_operador"] is False
    assert r["llega_antes_de_la_cita"] == "no sabe"
    assert r["entrega_realizada"] == "no aplica"
    assert r["hora_estimada_dicha"] == r["hora_estimada"] == r["fecha_estimada"] == r["motivo"] == ""
    assert r["estado_conversacion"] == "failed"
    assert r["duracion_seg"] == 0


@pytest.mark.parametrize("valor,esperado", [(True, True), ("true", True), ("True", True), (False, False),
                                            ("false", False), ("sí", False), (None, False), (1, False)])
def test_hablo_con_operador_normaliza(valor, esperado):
    http = HttpFalso(Respuesta(200, _conv("done", {"hablo_con_operador": valor})))
    r = telefonia.esperar_resultado("c", ENV, http=http, dormir=lambda s: None)
    assert r["hablo_con_operador"] is esperado


def test_esperar_resultado_valores_raros_usan_defaults():
    datos = {"llega_antes_de_la_cita": "quizá", "entrega_realizada": None, "motivo": None}
    http = HttpFalso(Respuesta(200, _conv("done", datos)))
    r = telefonia.esperar_resultado("c", ENV, http=http, dormir=lambda s: None)
    assert r["llega_antes_de_la_cita"] == "no sabe"
    assert r["entrega_realizada"] == "no aplica"
    assert r["motivo"] == ""


def test_esperar_resultado_tiempo_agotado():
    http = HttpFalso(*[Respuesta(200, _conv("in-progress")) for _ in range(100)])
    pausas = []
    with pytest.raises(telefonia.ErrorTelefonia):
        telefonia.esperar_resultado("conv_1", ENV, http=http, dormir=pausas.append, max_seg=30)
    assert pausas == [10, 10, 10]


def test_esperar_resultado_error_http_y_sin_red():
    with pytest.raises(telefonia.ErrorTelefonia) as e:
        telefonia.esperar_resultado("c", ENV, http=HttpFalso(Respuesta(500, texto=KEY)),
                                    dormir=lambda s: None)
    assert "500" in str(e.value) and KEY not in str(e.value)
    with pytest.raises(telefonia.ErrorTelefonia) as e:
        telefonia.esperar_resultado("c", ENV, http=HttpFalso(requests.ConnectionError(KEY)),
                                    dormir=lambda s: None)
    assert KEY not in str(e.value)


# --- registrar_numero.py ---

SID = "ACabcdef1234"
TOKEN = "tok-secreto-9876"
NUMERO = "+15125550123"
ENV_TWILIO = {"ELEVENLABS_API_KEY": KEY, "TWILIO_ACCOUNT_SID": SID, "TWILIO_AUTH_TOKEN": TOKEN,
              "TWILIO_NUMERO": NUMERO}


def test_registrar_numero_arma_la_peticion():
    http = HttpFalso(Respuesta(200, {"phone_number_id": "phnum_nuevo"}))
    assert registrar_numero.registrar(ENV_TWILIO, http=http) == "phnum_nuevo"
    metodo, url, kw = http.peticiones[0]
    assert (metodo, url) == ("POST", "https://api.elevenlabs.io/v1/convai/phone-numbers")
    assert kw["headers"] == {"xi-api-key": KEY}
    assert kw["json"] == {"phone_number": NUMERO, "label": registrar_numero.ETIQUETA,
                          "provider": "twilio", "sid": SID, "token": TOKEN}


def test_registrar_numero_error_no_filtra_secretos():
    http = HttpFalso(Respuesta(401, texto=f"{TOKEN} {KEY} {SID} {NUMERO}"))
    with pytest.raises(registrar_numero.ErrorRegistro) as e:
        registrar_numero.registrar(ENV_TWILIO, http=http)
    assert "401" in str(e.value)
    for secreto in (KEY, TOKEN, SID, NUMERO):
        assert secreto not in str(e.value)
    http = HttpFalso(requests.ConnectionError(f"{TOKEN} {SID}"))
    with pytest.raises(registrar_numero.ErrorRegistro) as e:
        registrar_numero.registrar(ENV_TWILIO, http=http)
    for secreto in (KEY, TOKEN, SID, NUMERO):
        assert secreto not in str(e.value)
