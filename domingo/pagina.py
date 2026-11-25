"""
Página web del domingo de seguimiento: subir el Excel, ver el resultado del validador, aprobar las
llamadas, ver el estado del domingo y detenerlas.

Una sola contraseña para el equipo (PAGINA_PASSWORD en .env), sesión firmada con PAGINA_SECRETO y un
token CSRF en cada POST. Se sirve con domingo/servir.py (waitress) detrás de Caddy con HTTPS.

La página solo LEE el estado de las llamadas: quien escribe estados.json es el latido. Lo único que
guarda aquí es la aprobación, la orden de detener, las fallas de envío de correo y los Excel
temporales que se suben (resultados/domingo/subidas/, se borran al día siguiente).

El bloqueo por intentos fallidos vive en memoria (un solo proceso): si se reinicia el servicio,
se borra. Es aceptable porque la contraseña es una sola y el reinicio es raro.
"""

import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, abort, flash, get_flashed_messages, redirect, render_template, request, session, url_for

from domingo import almacen, avisos
from domingo.calendario import domingo_de, domingo_para_aprobar
from domingo.viajes import validar_viajes
from lib.seguridad import RUTA_LISTA_BLANCA, ZONA_CDMX

TAMANO_MAXIMO = 2 * 1024 * 1024          # el Excel de viajes pesa unos KB; 2 MB sobra
MAX_INTENTOS_FALLIDOS = 5
MINUTOS_BLOQUEO = 15
HORAS_SESION = 12
EDAD_MAXIMA_SUBIDA = 24 * 60 * 60        # segundos: las subidas más viejas se borran
LARGO_MIN_NOMBRE, LARGO_MAX_NOMBRE = 2, 60
PATRON_SUBIDA = re.compile(r"^[0-9a-f]{32}\.xlsx\Z")
FIRMA_XLSX = b"PK\x03\x04"               # un .xlsx es un zip

ESTADOS = {
    "pendiente": "Pendiente", "en_curso": "Llamando", "sin_respuesta": "Sin respuesta",
    "a_tiempo": "A tiempo", "entregado": "Entregado", "monitoreo": "Pasó a monitoreo",
}

CABECERAS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                                "base-uri 'none'; frame-ancestors 'none'"),
}


def telefono_enmascarado(telefono):
    """Solo los últimos 4 dígitos: '+525500000001' -> '••••0001'."""
    digitos = re.sub(r"\D", "", telefono or "")
    return "••••" + digitos[-4:] if len(digitos) >= 4 else "••••"


def _cita_texto(viaje):
    if viaje.get("tipo_cita") == "Día":
        return f"{viaje.get('fecha_cita', '')}, antes de las {viaje.get('limite', '')}"
    return f"{viaje.get('fecha_cita', '')} {viaje.get('hora', '')}"


def _fecha_texto(valor):
    """Fecha ISO guardada -> 'AAAA-MM-DD HH:MM' en hora de CDMX (si no se entiende, el mismo texto)."""
    try:
        fecha = valor if isinstance(valor, datetime) else datetime.fromisoformat(valor)
        return fecha.astimezone(ZONA_CDMX).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(valor)


def _fila_de(viaje, estado):
    return {
        "viaje": viaje["viaje"], "operador": viaje.get("operador", ""),
        "telefono": telefono_enmascarado(viaje.get("telefono")), "cliente": viaje.get("cliente", ""),
        "cita": _cita_texto(viaje), "monitoreo": viaje.get("correo_monitoreo", ""),
        "estado": estado.get("estado", "pendiente"),
        "estado_texto": ESTADOS.get(estado.get("estado"), str(estado.get("estado"))),
        "intentos": estado.get("intentos", 0),
        "aviso_pendiente": bool(estado.get("aviso_pendiente")),
    }


def _nombre_valido(texto):
    """El nombre de quien aprueba o detiene, limpio; None si no sirve."""
    nombre = " ".join((texto or "").split())
    if not LARGO_MIN_NOMBRE <= len(nombre) <= LARGO_MAX_NOMBRE or not nombre.isprintable():
        return None
    return nombre


