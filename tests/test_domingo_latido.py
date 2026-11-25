"""Pruebas del latido del domingo: reloj fijo, tmp_path como raíz y llamadas y correos falsos (sin red)."""

import contextlib
import re
from datetime import date, datetime

import pytest

from domingo import almacen, avisos, latido, telefonia
from domingo.calendario import cargar_calendario
from domingo.latido import ejecutar_latido, normalizar_fecha_estimada
from domingo.reglas import estado_inicial
from domingo.telefonia import ErrorTelefonia
from lib.formato_voz import fecha_texto
from lib.seguridad import ZONA_CDMX

DOMINGO = date(2026, 11, 29)
CONTROL = "roberto@ejemplo.com"
ENV = {"ELEVENLABS_API_KEY": "key-falsa-123456", "ELEVENLABS_AGENT_ID_SEGUIMIENTO": "agente_falso",
       "ELEVENLABS_PHONE_NUMBER_ID": "numero_falso", "CORREO_CONTROL": CONTROL}

A_TIEMPO = {"hablo_con_operador": True, "llega_antes_de_la_cita": "sí", "entrega_realizada": "no aplica",
            "hora_estimada_dicha": "como a las 7", "hora_estimada": "07:00", "fecha_estimada": "2026-11-30",
            "motivo": ""}
TARDE = {"hablo_con_operador": True, "llega_antes_de_la_cita": "no", "entrega_realizada": "no aplica",
         "hora_estimada_dicha": "a las 10", "hora_estimada": "10:00", "fecha_estimada": "2026-11-30",
         "motivo": "tráfico"}
NO_CONTESTA = {"hablo_con_operador": False, "llega_antes_de_la_cita": "no sabe", "entrega_realizada": "no aplica",
               "hora_estimada_dicha": "", "hora_estimada": "", "fecha_estimada": "", "motivo": ""}


def dom(h, m=0):
    return datetime(2026, 11, 29, h, m, tzinfo=ZONA_CDMX)


def lun(h, m=0):
    return datetime(2026, 11, 30, h, m, tzinfo=ZONA_CDMX)


def _viaje(n, correo, telefono=None):
    return {"viaje": f"V{n}", "linea": "Linea Norte", "operador": f"Operador {n}",
            "telefono": telefono or f"+52550000000{n}", "cliente": f"Cliente {n}", "destino": "Monterrey",
            "fecha_cita": "2026-11-30", "tipo_cita": "Hora", "hora": "08:00", "correo_monitoreo": correo,
            "telefono_monitoreo": "+525550001111", "limite": "08:00", "_fila": n + 1}


VIAJES_RONDA = [_viaje(1, "ana@m.com"), _viaje(2, "luis@m.com"), _viaje(3, "eva@m.com")]
RESPUESTAS_RONDA = {"V1": A_TIEMPO, "V2": TARDE, "V3": NO_CONTESTA}


