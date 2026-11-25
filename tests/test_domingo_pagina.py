r"""
Pruebas de la página web del domingo de seguimiento (subir, aprobar, estado y detener).

Uso:
    .venv\Scripts\python -m pytest tests/test_domingo_pagina.py -q
"""

import io
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from domingo import almacen  # noqa: E402
from domingo.calendario import cargar_calendario  # noqa: E402
from domingo.pagina import crear_app, ocultar_telefonos  # noqa: E402
from domingo.viajes import COLUMNAS_VIAJE  # noqa: E402
from lib.seguridad import ZONA_CDMX  # noqa: E402

LISTA = RAIZ / "datos" / "numeros_demo.txt"
VIAJES_OK = RAIZ / "datos" / "viajes_prueba.xlsx"
VIAJES_MALOS = RAIZ / "datos" / "viajes_con_errores.xlsx"
DOMINGO = date(2026, 11, 29)
VIERNES = datetime(2026, 11, 27, 18, 0, tzinfo=ZONA_CDMX)
DOMINGO_11 = datetime(2026, 11, 29, 11, 0, tzinfo=ZONA_CDMX)
CLAVE = "clave-de-prueba"
ENV = {"PAGINA_PASSWORD": CLAVE, "PAGINA_SECRETO": "s" * 40, "CORREO_CONTROL": "control@ejemplo.com"}
PATRON_TOKEN = re.compile(r'name="csrf" value="([^"]+)"')


class Contexto:
    """App de prueba con reloj movible y un envío de avisos falso."""

    def __init__(self, tmp_path, enviar_ok=True, ruta_lista=LISTA):
        self.ahora = VIERNES
        self.avisos = []
        self.enviar_ok = enviar_ok
        self.raiz = tmp_path / "domingo"
        self.env = dict(ENV)
        self.cal = cargar_calendario()
        self.campos = {}
        self.app = crear_app(self.raiz, self.env, self.cal, reloj=lambda: self.ahora,
                             enviar=self._enviar, ruta_lista=ruta_lista)
        self.cliente = self.app.test_client()

    def en(self, momento):
        """Mueve el reloj sin vencer la sesión (que dura 12 horas): como si hubiera entrado en ese momento."""
        self.ahora = momento
        with self.cliente.session_transaction() as sesion:
            if sesion.get("entro"):
                sesion["entro_en"] = momento.timestamp()

    def _enviar(self, aviso, env):
        self.avisos.append(aviso)
        return self.enviar_ok

    def token(self, ruta="/entrar"):
        return PATRON_TOKEN.search(self.cliente.get(ruta).get_data(as_text=True)).group(1)

    def entrar(self, clave=CLAVE):
        return self.cliente.post("/entrar", data={"csrf": self.token(), "password": clave})

    def subir(self, ruta=VIAJES_OK, nombre="viajes.xlsx", contenido=None):
        token = self.token("/")
        datos = contenido if contenido is not None else Path(ruta).read_bytes()
        r = self.cliente.post("/subir", data={"csrf": token, "archivo": (io.BytesIO(datos), nombre)},
                              content_type="multipart/form-data")
        self.campos = self._campos_de(texto(r))
        return r

    @staticmethod
    def _campos_de(html):
        """Los campos ocultos del formulario de aprobar (la subida, el domingo y el total que se revisó)."""
        return {n: v for n, v in re.findall(r'name="(subida|domingo|n)" value="([^"]*)"', html)}

    def aprobar(self, nombre="Ana Pérez", campos=None):
        datos = {"csrf": self.token("/"), "nombre": nombre, **(self.campos if campos is None else campos)}
        r = self.cliente.post("/aprobar", data=datos)
        if r.status_code != 302:  # si la página volvió a mostrar la revisión, esos son los campos vigentes
            self.campos = self._campos_de(texto(r)) or self.campos
        return r

    def detener(self, nombre="Ana Pérez"):
        return self.cliente.post("/detener", data={"csrf": self.token("/"), "nombre": nombre})


@pytest.fixture
def ctx(tmp_path):
    return Contexto(tmp_path)


@pytest.fixture
def adentro(ctx):
    ctx.entrar()
    return ctx


def texto(respuesta):
    return respuesta.get_data(as_text=True)


