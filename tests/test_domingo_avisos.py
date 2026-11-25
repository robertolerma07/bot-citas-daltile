"""Pruebas de los avisos por correo y del Excel del resumen del domingo (SMTP falso, sin red)."""

import smtplib
import ssl
from datetime import datetime

import openpyxl
import pytest

from domingo import avisos
from domingo.avisos import Aviso
from lib.seguridad import ZONA_CDMX

DOMINGO = "2026-11-29"
CONTROL = "roberto@ejemplo.com"
CLAVE = "clave-secreta-smtp-1234"
ENV = {"SMTP_HOST": "smtp.ejemplo.com", "SMTP_PUERTO": "587", "SMTP_USUARIO": "bot@ejemplo.com",
       "SMTP_PASSWORD": CLAVE}


def _viaje(n, correo, tipo="Hora", hora="08:00"):
    return {"viaje": f"V{n}", "linea": "Linea Norte", "operador": f"Operador {n}", "telefono": f"+52555000000{n}",
            "cliente": f"Cliente {n}", "destino": "Monterrey", "fecha_cita": "2026-11-30", "tipo_cita": tipo,
            "hora": hora, "correo_monitoreo": correo, "telefono_monitoreo": "+525550001111",
            "limite": hora if tipo == "Hora" else "16:00", "_fila": n + 1}


def _entrada(decision, dicha="a las 10", motivo="tráfico", conv="conv_abc"):
    return {"fecha": "2026-11-29T13:00:00-06:00", "decision": decision, "conversacion_id": conv,
            "hablo_con_operador": decision != "sin_respuesta", "llega_antes_de_la_cita": "no",
            "entrega_realizada": "no aplica", "hora_estimada_dicha": dicha, "hora_estimada": "10:00",
            "fecha_estimada": "2026-11-30", "motivo": motivo}


def _estado(estado, intentos=1, historial=None, aviso=False):
    return {"estado": estado, "intentos": intentos, "ultimo_intento": datetime(2026, 11, 29, 13, 0, tzinfo=ZONA_CDMX),
            "en_curso": None, "historial": historial or [], "aviso_pendiente": aviso, "fallas_api": 0}


def _escenario():
    viajes = [_viaje(1, "ana@m.com"), _viaje(2, "ana@m.com"), _viaje(3, "luis@m.com", tipo="Día"),
              _viaje(4, "luis@m.com")]
    estados = {
        "V1": _estado("monitoreo", 1, [_entrada("monitoreo")], True),
        "V2": _estado("monitoreo", 3, [_entrada("sin_respuesta", None, None)] * 3, True),
        "V3": _estado("monitoreo", 1, [_entrada("monitoreo", "como a las 5", "falla", "conv_xyz")], True),
        "V4": _estado("a_tiempo", 1, [_entrada("a_tiempo", "antes de las 8", None)]),
        "VIEJO": _estado("monitoreo", 1, [_entrada("monitoreo")], True),  # viaje ya no aprobado
    }
    return viajes, estados


class SmtpFalso:
    enviados = []
    conexiones = []
    contextos = []
    falla = None

    def __init__(self, host, puerto, timeout=None):
        if SmtpFalso.falla:
            raise SmtpFalso.falla
        SmtpFalso.conexiones.append((host, puerto, timeout))
        self.pasos = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, *a, context=None, **k):
        self.pasos.append("starttls")
        SmtpFalso.contextos.append(context)

    def login(self, usuario, clave):
        self.pasos.append(("login", usuario, clave))

    def send_message(self, mensaje, *a, **k):
        assert self.pasos[0] == "starttls"
        SmtpFalso.enviados.append(mensaje)


@pytest.fixture(autouse=True)
def _limpia():
    SmtpFalso.enviados, SmtpFalso.conexiones, SmtpFalso.contextos, SmtpFalso.falla = [], [], [], None


def test_avisos_de_casos_por_persona():
    viajes, estados = _escenario()
    lista = avisos.avisos_de_casos(viajes, estados, CONTROL)
    assert len(lista) == 2
    por_persona = {a.para[0]: a for a in lista}
    assert set(por_persona) == {"ana@m.com", "luis@m.com"}
    ana, luis = por_persona["ana@m.com"], por_persona["luis@m.com"]
    assert ana.copia == [CONTROL] and luis.copia == [CONTROL]
    assert "V1" in ana.cuerpo and "V2" in ana.cuerpo and "V3" not in ana.cuerpo
    assert "V3" in luis.cuerpo and "V1" not in luis.cuerpo
    assert "V4" not in ana.cuerpo + luis.cuerpo  # a_tiempo no aparece
    assert "VIEJO" not in ana.cuerpo + luis.cuerpo
    assert "[Sofía domingo]" in ana.asunto
    assert "a las 08:00" in ana.cuerpo and "antes de las 16:00" in luis.cuerpo
    assert "como a las 5" in luis.cuerpo and "falla" in luis.cuerpo and "conv_xyz" in luis.cuerpo
    assert "No contestó en 3 llamadas" in ana.cuerpo
    assert "+525550000001" in ana.cuerpo