class Telefonia:
    """llamar y esperar_resultado falsos: cada viaje (o conversación) contesta lo que diga 'respuestas'."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []  # (viaje, variables)
        self.consultas = []
        self._viaje_de = {}

    def llamar(self, viaje, variables, env):
        self.llamadas.append((viaje["viaje"], variables))
        conversacion = f"conv_{viaje['viaje']}_{len(self.llamadas)}"
        self._viaje_de[conversacion] = viaje["viaje"]
        return conversacion

    def esperar_resultado(self, conversacion, env, dormir=None):
        self.consultas.append(conversacion)
        respuesta = self.respuestas[self._viaje_de.get(conversacion, conversacion)]
        if isinstance(respuesta, Exception):
            raise respuesta
        return dict(respuesta)

    def llamados(self):
        return [v for v, _ in self.llamadas]


class Correo:
    def __init__(self, resultado=True):
        self.enviados = []
        self.resultado = resultado

    def enviar(self, aviso, env):
        self.enviados.append(aviso)
        return self.resultado

    def con_asunto(self, texto):
        return [a for a in self.enviados if texto in a.asunto]


@pytest.fixture
def cal():
    cal = cargar_calendario()
    cal["ensayo"] = False  # la lista blanca se prueba aparte
    return cal


def _latido(ahora, tel, correo, raiz, cal, env=ENV, **kw):
    return ejecutar_latido(ahora, cal, env, raiz, tel.llamar, tel.esperar_resultado, correo.enviar, **kw)


def _aprobar(raiz, viajes):
    almacen.guardar_aprobacion(DOMINGO, viajes, b"xlsx", "Maria", datetime(2026, 11, 28, 18, 0, tzinfo=ZONA_CDMX),
                               raiz=raiz)


def _estados(raiz):
    return almacen.cargar_estados(DOMINGO, raiz=raiz)


def _ronda_1300(raiz, cal, correo=None):
    _aprobar(raiz, VIAJES_RONDA)
    tel = Telefonia(RESPUESTAS_RONDA)
    correo = correo or Correo()
    _latido(dom(13, 0), tel, correo, raiz, cal)
    return tel, correo


# --------------------------------------------------------------------------- cuándo no hace nada

def test_fuera_de_domingo_no_hace_nada(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    for ahora in (datetime(2026, 11, 28, 13, 0, tzinfo=ZONA_CDMX), datetime(2026, 12, 1, 13, 0, tzinfo=ZONA_CDMX),
                  lun(12, 30)):
        assert _latido(ahora, tel, correo, tmp_path, cal) == []
    assert tel.llamadas == [] and correo.enviados == []
    assert not (almacen.carpeta(DOMINGO, tmp_path) / "estados.json").exists()


def test_candado_ocupado_no_hace_nada(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    (tmp_path / "latido.lock").write_text("otro")
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    bitacora = _latido(dom(13, 0), tel, correo, tmp_path, cal)
    assert len(bitacora) == 1 and "candado" in bitacora[0]
    assert tel.llamadas == [] and correo.enviados == []


def test_refresca_el_candado_antes_de_cada_llamada_y_consulta(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    eventos = []

    @contextlib.contextmanager
    def candado_falso(raiz):
        yield lambda: eventos.append("refresco")

    tel = Telefonia(RESPUESTAS_RONDA)

    def llamar(viaje, variables, env):
        eventos.append("llamar")
        return tel.llamar(viaje, variables, env)

    def esperar(conversacion, env, dormir=None):
        dormir(10)  # la telefonía real duerme entre consulta y consulta
        eventos.append("consulta")
        return tel.esperar_resultado(conversacion, env)

    ejecutar_latido(dom(13, 0), cal, ENV, tmp_path, llamar, esperar, Correo().enviar, candado=candado_falso,
                    dormir=lambda seg: eventos.append(f"dormir {seg}"))
    assert eventos.count("llamar") == 3
    for i, evento in enumerate(eventos):
        if evento in ("llamar", "consulta"):
            assert i > 0 and eventos[i - 1] == "refresco", eventos
    assert eventos.count("dormir 10") == 3


def test_candado_perdido_detiene_el_latido(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()

    def llamar_y_perder(viaje, variables, env):
        (tmp_path / "latido.lock").write_text("ficha-de-otro")  # otro latido se quedó con el candado
        return tel.llamar(viaje, variables, env)

    bitacora = ejecutar_latido(dom(13, 0), cal, ENV, tmp_path, llamar_y_perder, tel.esperar_resultado,
                               correo.enviar)
    assert tel.llamados() == ["V1"]
    assert any("candado" in linea for linea in bitacora)
    assert (tmp_path / "latido.lock").read_text() == "ficha-de-otro"


def test_relee_los_estados_antes_de_cada_llamada(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()

    def llamar(viaje, variables, env):
        if viaje["viaje"] == "V1":  # mientras tanto, otro proceso ya resolvió V2
            estados = almacen.cargar_estados(DOMINGO, raiz=tmp_path)
            estados["V2"] = {**estado_inicial(), "estado": "a_tiempo", "intentos": 1, "ultimo_intento": dom(13, 0)}
            almacen.guardar_estados(DOMINGO, estados, raiz=tmp_path)
        return tel.llamar(viaje, variables, env)

    ejecutar_latido(dom(13, 0), cal, ENV, tmp_path, llamar, tel.esperar_resultado, correo.enviar)
    assert tel.llamados() == ["V1", "V3"]
    assert _estados(tmp_path)["V2"]["estado"] == "a_tiempo"


def test_sin_lista_avisa_una_vez(tmp_path, cal):
    tel, correo = Telefonia({}), Correo()
    _latido(dom(11, 55), tel, correo, tmp_path, cal)
    assert correo.enviados == []
    _latido(dom(12, 5), tel, correo, tmp_path, cal)
    _latido(dom(12, 10), tel, correo, tmp_path, cal)
    _latido(dom(13, 0), tel, correo, tmp_path, cal)
    assert len(correo.enviados) == 1
    assert "No hay lista aprobada" in correo.enviados[0].asunto and correo.enviados[0].para == [CONTROL]
    assert tel.llamadas == []


# --------------------------------------------------------------------------- ronda y reintentos

def test_ronda_1300_llama_a_todos_y_manda_correos(tmp_path, cal):
    tel, correo = _ronda_1300(tmp_path, cal)
    assert tel.llamados() == ["V1", "V2", "V3"]
    assert len(correo.enviados) == 2
    caso, control = correo.enviados
    assert caso.para == ["luis@m.com"] and caso.copia == [CONTROL] and "V2" in caso.cuerpo
    assert "V1" not in caso.cuerpo and "V3" not in caso.cuerpo
    assert control.para == [CONTROL] and "Control de la ronda de las 13:00" in control.asunto
    estados = _estados(tmp_path)
    assert [estados[v]["estado"] for v in ("V1", "V2", "V3")] == ["a_tiempo", "monitoreo", "sin_respuesta"]
    assert estados["V2"]["aviso_pendiente"] is False
    assert estados["V2"]["historial"][-1]["conversacion_id"] == "conv_V2_2"
    assert all(e["en_curso"] is None and e["intentos"] == 1 for e in estados.values())
    assert almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)


def test_variables_de_la_llamada(tmp_path, cal):
    tel, _ = _ronda_1300(tmp_path, cal)
    _, variables = tel.llamadas[0]
    assert variables["saludo"] == "Buenas tardes"
    assert variables["cita_ya_paso"] == "no"
    assert variables["hoy_texto"] == fecha_texto("2026-11-29")
    assert variables["operador"] == "Operador 1" and "tel_monitoreo_texto" in variables
    assert "+525500000001" not in variables.values()  # el teléfono del operador no se le pasa al agente


def test_segundo_latido_no_vuelve_a_llamar(tmp_path, cal):
    tel, correo = _ronda_1300(tmp_path, cal)
    _latido(dom(13, 30), tel, correo, tmp_path, cal)
    assert len(tel.llamadas) == 3 and len(correo.enviados) == 2


def test_reintentos_1900_y_1930(tmp_path, cal):
    tel, correo = _ronda_1300(tmp_path, cal)
    _latido(dom(18, 55), tel, correo, tmp_path, cal)
    assert len(tel.llamadas) == 3
    _latido(dom(19, 0), tel, correo, tmp_path, cal)
    assert tel.llamados()[3:] == ["V3"]
    assert _estados(tmp_path)["V3"]["estado"] == "sin_respuesta" and _estados(tmp_path)["V3"]["intentos"] == 2
    assert len(correo.enviados) == 2  # la ronda de las 19:30 todavía no termina
    _latido(dom(19, 5), tel, correo, tmp_path, cal)
    assert len(tel.llamadas) == 4
    _latido(dom(19, 30), tel, correo, tmp_path, cal)
    assert tel.llamados()[4:] == ["V3"]
    v3 = _estados(tmp_path)["V3"]
    assert v3["estado"] == "monitoreo" and v3["intentos"] == 3 and v3["aviso_pendiente"] is False
    nuevos = correo.enviados[2:]
    assert len(nuevos) == 2
    assert nuevos[0].para == ["eva@m.com"] and "No contestó en 3 llamadas" in nuevos[0].cuerpo
    assert "Control de la ronda de las 19:30" in nuevos[1].asunto and "monitoreo: 2" in nuevos[1].cuerpo
    _latido(dom(19, 35), tel, correo, tmp_path, cal)
    assert len(tel.llamadas) == 5 and len(correo.enviados) == 4


def test_mismo_telefono_espera_10_minutos(tmp_path, cal):
    viajes = [_viaje(1, "ana@m.com"), _viaje(2, "ana@m.com", telefono="+525500000001"), _viaje(3, "eva@m.com")]
    _aprobar(tmp_path, viajes)
    tel, correo = Telefonia({"V1": A_TIEMPO, "V2": A_TIEMPO, "V3": A_TIEMPO}), Correo()
    _latido(dom(13, 0), tel, correo, tmp_path, cal)
    assert tel.llamados() == ["V1", "V3"]
    assert correo.con_asunto("Control") == []  # la ronda no termina: falta V2
    _latido(dom(13, 5), tel, correo, tmp_path, cal)
    assert tel.llamados() == ["V1", "V3"]
    _latido(dom(13, 10), tel, correo, tmp_path, cal)
    assert tel.llamados() == ["V1", "V3", "V2"]
    assert len(correo.con_asunto("Control de la ronda de las 13:00")) == 1


def test_a_las_2100_lo_pendiente_pasa_a_monitoreo(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA[:2])
    sin_respuesta = {**estado_inicial(), "estado": "sin_respuesta", "intentos": 1, "ultimo_intento": dom(13, 0),
                     "historial": [{"fecha": dom(13, 0).isoformat(), "decision": "sin_respuesta",
                                    "conversacion_id": "conv_1", **NO_CONTESTA}]}
    almacen.guardar_estados(DOMINGO, {"V1": sin_respuesta}, raiz=tmp_path)  # V2 sigue pendiente
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    _latido(dom(21, 0), tel, correo, tmp_path, cal)
    assert tel.llamadas == []
    estados = _estados(tmp_path)
    for v, intentos in (("V1", 1), ("V2", 0)):
        assert estados[v]["estado"] == "monitoreo" and estados[v]["intentos"] == intentos
        assert estados[v]["historial"][-1]["motivo"] == "No se pudo completar la llamada"
        assert estados[v]["aviso_pendiente"] is False  # ya se mandó
    assert [a.para for a in correo.con_asunto("caso(s) nuevo(s)")] == [["ana@m.com"], ["luis@m.com"]]
    assert almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)
    assert almacen.ya_hecho(DOMINGO, "correo_1930", raiz=tmp_path)


# --------------------------------------------------------------------------- frenos

def test_detenido_no_llama(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    almacen.detener(DOMINGO, "Pedro", dom(12, 30), raiz=tmp_path)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    _latido(dom(13, 0), tel, correo, tmp_path, cal)
    _latido(dom(19, 30), tel, correo, tmp_path, cal)
    _latido(dom(21, 0), tel, correo, tmp_path, cal)
    assert tel.llamadas == []
    controles = correo.con_asunto("Control de la ronda")
    assert len(controles) == 2 and all("Pedro" in a.cuerpo and "12:30" in a.cuerpo for a in controles)
    assert all(e["estado"] == "pendiente" for e in _estados(tmp_path).values())  # sin conversión a las 21:00


def test_detener_a_media_ronda(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()

    def llamar_y_detener(viaje, variables, env):
        conversacion = tel.llamar(viaje, variables, env)
        almacen.detener(DOMINGO, "Pedro", dom(13, 1), raiz=tmp_path)
        return conversacion

    ejecutar_latido(dom(13, 0), cal, ENV, tmp_path, llamar_y_detener, tel.esperar_resultado, correo.enviar)
    assert tel.llamados() == ["V1"]
    assert _estados(tmp_path)["V1"]["estado"] == "a_tiempo"  # la llamada en curso sí termina


class ApiCaida:
    """llamar falso: lanza ErrorTelefonia mientras 'caida' sea True; si no, llama con la Telefonia falsa."""

    def __init__(self, tel):
        self.tel = tel
        self.caida = True
        self.intentos = []

    def llamar(self, viaje, variables, env):
        self.intentos.append(viaje["viaje"])
        if self.caida:
            raise ErrorTelefonia("ElevenLabs rechazó la llamada (HTTP 500)")
        return self.tel.llamar(viaje, variables, env)


def _latido_api(ahora, api, correo, raiz, cal):
    return ejecutar_latido(ahora, cal, ENV, raiz, api.llamar, api.tel.esperar_resultado, correo.enviar)


def test_tres_fallas_api_suspenden(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 6)])
    api, correo = ApiCaida(Telefonia({})), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2", "V3"]
    assert len(correo.enviados) == 1 and "Fallas de la API" in correo.enviados[0].asunto
    assert "HTTP 500" in correo.enviados[0].cuerpo
    estados = _estados(tmp_path)
    for v in ("V1", "V2", "V3"):  # no se gastó su intento: no hubo llamada
        assert estados[v]["estado"] == "pendiente" and estados[v]["intentos"] == 0
        assert estados[v]["historial"] == [] and estados[v]["fallas_api"] == 1
    assert not almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)
    assert any("HTTP 500" in f["texto"] for f in almacen.fallas_del_dia(DOMINGO, raiz=tmp_path))


def test_suspension_sigue_en_el_siguiente_latido_y_luego_un_sondeo(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 6)])
    api, correo = ApiCaida(Telefonia({})), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)
    _latido_api(dom(13, 5), api, correo, tmp_path, cal)
    _latido_api(dom(13, 10), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2", "V3"]  # 15 minutos sin llamar
    _latido_api(dom(13, 15), api, correo, tmp_path, cal)
    assert api.intentos[3:] == ["V4"]  # un solo sondeo por latido, con un viaje sin fallas
    _latido_api(dom(13, 20), api, correo, tmp_path, cal)
    assert api.intentos[4:] == ["V5"]
    assert len(correo.con_asunto("Fallas de la API")) == 1  # un aviso por caída
    assert all(e["intentos"] == 0 for e in _estados(tmp_path).values())


def test_la_api_se_recupera_y_se_llama_a_todos(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 6)])
    respuestas = {f"V{n}": A_TIEMPO for n in range(1, 6)}
    api, correo = ApiCaida(Telefonia(respuestas)), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)
    api.caida = False
    _latido_api(dom(13, 15), api, correo, tmp_path, cal)
    # El sondeo (V4, sin fallas) salió: se reanuda en el mismo latido, en el orden de la lista
    assert api.tel.llamados() == ["V4", "V1", "V2", "V3", "V5"]
    estados = _estados(tmp_path)
    assert all(e["estado"] == "a_tiempo" and e["intentos"] == 1 for e in estados.values())
    assert almacen.leer_estado_api(DOMINGO, raiz=tmp_path)["suspendida_desde"] is None
    assert len(correo.con_asunto("Control de la ronda de las 13:00")) == 1


def test_otra_caida_avisa_otra_vez(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 8)])
    respuestas = {f"V{n}": NO_CONTESTA for n in range(1, 8)}
    api, correo = ApiCaida(Telefonia(respuestas)), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)   # caída 1: V1, V2, V3
    api.caida = False
    _latido_api(dom(13, 15), api, correo, tmp_path, cal)  # se recupera: llama a los 7
    api.caida = True
    _latido_api(dom(19, 0), api, correo, tmp_path, cal)   # caída 2 en los reintentos
    assert len(correo.con_asunto("Fallas de la API")) == 2


def test_falla_de_api_no_se_reintenta_en_el_mismo_latido(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA[:2])
    api, correo = ApiCaida(Telefonia({})), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2"]  # cada uno una vez; dos fallas, aún sin suspender
    _latido_api(dom(13, 5), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2"]  # 10 minutos entre intentos del mismo viaje
    _latido_api(dom(13, 10), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2", "V1"]  # la tercera falla seguida (en otro latido) suspende
    assert len(correo.con_asunto("Fallas de la API")) == 1
    assert almacen.leer_estado_api(DOMINGO, raiz=tmp_path)["suspendida_desde"] == dom(13, 10)


def test_caida_toda_la_tarde_pasa_a_monitoreo_a_las_2100(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    api, correo = ApiCaida(Telefonia({})), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)
    _latido_api(dom(21, 0), api, correo, tmp_path, cal)
    estados = _estados(tmp_path)
    assert all(e["estado"] == "monitoreo" and e["intentos"] == 0 for e in estados.values())
    assert len(correo.con_asunto("caso(s) nuevo(s)")) == 3


def test_sondeo_prefiere_un_viaje_sin_fallas(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 5)])
    api, correo = ApiCaida(Telefonia({})), Correo()
    _latido_api(dom(13, 0), api, correo, tmp_path, cal)  # V1, V2, V3 fallan: se suspende
    _latido_api(dom(13, 15), api, correo, tmp_path, cal)
    assert api.intentos == ["V1", "V2", "V3", "V4"]  # V4 no ha fallado: se prueba con él
    _latido_api(dom(13, 20), api, correo, tmp_path, cal)
    assert api.intentos[4:] == ["V1"]  # ya todos fallaron una vez: el primero que toque


def test_un_numero_que_no_marca_pasa_a_monitoreo_sin_detener_la_ronda(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia({"V2": A_TIEMPO, "V3": A_TIEMPO}), Correo()
    intentos_v1 = []

    def llamar(viaje, variables, env):
        if viaje["viaje"] == "V1":  # ElevenLabs rechaza solo este número
            intentos_v1.append(viaje["viaje"])
            raise ErrorTelefonia("ElevenLabs rechazó la llamada (HTTP 422)")
        return tel.llamar(viaje, variables, env)

    def un_latido(ahora):
        ejecutar_latido(ahora, cal, ENV, tmp_path, llamar, tel.esperar_resultado, correo.enviar)

    un_latido(dom(13, 0))
    assert tel.llamados() == ["V2", "V3"] and len(intentos_v1) == 1
    assert len(correo.con_asunto("Control de la ronda de las 13:00")) == 1  # V1 no detiene los correos
    un_latido(dom(13, 5))
    assert len(intentos_v1) == 1  # 10 minutos entre intentos
    un_latido(dom(13, 10))
    un_latido(dom(13, 20))
    assert len(intentos_v1) == 3
    v1 = _estados(tmp_path)["V1"]
    assert v1["estado"] == "monitoreo" and v1["aviso_pendiente"] is True and v1["intentos"] == 0
    assert v1["historial"][-1]["motivo"] == "No se pudo marcar a este número (falla técnica)"
    assert any("V1" in f["texto"] and "monitoreo" in f["texto"]
               for f in almacen.fallas_del_dia(DOMINGO, raiz=tmp_path))
    un_latido(dom(13, 30))
    assert len(intentos_v1) == 3  # ya no se le marca
    assert correo.con_asunto("Fallas de la API") == []  # no es una caída de la API
    un_latido(dom(19, 30))
    a_ana = [a for a in correo.con_asunto("caso(s) nuevo(s)") if a.para == ["ana@m.com"]]
    assert len(a_ana) == 1 and "No se pudo marcar a este número" in a_ana[0].cuerpo


def test_una_llamada_buena_reinicia_las_fallas_seguidas(tmp_path, cal):
    _aprobar(tmp_path, [_viaje(n, "ana@m.com") for n in range(1, 6)])
    tel, correo = Telefonia({"V3": A_TIEMPO}), Correo()

    def llamar(viaje, variables, env):
        if viaje["viaje"] != "V3":
            tel.llamadas.append((viaje["viaje"], variables))
            raise ErrorTelefonia("ElevenLabs rechazó la llamada (HTTP 500)")
        return tel.llamar(viaje, variables, env)

    ejecutar_latido(dom(13, 0), cal, ENV, tmp_path, llamar, tel.esperar_resultado, correo.enviar)
    assert tel.llamados() == ["V1", "V2", "V3", "V4", "V5"]
    assert correo.con_asunto("Fallas de la API") == []


def test_tope_del_domingo(tmp_path, cal):
    cal["tope_llamadas_por_domingo"] = 2
    tel, correo = _ronda_1300(tmp_path, cal)
    assert tel.llamados() == ["V1", "V2"]
    control = correo.con_asunto("Control de la ronda de las 13:00")
    assert len(control) == 1 and "tope" in control[0].cuerpo


def test_lista_blanca_en_ensayo(tmp_path, cal):
    cal["ensayo"] = True
    lista = tmp_path / "permitidos.txt"
    lista.write_text("+525500000001\n+525500000002  # V3 se quitó después de aprobar\n", encoding="utf-8")
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    _latido(dom(13, 0), tel, correo, tmp_path, cal, ruta_lista=lista)
    assert tel.llamados() == ["V1", "V2"]
    assert _estados(tmp_path)["V3"]["estado"] == "pendiente"
    control = correo.con_asunto("Control de la ronda de las 13:00")
    assert len(control) == 1
    assert "V3" in control[0].cuerpo and "lista blanca" in control[0].cuerpo
    assert "+525500000003" not in control[0].cuerpo  # solo los últimos 4 dígitos
    # A las 21:00 no queda sin que nadie sepa: pasa a monitoreo
    _latido(dom(21, 0), tel, correo, tmp_path, cal, ruta_lista=lista)
    assert tel.llamados() == ["V1", "V2"]
    assert _estados(tmp_path)["V3"]["estado"] == "monitoreo"
    assert any("V3" in a.cuerpo for a in correo.con_asunto("caso(s) nuevo(s)") if a.para == ["eva@m.com"])


def test_lista_blanca_ilegible_no_llama(tmp_path, cal):
    cal["ensayo"] = True
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    bitacora = _latido(dom(13, 0), tel, correo, tmp_path, cal, ruta_lista=tmp_path / "no_existe.txt")
    assert tel.llamadas == []
    assert any("lista blanca" in linea for linea in bitacora)


def test_falta_correo_control_no_detiene_las_llamadas(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    env = {k: v for k, v in ENV.items() if k != "CORREO_CONTROL"}
    bitacora = _latido(dom(13, 0), tel, correo, tmp_path, cal, env=env)
    assert tel.llamados() == ["V1", "V2", "V3"]
    assert any("CORREO_CONTROL" in linea for linea in bitacora)
    control = correo.con_asunto("Control de la ronda de las 13:00")
    assert len(control) == 1 and control[0].para == [] and "CORREO_CONTROL" in control[0].cuerpo


def test_falta_configuracion_de_llamadas_no_llama(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA)
    tel, correo = Telefonia(RESPUESTAS_RONDA), Correo()
    env = {k: v for k, v in ENV.items() if k != "ELEVENLABS_AGENT_ID_SEGUIMIENTO"}
    bitacora = _latido(dom(13, 0), tel, correo, tmp_path, cal, env=env)
    assert tel.llamadas == []
    assert all(e["intentos"] == 0 for e in _estados(tmp_path).values())
    assert any("ELEVENLABS_AGENT_ID_SEGUIMIENTO" in linea for linea in bitacora)


# --------------------------------------------------------------------------- llamadas en curso

def _en_curso(raiz, conversacion, inicio):
    _aprobar(raiz, VIAJES_RONDA[:1])
    estado = almacen.estados_de(DOMINGO, VIAJES_RONDA[:1], raiz)["V1"]
    estado.update(estado="en_curso", en_curso={"conversacion_id": conversacion, "inicio": inicio})
    almacen.guardar_estados(DOMINGO, {"V1": estado}, raiz=raiz)


def test_en_curso_se_resuelve(tmp_path, cal):
    _en_curso(tmp_path, "conv_previa", dom(13, 0))
    tel, correo = Telefonia({"conv_previa": A_TIEMPO}), Correo()
    _latido(dom(13, 5), tel, correo, tmp_path, cal)
    assert tel.llamadas == [] and tel.consultas == ["conv_previa"]
    v1 = _estados(tmp_path)["V1"]
    assert v1["estado"] == "a_tiempo" and v1["intentos"] == 1 and v1["en_curso"] is None
    assert v1["historial"][-1]["conversacion_id"] == "conv_previa"
    assert v1["historial"][-1]["fecha"] == dom(13, 0).isoformat()  # cuenta desde que empezó la llamada


def test_resultado_que_no_llega_deja_en_curso(tmp_path, cal):
    _aprobar(tmp_path, VIAJES_RONDA[:1])
    tel, correo = Telefonia({"V1": ErrorTelefonia("La conversación no terminó en 600 segundos")}), Correo()
    _latido(dom(13, 0), tel, correo, tmp_path, cal)
    v1 = _estados(tmp_path)["V1"]
    assert v1["estado"] == "en_curso" and v1["en_curso"]["conversacion_id"] == "conv_V1_1"
    assert v1["en_curso"]["inicio"] == dom(13, 0)
    # El siguiente latido la resuelve por su conversación, sin volver a marcar
    tel.respuestas["V1"] = A_TIEMPO
    _latido(dom(13, 5), tel, correo, tmp_path, cal)
    assert len(tel.llamadas) == 1
    assert _estados(tmp_path)["V1"]["estado"] == "a_tiempo"


def test_en_curso_que_nunca_termina_cuenta_sin_respuesta(tmp_path, cal):
    _en_curso(tmp_path, "conv_perdida", dom(13, 0))
    tel, correo = Telefonia({"conv_perdida": ErrorTelefonia("No se pudo consultar la conversación (HTTP 404)")}), Correo()
    _latido(dom(13, 30), tel, correo, tmp_path, cal)
    assert _estados(tmp_path)["V1"]["estado"] == "en_curso"
    _latido(dom(14, 0), tel, correo, tmp_path, cal)
    v1 = _estados(tmp_path)["V1"]
    assert v1["estado"] == "sin_respuesta" and v1["intentos"] == 1 and v1["en_curso"] is None
    assert tel.llamadas == []


# --------------------------------------------------------------------------- avisos

def test_aviso_que_falla_queda_pendiente(tmp_path, cal):
    tel, correo = _ronda_1300(tmp_path, cal, correo=Correo(resultado=False))
    assert _estados(tmp_path)["V2"]["aviso_pendiente"] is True
    assert almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)  # no se reintenta cada 5 minutos
    enviados = len(correo.enviados)
    _latido(dom(13, 30), tel, correo, tmp_path, cal)
    assert len(correo.enviados) == enviados
    # En el siguiente envío (19:30) sale junto con los casos nuevos
    correo.resultado = True
    _latido(dom(19, 0), tel, correo, tmp_path, cal)
    _latido(dom(19, 30), tel, correo, tmp_path, cal)
    a_luis = [a for a in correo.enviados[enviados:] if a.para == ["luis@m.com"]]
    assert len(a_luis) == 1 and "V2" in a_luis[0].cuerpo
    assert _estados(tmp_path)["V2"]["aviso_pendiente"] is False


def test_resumen_lunes_una_vez(tmp_path, cal):
    tel, correo = _ronda_1300(tmp_path, cal)
    _latido(dom(19, 0), tel, correo, tmp_path, cal)
    _latido(dom(19, 30), tel, correo, tmp_path, cal)
    _latido(lun(6, 55), tel, correo, tmp_path, cal)
    assert correo.con_asunto("Resumen") == []
    _latido(lun(7, 0), tel, correo, tmp_path, cal)
    resumen = correo.con_asunto("Resumen")
    assert len(resumen) == 4  # ana, luis, eva y control
    assert resumen[-1].para == [CONTROL] and resumen[-1].adjunto.exists()
    _latido(lun(7, 5), tel, correo, tmp_path, cal)
    assert len(correo.con_asunto("Resumen")) == 4
    assert len(tel.llamadas) == 5


# --------------------------------------------------------------------------- año de la fecha estimada

@pytest.mark.parametrize("cita, dicha, esperada", [
    ("2026-11-30", "2025-11-30", "2026-11-30"),   # año equivocado, mismo mes
    ("2026-11-30", "2027-12-01", "2026-12-01"),
    ("2026-11-30", "2026-12-01", "2026-12-01"),   # ya está bien
    ("2026-12-31", "2026-01-02", "2027-01-02"),   # diciembre -> enero
    ("2026-12-31", "2025-01-02", "2027-01-02"),
    ("2027-01-04", "2027-12-31", "2026-12-31"),   # cita en enero, llega el 31 de diciembre
    ("2026-12-01", "2025-11-30", "2026-11-30"),   # la víspera, en el mes anterior
    ("2026-11-30", "", ""),
    ("2026-11-30", "mañana", "mañana"),
    ("2026-11-30", None, None),
])
def test_normalizar_fecha_estimada(cita, dicha, esperada):
    viaje = {**_viaje(1, "ana@m.com"), "fecha_cita": cita}
    resultado = {**A_TIEMPO, "fecha_estimada": dicha}
    assert normalizar_fecha_estimada(viaje, resultado)["fecha_estimada"] == esperada
    assert resultado["fecha_estimada"] == dicha  # no modifica el original


def test_fecha_con_otro_ano_no_da_a_tiempo(tmp_path, cal):
    # Dijo "sí" pero llega el martes 1 de diciembre: la extracción puso 2025 y sin corregir parecería antes de la cita
    _aprobar(tmp_path, VIAJES_RONDA[:1])
    tel, correo = Telefonia({"V1": {**A_TIEMPO, "fecha_estimada": "2025-12-01"}}), Correo()
    _latido(dom(13, 0), tel, correo, tmp_path, cal)
    v1 = _estados(tmp_path)["V1"]
    assert v1["estado"] == "monitoreo" and v1["historial"][-1]["fecha_estimada"] == "2026-12-01"


# --------------------------------------------------------------------------- main()

@pytest.fixture
def main_aislado(tmp_path, monkeypatch, cal):
    """main() sin el .env real ni red: ejecutar_latido falso y la bitácora en tmp_path."""
    llamadas = []
    monkeypatch.setattr(latido, "RAIZ_DATOS", tmp_path)
    monkeypatch.setattr(latido, "cargar_calendario", lambda: cal)
    monkeypatch.setattr(latido, "cargar_env", lambda nombres: ({"ELEVENLABS_API_KEY": "secreto-abcdef123456"}, []))

    def falso(*args, **kw):
        llamadas.append((args, kw))
        return ["Viaje V1: llamada 1 -> a_tiempo"]

    monkeypatch.setattr(latido, "ejecutar_latido", falso)
    return llamadas


def test_main_escribe_la_bitacora(tmp_path, main_aislado, capsys):
    assert latido.main() == 0
    (ahora, cal, env, raiz, llamar, esperar, enviar), kw = main_aislado[0]
    assert ahora.tzinfo is not None and raiz == tmp_path
    assert llamar is telefonia.llamar and esperar is telefonia.esperar_resultado and enviar is avisos.enviar
    lineas = (tmp_path / "latido.log").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 1 and lineas[0].endswith("Viaje V1: llamada 1 -> a_tiempo")
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", lineas[0])  # empieza con la fecha y hora
    assert "secreto-abcdef123456" not in capsys.readouterr().out


def test_main_error_inesperado_sale_con_1(tmp_path, main_aislado, monkeypatch, capsys):
    def revienta(*a, **k):
        raise RuntimeError("se cayó el disco")

    monkeypatch.setattr(latido, "ejecutar_latido", revienta)
    assert latido.main() == 1
    texto = (tmp_path / "latido.log").read_text(encoding="utf-8")
    assert "RuntimeError" in texto and "se cayó el disco" in texto
    assert "Traceback" not in capsys.readouterr().err