def excel_con(ruta, **cambios):
    fila = {"viaje": "200001", "linea": "Fletes Rápidos de Occidente", "operador": "Miguel Ángel Torres",
            "telefono": "+525500000001", "cliente": "Cerámicas y Acabados Tapatíos",
            "destino": "Zapopan, Jalisco", "fecha_cita": "2026-11-28", "tipo_cita": "Hora", "hora": "10:00",
            "correo_monitoreo": "monitoreo@ejemplo.com", "telefono_monitoreo": "+525500000003"}
    fila.update(cambios)
    libro = Workbook()
    hoja = libro.active
    hoja.append(COLUMNAS_VIAJE)
    hoja.append([fila[c] for c in COLUMNAS_VIAJE])
    libro.save(ruta)
    return ruta


# --- entrar -------------------------------------------------------------------------------------

def test_sin_entrar_redirige(ctx):
    for ruta in ("/", "/aprobar", "/detener"):
        r = ctx.cliente.get(ruta)
        assert r.status_code == 302 and "/entrar" in r.headers["Location"], ruta


def test_entrar_con_la_contrasena_buena(ctx):
    r = ctx.entrar()
    assert r.status_code == 302
    assert ctx.cliente.get("/").status_code == 200


def test_contrasena_mala(ctx):
    r = ctx.entrar("otra-clave")
    assert r.status_code == 401
    assert "incorrecta" in texto(r)
    assert ctx.cliente.get("/").status_code == 302


def test_bloqueo_tras_5_intentos(ctx):
    token = ctx.token()
    for _ in range(5):
        assert ctx.cliente.post("/entrar", data={"csrf": token, "password": "mala"}).status_code == 401
    # Bloqueada: ni con la contraseña buena
    r = ctx.cliente.post("/entrar", data={"csrf": token, "password": CLAVE})
    assert r.status_code == 429
    assert ctx.cliente.get("/").status_code == 302
    # Pasados los 15 minutos vuelve a dejar entrar
    ctx.ahora += timedelta(minutes=16)
    assert ctx.cliente.post("/entrar", data={"csrf": token, "password": CLAVE}).status_code == 302


def test_sin_contrasena_configurada_no_arranca(tmp_path):
    with pytest.raises(ValueError):
        crear_app(tmp_path, {"PAGINA_SECRETO": "s" * 40}, cargar_calendario())
    with pytest.raises(ValueError):
        crear_app(tmp_path, {"PAGINA_PASSWORD": "x"}, cargar_calendario())


def test_cookie_de_sesion_segura(ctx):
    cookie = ctx.cliente.get("/entrar").headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


# --- subir --------------------------------------------------------------------------------------

def test_subir_con_errores_no_ofrece_aprobar(adentro):
    html = texto(adentro.subir(VIAJES_MALOS))
    assert "Fila 3" in html and "ya pasó" in html
    assert 'action="/aprobar"' not in html
    assert "Aprobar" not in html.replace("aprobar", "")


def test_subir_y_aprobar(adentro):
    html = texto(adentro.subir())
    assert "Aprobar 5 llamadas" in html
    assert 'name="nombre"' in html and "required" in html
    r = adentro.aprobar("Ana Pérez")
    assert r.status_code == 302
    ap = almacen.leer_aprobacion(DOMINGO, adentro.raiz)
    assert ap["quien"] == "Ana Pérez" and len(ap["viajes"]) == 5
    assert (adentro.raiz / DOMINGO.isoformat() / "viajes.xlsx").read_bytes() == VIAJES_OK.read_bytes()
    assert len(adentro.avisos) == 1
    assert adentro.avisos[0].para == ["control@ejemplo.com"]
    assert "5 llamadas" in adentro.avisos[0].asunto
    # La página lo muestra ya aprobado
    inicio = texto(adentro.cliente.get("/"))
    assert "Ana Pérez" in inicio and "5 llamadas" in inicio


def test_advertencias_no_impiden_aprobar(adentro, tmp_path):
    ruta = excel_con(tmp_path / "v.xlsx", fecha_cita="2026-12-05")  # fuera del rango: advertencia
    html = texto(adentro.subir(ruta))
    assert "fuera de" in html
    assert "Aprobar 1 llamada" in html


def test_aprobar_sin_nombre_falla(adentro):
    adentro.subir()
    for nombre in ("", "   "):
        r = adentro.aprobar(nombre)
        assert r.status_code == 400
        assert "nombre" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert adentro.avisos == []


def test_aprobar_sin_subir_antes(adentro):
    assert adentro.aprobar().status_code == 400
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None