def test_avisos_de_casos_sin_casos_no_manda():
    viajes = [_viaje(4, "luis@m.com")]
    assert avisos.avisos_de_casos(viajes, {"V4": _estado("a_tiempo")}, CONTROL) == []


def test_aviso_de_control_sin_casos():
    viajes = [_viaje(4, "luis@m.com"), _viaje(5, "luis@m.com")]
    estados = {"V4": _estado("a_tiempo", 1, [_entrada("a_tiempo")]), "V5": _estado("pendiente", 0)}
    a = avisos.aviso_de_control(DOMINGO, "13:00", viajes, estados, CONTROL, [])
    assert a.para == [CONTROL] and a.asunto.startswith("[Sofía domingo] " + DOMINGO)
    for texto in ("llamadas: 1", "a tiempo: 1", "monitoreo: 0", "pendientes: 1"):
        assert texto in a.cuerpo
    assert "fallas" not in a.cuerpo.lower()


def test_aviso_de_control_con_fallas_y_conteos():
    viajes, estados = _escenario()
    a = avisos.aviso_de_control(DOMINGO, "19:30", viajes, estados, CONTROL, ["no salió el correo a ana"])
    assert "llamadas: 6" in a.cuerpo and "monitoreo: 3" in a.cuerpo and "a tiempo: 1" in a.cuerpo
    assert "entregado: 0" in a.cuerpo and "no salió el correo a ana" in a.cuerpo


def test_avisos_de_aprobacion_sin_lista_detenido_y_fallas():
    viajes, _ = _escenario()
    apr = {"quien": "Maria", "cuando": datetime(2026, 11, 29, 10, 0, tzinfo=ZONA_CDMX), "viajes": viajes}
    a = avisos.aviso_de_aprobacion(DOMINGO, apr, CONTROL)
    assert "Maria" in a.cuerpo and "V1" in a.cuerpo and "4" in a.cuerpo and a.para == [CONTROL]
    s = avisos.aviso_sin_lista(DOMINGO, CONTROL)
    assert s.para == [CONTROL] and DOMINGO in s.asunto
    d = avisos.aviso_detenido(DOMINGO, "Pedro", datetime(2026, 11, 29, 13, 5, tzinfo=ZONA_CDMX), CONTROL)
    assert "Pedro" in d.cuerpo and "13:05" in d.cuerpo
    f = avisos.aviso_fallas_api(DOMINGO, ["ElevenLabs 500"], CONTROL)
    assert "ElevenLabs 500" in f.cuerpo


def test_resumen_y_excel(tmp_path):
    viajes, estados = _escenario()
    ruta = tmp_path / "resumen.xlsx"
    lista = avisos.avisos_de_resumen(DOMINGO, viajes, estados, CONTROL, ruta)
    assert ruta.exists()
    libro = openpyxl.load_workbook(ruta)
    assert libro.sheetnames == ["Viajes", "Historial"]
    assert libro["Viajes"].max_row == 1 + 4
    assert libro["Historial"].max_row == 1 + 1 + 3 + 1 + 1  # V1, V2 (3), V3, V4
    assert len(lista) == 3
    control = [a for a in lista if a.para == [CONTROL]][0]
    assert control.adjunto == ruta
    assert all(a.adjunto is None for a in lista if a.para != [CONTROL])
    ana = [a for a in lista if a.para == ["ana@m.com"]][0]
    assert "V1" in ana.cuerpo and "V4" not in ana.cuerpo


def test_enviar_ok(tmp_path):
    adj = tmp_path / "r.xlsx"
    adj.write_bytes(b"datos")
    a = Aviso(para=["ana@m.com"], copia=[CONTROL], asunto="[Sofía domingo] x", cuerpo="hola", adjunto=adj)
    assert avisos.enviar(a, ENV, smtp=SmtpFalso) is True
    assert SmtpFalso.conexiones == [("smtp.ejemplo.com", 587, 30)]
    m = SmtpFalso.enviados[0]
    assert m["From"] == "bot@ejemplo.com" and m["To"] == "ana@m.com" and m["Cc"] == CONTROL
    assert any(p.get_filename() == "r.xlsx" for p in m.iter_attachments())


def test_enviar_falla_sin_traza(capsys):
    SmtpFalso.falla = OSError("sin red")
    assert avisos.enviar(Aviso(["a@m.com"], [], "x", "y"), ENV, smtp=SmtpFalso) is False
    SmtpFalso.falla = smtplib.SMTPAuthenticationError(535, b"mal")
    assert avisos.enviar(Aviso(["a@m.com"], [], "x", "y"), ENV, smtp=SmtpFalso) is False
    assert CLAVE not in capsys.readouterr().out