class _Bloqueos:
    """Intentos fallidos de contraseña por IP, en memoria y seguros entre hilos."""

    def __init__(self):
        self._candado = threading.Lock()
        self._datos = {}  # ip -> {"fallos": n, "hasta": datetime | None}

    def bloqueada(self, ip, ahora):
        with self._candado:
            for otra in [k for k, v in self._datos.items() if v["hasta"] and v["hasta"] <= ahora]:
                del self._datos[otra]
            dato = self._datos.get(ip)
            return bool(dato and dato["hasta"] and dato["hasta"] > ahora)

    def fallo(self, ip, ahora):
        with self._candado:
            dato = self._datos.setdefault(ip, {"fallos": 0, "hasta": None})
            dato["fallos"] += 1
            if dato["fallos"] >= MAX_INTENTOS_FALLIDOS:
                dato["hasta"] = ahora + timedelta(minutes=MINUTOS_BLOQUEO)

    def acierto(self, ip):
        with self._candado:
            self._datos.pop(ip, None)


def crear_app(raiz, env, cal, reloj=lambda: datetime.now(ZONA_CDMX), enviar=avisos.enviar,
              ruta_lista=RUTA_LISTA_BLANCA):
    """
    La app de Flask. 'raiz' es la carpeta de datos del domingo (resultados/domingo), 'env' trae
    PAGINA_PASSWORD, PAGINA_SECRETO y CORREO_CONTROL, y 'reloj' y 'enviar' se pueden cambiar en las
    pruebas. Lanza ValueError si falta la contraseña o el secreto de la sesión.
    """
    clave = env.get("PAGINA_PASSWORD") or ""
    secreto = env.get("PAGINA_SECRETO") or ""
    if not clave:
        raise ValueError("Falta PAGINA_PASSWORD en .env (la contraseña del equipo para la página)")
    if len(secreto) < 16:
        raise ValueError("Falta PAGINA_SECRETO en .env (al menos 16 caracteres al azar para firmar la sesión)")
    raiz = Path(raiz)
    carpeta_subidas = raiz / "subidas"
    correo_control = env.get("CORREO_CONTROL") or ""
    bloqueos = _Bloqueos()

    app = Flask(__name__, template_folder=str(Path(__file__).parent / "plantillas_html"), static_folder=None)
    app.config.update(
        SECRET_KEY=secreto,
        SESSION_COOKIE_NAME="sofia_sesion",
        SESSION_COOKIE_SECURE=True,      # la página se sirve por HTTPS (Caddy)
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=HORAS_SESION),
        MAX_CONTENT_LENGTH=TAMANO_MAXIMO + 512 * 1024,  # el archivo, más lo que ocupa el resto del formulario
    )

    # --- piezas comunes ---------------------------------------------------------------------------

    def token_csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    app.jinja_env.globals["csrf_token"] = token_csrf

    def contexto_base():
        """Lo que casi todas las páginas necesitan: a qué domingo se aprueba y hasta qué hora."""
        return {"para_aprobar": domingo_para_aprobar(reloj(), cal), "aprobar_hasta": cal["aprobar_hasta"]}

    def pagina(plantilla, codigo=200, **datos):
        return render_template(plantilla, **contexto_base(), **datos), codigo

    def error(mensaje, codigo):
        return pagina("error.html", codigo, mensaje=mensaje)

    def aprobacion_resumida(domingo):
        ap = almacen.leer_aprobacion(domingo, raiz)
        if not ap:
            return None
        return {"quien": ap["quien"], "cuando": _fecha_texto(ap["cuando"]), "total": len(ap["viajes"])}

    def validar(ruta, domingo, ahora):
        try:
            return validar_viajes(ruta, domingo, ahora, cal, ruta_lista)
        except Exception as e:  # nunca una traza en pantalla
            return [f"No se pudo revisar el archivo ({type(e).__name__}). Avisa a Roberto."], [], []

    def borrar_subida(nombre):
        if nombre and PATRON_SUBIDA.match(nombre):
            (carpeta_subidas / nombre).unlink(missing_ok=True)

    def limpiar_subidas_viejas():
        if not carpeta_subidas.is_dir():
            return
        limite = time.time() - EDAD_MAXIMA_SUBIDA
        for archivo in carpeta_subidas.iterdir():
            try:
                if archivo.is_file() and archivo.stat().st_mtime < limite:
                    archivo.unlink()
            except OSError:
                pass  # otro proceso lo borró o lo tiene abierto: se intenta en la siguiente subida

    def avisar(aviso):
        try:
            return bool(enviar(aviso, env))
        except Exception:  # el correo nunca debe tumbar una aprobación ya guardada
            return False

    # --- candados de toda petición ----------------------------------------------------------------

    @app.before_request
    def exigir_sesion_y_token():
        if request.endpoint != "entrar" and not session.get("entro"):
            return redirect(url_for("entrar"))
        if request.method == "POST":
            esperado, enviado = session.get("csrf") or "", request.form.get("csrf") or ""
            if not esperado or not hmac.compare_digest(esperado.encode(), enviado.encode()):
                abort(400, "Falta el token de seguridad")
        return None

    @app.after_request
    def poner_cabeceras(respuesta):
        for nombre, valor in CABECERAS.items():
            respuesta.headers[nombre] = valor
        return respuesta

    @app.errorhandler(400)
    def mal_pedido(e):
        return error("La solicitud no es válida (recarga la página e inténtalo de nuevo).", 400)

    @app.errorhandler(413)
    def muy_grande(e):
        return error("El archivo pesa más de 2 MB. Sube solo el Excel de viajes.", 413)

    @app.errorhandler(405)
    def metodo_no_permitido(e):
        return redirect(url_for("inicio"))

    # --- entrar y salir ---------------------------------------------------------------------------

    @app.route("/entrar", methods=["GET", "POST"])
    def entrar():
        if request.method == "GET":
            return pagina("entrar.html")
        ahora, ip = reloj(), request.remote_addr or "?"
        if bloqueos.bloqueada(ip, ahora):
            return pagina("entrar.html", 429, mensaje=f"Demasiados intentos. Espera {MINUTOS_BLOQUEO} minutos.")
        escrita = (request.form.get("password") or "").encode()
        if not hmac.compare_digest(escrita, clave.encode()):
            bloqueos.fallo(ip, ahora)
            return pagina("entrar.html", 401, mensaje="Contraseña incorrecta.")
        bloqueos.acierto(ip)
        session.clear()
        session["entro"] = True
        session.permanent = True
        return redirect(url_for("inicio"))

    @app.post("/salir")
    def salir():
        borrar_subida(session.get("subida"))
        session.clear()
        return redirect(url_for("entrar"))

    # --- inicio: aprobación vigente y estado del domingo ------------------------------------------

    @app.get("/")
    def inicio():
        ahora = reloj()
        en_curso = domingo_de(ahora)
        datos = {"mensajes": get_flashed_messages(with_categories=True), "en_curso": en_curso,
                 "vigente": None, "filas": [], "detenido": None, "fallas": [], "pendientes": []}
        para_aprobar = domingo_para_aprobar(ahora, cal)
        if para_aprobar:
            datos["vigente"] = aprobacion_resumida(para_aprobar)
        if en_curso:
            datos["aprobacion_en_curso"] = aprobacion_resumida(en_curso)
            ap = almacen.leer_aprobacion(en_curso, raiz)
            if ap:
                estados = almacen.estados_de(en_curso, ap["viajes"], raiz)  # solo lectura
                datos["filas"] = [_fila_de(v, estados[v["viaje"]]) for v in ap["viajes"]]
                datos["pendientes"] = [f for f in datos["filas"] if f["aviso_pendiente"]]
            detenido = almacen.detenido(en_curso, raiz)
            if detenido:
                datos["detenido"] = {"quien": detenido["quien"], "cuando": _fecha_texto(detenido["cuando"])}
            datos["fallas"] = [{"cuando": _fecha_texto(f.get("cuando")), "texto": f.get("texto", "")}
                               for f in almacen.fallas_del_dia(en_curso, raiz)]
        return pagina("estado.html", **datos)

    # --- subir y aprobar --------------------------------------------------------------------------

    def revisar(codigo=200, errores=(), advertencias=(), viajes=(), domingo=None, puede_aprobar=False):
        vigente = aprobacion_resumida(domingo) if domingo else None
        filas = [_fila_de(v, {}) for v in viajes]
        return pagina("revisar.html", codigo, errores=list(errores), advertencias=list(advertencias),
                      filas=filas, domingo=domingo, puede_aprobar=puede_aprobar, vigente=vigente)

    @app.post("/subir")
    def subir():
        archivo = request.files.get("archivo")
        if archivo is None or not archivo.filename:
            return revisar(400, ["Falta el archivo: elige el Excel de viajes (.xlsx)."])
        if not archivo.filename.lower().endswith(".xlsx"):
            return revisar(400, ["El archivo debe ser un Excel .xlsx (no .xls, .csv ni otro formato)."])
        contenido = archivo.stream.read(TAMANO_MAXIMO + 1)
        if len(contenido) > TAMANO_MAXIMO:
            return revisar(400, ["El archivo pesa más de 2 MB. Sube solo el Excel de viajes."])
        if not contenido.startswith(FIRMA_XLSX):
            return revisar(400, ["El archivo no es un Excel .xlsx válido. Guárdalo desde Excel como .xlsx."])
        ahora = reloj()
        domingo = domingo_para_aprobar(ahora, cal)
        if domingo is None:
            return revisar(403, [f"Ya no se pueden aprobar listas para hoy: las aprobaciones cierran a las "
                                 f"{cal['aprobar_hasta']} del domingo."])

        limpiar_subidas_viejas()
        borrar_subida(session.get("subida"))
        nombre = secrets.token_hex(16) + ".xlsx"
        carpeta_subidas.mkdir(parents=True, exist_ok=True)
        ruta = carpeta_subidas / nombre
        ruta.write_bytes(contenido)

        errores, advertencias, viajes = validar(ruta, domingo, ahora)
        puede = not errores and bool(viajes)  # cualquier error, aunque haya viajes, impide aprobar
        if puede:
            session["subida"] = nombre
        else:
            session.pop("subida", None)
            ruta.unlink(missing_ok=True)
        return revisar(200, errores, advertencias, viajes, domingo, puede)

    @app.post("/aprobar")
    def aprobar():
        quien = _nombre_valido(request.form.get("nombre"))
        if quien is None:
            return error(f"Escribe tu nombre ({LARGO_MIN_NOMBRE} a {LARGO_MAX_NOMBRE} letras) para aprobar.", 400)
        ahora = reloj()
        domingo = domingo_para_aprobar(ahora, cal)
        if domingo is None:
            return error(f"Ya no se puede aprobar: las aprobaciones cierran a las {cal['aprobar_hasta']} "
                         "del domingo.", 403)
        if almacen.detenido(domingo, raiz):
            return error("Las llamadas de ese domingo están detenidas; ya no se puede aprobar otra lista.", 409)
        subida = session.get("subida")
        if not subida or not PATRON_SUBIDA.match(subida) or not (carpeta_subidas / subida).is_file():
            return error("No hay un Excel por aprobar. Sube la lista de nuevo.", 400)

        ruta = carpeta_subidas / subida
        errores, advertencias, viajes = validar(ruta, domingo, ahora)  # con la hora de ahora, no la de la subida
        if errores or not viajes:
            session.pop("subida", None)
            ruta.unlink(missing_ok=True)
            return revisar(409, errores or ["El archivo no tiene viajes."], advertencias, viajes, domingo, False)

        almacen.guardar_aprobacion(domingo, viajes, ruta.read_bytes(), quien, ahora, raiz)
        ruta.unlink(missing_ok=True)
        session.pop("subida", None)
        total = len(viajes)
        flash(f"Aprobadas {total} llamadas para el domingo {domingo}.", "bien")
        aprobacion = {"quien": quien, "cuando": ahora, "viajes": viajes}
        if not avisar(avisos.aviso_de_aprobacion(domingo, aprobacion, correo_control)):
            almacen.anotar_falla(domingo, f"No se pudo enviar el correo de la aprobación de {quien}", ahora, raiz)
            flash("La aprobación quedó guardada, pero no se pudo enviar el aviso por correo a control. "
                  "Avísale a Roberto.", "mal")
        return redirect(url_for("inicio"))

    @app.post("/detener")
    def detener():
        quien = _nombre_valido(request.form.get("nombre"))
        if quien is None:
            return error(f"Escribe tu nombre ({LARGO_MIN_NOMBRE} a {LARGO_MAX_NOMBRE} letras) para detener.", 400)
        ahora = reloj()
        domingo = domingo_de(ahora)
        if domingo is None:
            return error("Solo se pueden detener las llamadas el domingo.", 409)
        almacen.detener(domingo, quien, ahora, raiz)
        flash(f"Llamadas detenidas por {quien}. No se hará ninguna llamada más hoy.", "bien")
        if not avisar(avisos.aviso_detenido(domingo, quien, ahora, correo_control)):
            almacen.anotar_falla(domingo, f"No se pudo enviar el correo de que {quien} detuvo las llamadas",
                                 ahora, raiz)
            flash("Las llamadas quedaron detenidas, pero no se pudo enviar el aviso por correo. "
                  "Avísale a Roberto.", "mal")
        return redirect(url_for("inicio"))

    return app