def test_no_aprueba_domingo_despues_de_las_12(adentro):
    adentro.subir()
    adentro.en(datetime(2026, 11, 29, 12, 30, tzinfo=ZONA_CDMX))
    r = adentro.aprobar()
    assert r.status_code == 403
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert adentro.avisos == []
    # Y subir otra lista ya no ofrece aprobar
    html = texto(adentro.subir())
    assert "Aprobar 5 llamadas" not in html
    assert "12:00" in html


def test_aprobar_revalida(adentro, tmp_path):
    ruta = excel_con(tmp_path / "sabado.xlsx", fecha_cita="2026-11-28", hora="10:00")
    assert "Aprobar 1 llamada" in texto(adentro.subir(ruta))
    adentro.en(datetime(2026, 11, 28, 11, 0, tzinfo=ZONA_CDMX))  # ya pasó la cita del sábado 10:00
    r = adentro.aprobar()
    assert r.status_code == 409
    assert "ya pasó" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert adentro.avisos == []


def test_errores_de_archivo_con_viajes_no_aprueban(tmp_path):
    # Un error de todo el archivo (falta la lista blanca en ensayo) viene junto con viajes válidos:
    # ni al subir ni al aprobar se acepta, aunque 'viajes' traiga filas.
    lista = tmp_path / "lista.txt"
    lista.write_bytes(LISTA.read_bytes())
    ctx = Contexto(tmp_path, ruta_lista=lista)
    ctx.entrar()
    assert "Aprobar 5 llamadas" in texto(ctx.subir())
    lista.unlink()  # entre subir y aprobar desaparece la lista blanca
    r = ctx.aprobar()
    assert r.status_code == 409 and 'action="/aprobar"' not in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, ctx.raiz) is None
    html = texto(ctx.subir())  # y subir con ese error tampoco ofrece aprobar
    assert 'action="/aprobar"' not in html and "lista blanca" in html.lower()


def test_aprobar_aunque_falle_el_correo(tmp_path):
    ctx = Contexto(tmp_path, enviar_ok=False)
    ctx.entrar()
    ctx.subir()
    assert ctx.aprobar().status_code == 302
    assert almacen.leer_aprobacion(DOMINGO, ctx.raiz) is not None
    assert "no se pudo enviar" in texto(ctx.cliente.get("/")).lower()


def test_reemplaza_la_aprobacion_anterior(adentro, tmp_path):
    adentro.subir()
    adentro.aprobar("Ana")
    adentro.subir(excel_con(tmp_path / "otra.xlsx", fecha_cita="2026-11-30", hora="09:00"))
    adentro.aprobar("Luis")
    ap = almacen.leer_aprobacion(DOMINGO, adentro.raiz)
    assert ap["quien"] == "Luis" and len(ap["viajes"]) == 1


def test_archivo_que_no_es_xlsx(adentro):
    for nombre, contenido in (("viajes.csv", b"viaje,linea\n1,2\n"), ("viajes.xlsx", b"esto no es un Excel"),
                              ("viajes.xls", b"PK\x03\x04")):
        html = texto(adentro.subir(nombre=nombre, contenido=contenido))
        assert 'action="/aprobar"' not in html, nombre
        assert "xlsx" in html, nombre


def test_archivo_muy_grande(adentro):
    html = texto(adentro.subir(contenido=b"PK" + b"0" * (2 * 1024 * 1024 + 10)))
    assert "2 MB" in html
    assert 'action="/aprobar"' not in html


def test_sin_archivo(adentro):
    r = adentro.cliente.post("/subir", data={"csrf": adentro.token("/")})
    assert r.status_code == 400 and "archivo" in texto(r)


def test_borra_subidas_viejas(adentro):
    carpeta = adentro.raiz / "subidas"
    carpeta.mkdir(parents=True)
    vieja, reciente = carpeta / "vieja.xlsx", carpeta / "reciente.xlsx"
    vieja.write_bytes(b"x")
    reciente.write_bytes(b"x")
    hace_dos_dias = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(vieja, (hace_dos_dias, hace_dos_dias))
    adentro.subir()
    assert not vieja.exists() and reciente.exists()


# --- detener ------------------------------------------------------------------------------------