def test_enviar_sin_config():
    llamadas = []

    def smtp(*a, **k):
        llamadas.append(a)

    env = {"SMTP_HOST": "x"}
    assert avisos.enviar(Aviso(["a@m.com"], [], "x", "y"), env, smtp=smtp) is False
    assert llamadas == []


def test_canal_no_implementado():
    with pytest.raises(NotImplementedError):
        avisos.enviar(Aviso(["a@m.com"], [], "x", "y"), ENV, canal="whatsapp", smtp=SmtpFalso)


def test_ninguna_key_en_el_cuerpo(tmp_path, capsys):
    viajes, estados = _escenario()
    env = dict(ENV)
    todos = avisos.avisos_de_casos(viajes, estados, CONTROL)
    todos.append(avisos.aviso_de_control(DOMINGO, "13:00", viajes, estados, CONTROL, []))
    todos += avisos.avisos_de_resumen(DOMINGO, viajes, estados, CONTROL, tmp_path / "r.xlsx")
    for a in todos:
        assert env["SMTP_PASSWORD"] not in a.asunto + a.cuerpo
        avisos.enviar(a, env, smtp=SmtpFalso)
    assert CLAVE not in capsys.readouterr().out
    for m in SmtpFalso.enviados:
        assert CLAVE not in m.as_string()


def test_casos_sin_correo_de_monitoreo_van_a_control(tmp_path):
    viajes, estados = _escenario()
    viajes.append(_viaje(6, ""))
    estados["V6"] = _estado("monitoreo", 1, [_entrada("monitoreo")], True)
    lista = avisos.avisos_de_casos(viajes, estados, CONTROL)
    sin = [a for a in lista if a.para == [CONTROL]]
    assert len(sin) == 1 and "sin persona de monitoreo" in sin[0].asunto.lower()
    assert "V6" in sin[0].cuerpo and "V1" not in sin[0].cuerpo
    assert all("V6" not in a.cuerpo for a in lista if a.para != [CONTROL])
    resumen = avisos.avisos_de_resumen(DOMINGO, viajes, estados, CONTROL, tmp_path / "r.xlsx")
    control = [a for a in resumen if a.para == [CONTROL]]
    assert len(control) == 1 and "V6" in control[0].cuerpo
    assert "sin persona de monitoreo" in control[0].cuerpo.lower()
    assert all("V6" not in a.cuerpo for a in resumen if a.para != [CONTROL])


def test_enviar_destinatario_invalido_regresa_false(capsys):
    a = Aviso(["ana@m.com\r\nBcc: x@y.com"], [], "x", "y")
    assert avisos.enviar(a, ENV, smtp=SmtpFalso) is False
    assert SmtpFalso.enviados == [] and CLAVE not in capsys.readouterr().out


def test_enviar_starttls_verifica_el_certificado():
    # La contraseña de Gmail viaja después del STARTTLS: el certificado del servidor se verifica
    assert avisos.enviar(Aviso(["a@m.com"], [], "x", "y"), ENV, smtp=SmtpFalso) is True
    contexto = SmtpFalso.contextos[0]
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname is True


def _nota(motivo):
    """Nota del historial que no es una llamada (paso a monitoreo de las 21:00 o por fallas al marcar)."""
    return {"fecha": "2026-11-29T21:00:00-06:00", "decision": "monitoreo", "conversacion_id": None,
            "hablo_con_operador": None, "llega_antes_de_la_cita": None, "entrega_realizada": None,
            "hora_estimada_dicha": None, "hora_estimada": None, "fecha_estimada": None, "motivo": motivo}


def test_las_notas_del_historial_no_cuentan_como_llamadas(tmp_path):
    viajes = [_viaje(1, "ana@m.com"), _viaje(2, "ana@m.com")]
    estados = {
        # Dos llamadas sin respuesta y luego, a las 21:00, la nota de que pasa a monitoreo
        "V1": _estado("monitoreo", 2, [_entrada("sin_respuesta", None, None)] * 2
                      + [_nota("No se pudo completar la llamada")], True),
        # Nunca se pudo marcar: ninguna llamada, solo la nota
        "V2": _estado("monitoreo", 0, [_nota("No se pudo marcar a este número (falla técnica)")], True),
    }
    control = avisos.aviso_de_control(DOMINGO, "19:30", viajes, estados, CONTROL, [])
    assert "llamadas: 2" in control.cuerpo
    resumen = avisos.avisos_de_resumen(DOMINGO, viajes, estados, CONTROL, tmp_path / "r.xlsx")
    assert all("llamadas: 2" in a.cuerpo for a in resumen)
    hoja = openpyxl.load_workbook(tmp_path / "r.xlsx")["Viajes"]
    columna = [c.value for c in hoja[1]].index("Llamadas")
    assert [fila[columna] for fila in hoja.iter_rows(min_row=2, values_only=True)] == [2, 0]
    casos = avisos.avisos_de_casos(viajes, estados, CONTROL)[0].cuerpo
    assert "Llamadas hechas: 2" in casos and "Llamadas hechas: 0" in casos