def test_detener(adentro):
    adentro.en(datetime(2026, 11, 29, 14, 0, tzinfo=ZONA_CDMX))  # también después de las 12:00
    assert adentro.detener("Luis Gómez").status_code == 302
    assert almacen.detenido(DOMINGO, adentro.raiz)["quien"] == "Luis Gómez"
    assert len(adentro.avisos) == 1 and "detenidas" in adentro.avisos[0].asunto.lower()
    assert "Luis Gómez" in texto(adentro.cliente.get("/"))


def test_detener_sin_nombre_falla(adentro):
    adentro.en(DOMINGO_11)
    assert adentro.detener("  ").status_code == 400
    assert almacen.detenido(DOMINGO, adentro.raiz) is None


def test_detener_fuera_de_domingo(adentro):
    assert adentro.detener().status_code == 409  # viernes
    assert adentro.avisos == []


def test_no_aprueba_si_esta_detenido(adentro):
    adentro.en(DOMINGO_11)
    adentro.detener()
    adentro.subir()
    assert adentro.aprobar().status_code == 409
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None


# --- seguridad y pantalla -----------------------------------------------------------------------

def test_csrf(adentro):
    adentro.subir()
    for ruta, datos in (("/aprobar", {"nombre": "Ana"}), ("/detener", {"nombre": "Ana"}),
                        ("/subir", {}), ("/entrar", {"password": CLAVE}), ("/salir", {})):
        assert adentro.cliente.post(ruta, data=datos).status_code == 400, ruta
        assert adentro.cliente.post(ruta, data={**datos, "csrf": "falso"}).status_code == 400, ruta
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert almacen.detenido(DOMINGO, adentro.raiz) is None


def test_telefono_enmascarado(adentro):
    adentro.en(DOMINGO_11)
    revisar = texto(adentro.subir())
    adentro.aprobar()
    inicio = texto(adentro.cliente.get("/"))
    for html in (revisar, inicio):
        assert "+525500000001" not in html and "5500000001" not in html
        assert "0001" in html


def test_estado_del_domingo_en_curso(adentro):
    adentro.en(DOMINGO_11)
    adentro.subir()
    adentro.aprobar()
    viajes = almacen.leer_aprobacion(DOMINGO, adentro.raiz)["viajes"]
    estados = almacen.estados_de(DOMINGO, viajes, adentro.raiz)
    estados["104512"].update(estado="monitoreo", intentos=3, aviso_pendiente=True)
    estados["104513"].update(estado="a_tiempo", intentos=1)
    almacen.guardar_estados(DOMINGO, estados, adentro.raiz)
    almacen.anotar_falla(DOMINGO, "Twilio no contestó <script>", adentro.ahora, adentro.raiz)
    archivo = adentro.raiz / DOMINGO.isoformat() / "estados.json"
    antes = archivo.read_bytes()
    html = texto(adentro.cliente.get("/"))
    assert "Pasó a monitoreo" in html and "A tiempo" in html and "Pendiente" in html
    assert "Miguel Ángel Torres" in html
    assert "avisos pendientes" in html.lower()
    assert "Twilio no contestó &lt;script&gt;" in html and "<script>" not in html
    assert archivo.read_bytes() == antes  # la página nunca escribe estados.json


def test_pagina_sin_aprobacion_y_sin_domingo_en_curso(adentro):
    html = texto(adentro.cliente.get("/"))  # viernes
    assert "2026-11-29" in html
    assert "No hay lista aprobada" in html


def test_salir(adentro):
    assert adentro.cliente.post("/salir", data={"csrf": adentro.token("/")}).status_code == 302
    assert adentro.cliente.get("/").status_code == 302


def test_encabezados_de_seguridad(adentro):
    r = adentro.cliente.get("/")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "no-store" in r.headers["Cache-Control"]
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert "viewport" in texto(r)


# --- ronda de correcciones: aprobar exactamente lo revisado ---------------------------------------

def test_aprueba_lo_que_se_reviso_y_no_otra_subida(adentro, tmp_path):
    adentro.subir()                                    # A: 5 llamadas
    campos_a = dict(adentro.campos)
    adentro.subir(excel_con(tmp_path / "b.xlsx", fecha_cita="2026-11-30", hora="09:00"))  # B: otra pestaña
    campos_b = dict(adentro.campos)
    r = adentro.aprobar(campos=campos_a)
    assert r.status_code == 409 and "otra lista" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None and adentro.avisos == []
    assert adentro.aprobar(campos=campos_b).status_code == 302
    assert len(almacen.leer_aprobacion(DOMINGO, adentro.raiz)["viajes"]) == 1


def test_no_aprueba_si_cambia_el_total_revisado(adentro):
    adentro.subir()
    r = adentro.aprobar(campos={**adentro.campos, "n": "4"})
    assert r.status_code == 409 and "cambió" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None


def test_no_aprueba_sin_los_campos_de_la_revision(adentro):
    adentro.subir()
    assert adentro.aprobar(campos={}).status_code == 409
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None


def test_no_aprueba_para_otro_domingo(adentro, tmp_path):
    adentro.subir(excel_con(tmp_path / "v.xlsx", fecha_cita="2026-12-07", hora="09:00"))
    adentro.en(datetime(2026, 11, 30, 10, 0, tzinfo=ZONA_CDMX))  # lunes: ahora se aprueba el 6 de diciembre
    r = adentro.aprobar()
    assert r.status_code == 409 and "domingo" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert almacen.leer_aprobacion(date(2026, 12, 6), adentro.raiz) is None


def test_no_aprueba_una_subida_de_mas_de_un_dia(adentro):
    adentro.subir()
    for archivo in (adentro.raiz / "subidas").iterdir():
        viejo = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(archivo, (viejo, viejo))
    r = adentro.aprobar()
    assert r.status_code == 409 and "un día" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None


def test_advertencias_nuevas_se_muestran_antes_de_aprobar(adentro):
    adentro.subir()  # sin advertencias
    adentro.cal["rango_citas"]["hasta"] = "07:00"  # ahora la cita del lunes 08:00 queda fuera del rango
    r = adentro.aprobar()
    assert r.status_code == 409 and "fuera de" in texto(r) and "Aprobar 5 llamadas" in texto(r)
    assert almacen.leer_aprobacion(DOMINGO, adentro.raiz) is None
    assert adentro.aprobar().status_code == 302  # ya vistas, se aprueba


# --- la sesión sigue a la contraseña y vence a las 12 horas -------------------------------------

def test_cambiar_la_contrasena_cierra_las_sesiones(adentro):
    assert adentro.cliente.get("/").status_code == 200
    adentro.env["PAGINA_PASSWORD"] = "otra-clave-nueva"
    r = adentro.cliente.get("/")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_la_sesion_vence_a_las_12_horas_aunque_haya_actividad(adentro):
    assert adentro.cliente.get("/").status_code == 200
    adentro.ahora += timedelta(hours=6)
    assert adentro.cliente.get("/").status_code == 200  # la actividad no la alarga
    adentro.ahora += timedelta(hours=6, minutes=1)
    assert adentro.cliente.get("/").status_code == 302


# --- teléfonos de operador en los mensajes del validador ------------------------------------------

def test_los_mensajes_del_validador_no_muestran_telefonos_completos(adentro, tmp_path):
    libro = Workbook()
    hoja = libro.active
    hoja.append(COLUMNAS_VIAJE)
    base = {"linea": "L", "operador": "Op", "cliente": "C", "destino": "Zapopan, Jalisco",
            "fecha_cita": "2026-11-30", "tipo_cita": "Hora", "hora": "08:00",
            "correo_monitoreo": "m@ejemplo.com", "telefono_monitoreo": "55 5000 0003"}
    for viaje, tel in (("300001", "+525500000001"), ("300002", "+525500000001"), ("300003", "+525599999999")):
        hoja.append([{**base, "viaje": viaje, "telefono": tel}[c] for c in COLUMNAS_VIAJE])
    ruta = tmp_path / "tel.xlsx"
    libro.save(ruta)
    for archivo in (ruta, VIAJES_MALOS):
        html = texto(adentro.subir(archivo))
        for completo in ("5500000001", "5599999999", "5500000002", "5599999999", "5000 0003", "5500000003"):
            assert completo not in html, (archivo.name, completo)
    html = texto(adentro.subir(ruta))
    assert "lista blanca" in html and "…9999" in html and "…0001" in html


def test_ocultar_telefonos_respeta_fechas_y_viajes():
    assert ocultar_telefonos("la cita es el 2026-11-30 10:30 (viaje 104512)") == "la cita es el 2026-11-30 10:30 (viaje 104512)"
    assert ocultar_telefonos("+525500000001 y 55 5000 0003 y (55) 5000-0004") == "…0001 y …0003 y (…0004"
