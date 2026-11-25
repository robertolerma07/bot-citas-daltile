r"""
El latido del domingo de seguimiento.

El programador de tareas lo corre cada 5 minutos (sin argumentos):
    .venv\Scripts\python -m domingo.latido

Cada latido mira la hora de CDMX y lo guardado, hace lo que toque y termina. Si el servidor se
reinicia a media llamada, el siguiente latido la resuelve por su conversación. Dentro del candado
(si otro latido lo tiene, no hace nada), en este orden:
  1. El domingo en curso (o el anterior, el lunes en la mañana para el resumen); si no hay, termina.
  2. Domingo después de las 12:00 sin lista aprobada: un solo aviso a control.
  3. Resuelve las llamadas que quedaron "en curso" en un latido anterior.
  4. Llama, una por una, a quien le toque (ronda de las 13:00, reintentos de las 19:00 y 19:30),
     salvo que el domingo esté detenido o se llegue al tope de llamadas.
  5. Una falla de la API (no salió la llamada) no gasta el intento del viaje. Con 3 fallas seguidas
     se suspenden las llamadas 15 minutos (también para los latidos siguientes) y se avisa a control
     una vez por caída; después se prueba con una sola llamada por latido (de preferencia a un viaje
     sin fallas) hasta que una salga. Un número que no se pudo marcar 3 veces pasa a monitoreo.
  6. Al terminar cada ronda: avisos de los casos nuevos a monitoreo y correo de control. Desde las
     21:00, lo que no se pudo llamar pasa a monitoreo para que alguien lo siga.
  7. Lunes después de las 7:00: resumen con el Excel, una sola vez.

Nunca imprime keys ni contraseñas, y la bitácora no trae teléfonos completos.
"""

import copy
import sys
import time
from datetime import date, datetime, timedelta

from domingo import almacen, avisos, telefonia
from domingo.calendario import _en_cdmx, cargar_calendario, domingo_de, hora_de
from domingo.reglas import CAMPOS_EXTRAIDOS, aplicar, cita_ya_paso, decidir, toca_llamar
from domingo.telefonia import ErrorTelefonia
from domingo.viajes import _cargar_permitidos, variables_de_voz_viaje
from lib.formato_voz import fecha_texto, saludo
from lib.seguridad import RUTA_LISTA_BLANCA, ZONA_CDMX, cargar_env

RAIZ_DATOS = almacen.RAIZ_DOMINGO
MAX_FALLAS_API_SEGUIDAS = 3
MINUTOS_SUSPENSION_API = 15  # tras 3 fallas seguidas; después, un sondeo por latido
MINUTOS_MAXIMOS_EN_CURSO = 60  # una conversación que no se puede leer en este tiempo cuenta como sin respuesta
MOTIVO_SIN_LLAMADA = "No se pudo completar la llamada"
MAX_FALLAS_API_POR_VIAJE = 3  # un número que no se puede marcar 3 veces pasa a monitoreo
MOTIVO_NO_MARCA = "No se pudo marcar a este número (falla técnica)"
VARIABLES_TELEFONIA = ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID_SEGUIMIENTO", "ELEVENLABS_PHONE_NUMBER_ID")
VARIABLES_ENV = VARIABLES_TELEFONIA + ("SMTP_HOST", "SMTP_PUERTO", "SMTP_USUARIO", "SMTP_PASSWORD", "CORREO_CONTROL")


# --------------------------------------------------------------------------- piezas puras

def normalizar_fecha_estimada(viaje, resultado):
    """
    La extracción no trae un año confiable: a la fecha estimada se le pone el año (el de la cita, el
    anterior o el siguiente) que la deja más cerca de la cita. Así "2 de enero" para una cita del 31
    de diciembre cae en el año siguiente. Regresa un resultado nuevo; el original no cambia.
    """
    try:
        fecha = date.fromisoformat(resultado.get("fecha_estimada") or "")
    except (TypeError, ValueError):
        return resultado
    cita = date.fromisoformat(viaje["fecha_cita"])
    candidatas = []
    for anio in (cita.year - 1, cita.year, cita.year + 1):
        try:
            candidatas.append(fecha.replace(year=anio))
        except ValueError:
            pass  # 29 de febrero en un año que no es bisiesto
    if not candidatas:
        return resultado
    mejor = min(candidatas, key=lambda f: (abs((f - cita).days), -f.year))
    if mejor == fecha:
        return resultado
    return {**resultado, "fecha_estimada": mejor.isoformat()}


def variables_de_llamada(viaje, momento):
    """Variables para el agente: las del viaje más las del momento de la llamada."""
    return {
        **variables_de_voz_viaje(viaje),
        "saludo": saludo(momento.strftime("%H:%M")),
        "cita_ya_paso": "sí" if cita_ya_paso(viaje, momento) else "no",
        "hoy_texto": fecha_texto(momento.date().isoformat()),
    }


def _pasar_a_monitoreo(estado, momento, motivo):
    """Pasa a monitoreo un viaje sin llamada que lo resuelva (modifica 'estado'), con una nota en el historial."""
    estado["estado"] = "monitoreo"
    estado["aviso_pendiente"] = True
    nota = {"fecha": momento.isoformat(), "decision": "monitoreo", "conversacion_id": None}
    nota.update({campo: None for campo in CAMPOS_EXTRAIDOS})
    nota["motivo"] = motivo
    estado["historial"].append(nota)


def _momento(dia, texto_hora):
    return datetime.combine(dia, hora_de(texto_hora), tzinfo=ZONA_CDMX)


def _ultimos_4(telefono):
    return f"terminado en {str(telefono)[-4:]}"


# --------------------------------------------------------------------------- el latido

def ejecutar_latido(ahora, cal, env, raiz, llamar, esperar_resultado, enviar,
                    ruta_lista=RUTA_LISTA_BLANCA, reloj=None, candado=None, dormir=time.sleep):
    """
    Hace lo que toque en este momento y regresa la bitácora (una línea por acción). 'llamar',
    'esperar_resultado' y 'enviar' son las de telefonia y avisos (o falsas en las pruebas). 'reloj'
    da la hora en cada paso, porque un latido con muchas llamadas dura minutos; sin reloj se usa
    'ahora' en todo el latido. 'candado' (por omisión almacen.candado) entrega la función que
    refresca el candado: se llama antes de cada llamada y de cada consulta del resultado, para que
    otro latido no lo crea abandonado. 'dormir' es la pausa entre consultas.
    """
    bitacora = []
    candado = candado or almacen.candado
    try:
        with candado(raiz) as refrescar:
            _Latido(ahora, cal, env, raiz, llamar, esperar_resultado, enviar, ruta_lista, reloj, bitacora,
                    refrescar, dormir).correr()
    except almacen.CandadoOcupado:
        bitacora.append("Otro latido sigue trabajando (candado ocupado); este no hace nada.")
    except almacen.CandadoPerdido:
        bitacora.append("Otro latido se quedó con el candado; este se detiene sin llamar a nadie más.")
    return bitacora


class _Latido:
    def __init__(self, ahora, cal, env, raiz, llamar, esperar_resultado, enviar, ruta_lista, reloj, bitacora,
                 refrescar, dormir):
        self.inicio = _en_cdmx(ahora)
        self.cal = cal
        self.env = env
        self.raiz = raiz
        self._llamar = llamar
        self._esperar = esperar_resultado
        self._enviar = enviar
        self.ruta_lista = ruta_lista
        self.reloj = reloj
        self.bitacora = bitacora
        self.refrescar = refrescar
        self._dormir = dormir
        self.correo_control = (env.get("CORREO_CONTROL") or "").strip()
        self.domingo = None
        self.viajes = []
        self.estados = {}
        self.bloqueados = set()  # viajes que no pasaron la lista blanca en este latido
        self.fallaron_api = set()  # viajes cuya llamada no salió en este latido: no se reintentan en él

    # ----------------------------------------------------------------- utilidades

    def ahora(self):
        return _en_cdmx(self.reloj()) if self.reloj else self.inicio

    def anota(self, texto):
        self.bitacora.append(texto)

    def falla(self, texto):
        """Anota en la bitácora y en las fallas del día (correo de control y página)."""
        self.anota(texto)
        almacen.anotar_falla(self.domingo, texto, self.ahora(), self.raiz)

    def recargar(self):
        """Vuelve a leer los estados del disco (lo guardado manda sobre lo que hay en memoria)."""
        self.estados = almacen.estados_de(self.domingo, self.viajes, self.raiz)

    def guardar_viaje(self, id_viaje, estado):
        """Guarda solo el estado de este viaje sobre lo que hay en disco, sin pisar a los demás."""
        self.recargar()
        self.estados[id_viaje] = estado
        almacen.guardar_estados(self.domingo, self.estados, self.raiz)

    def dormir_y_refrescar(self, segundos):
        """Pausa entre consultas del resultado: al despertar refresca el candado antes de consultar."""
        self._dormir(segundos)
        self.refrescar()

    def detenido(self):
        return almacen.detenido(self.domingo, self.raiz)

    def ya_hecho(self, clave):
        return almacen.ya_hecho(self.domingo, clave, self.raiz)

    def marcar_hecho(self, clave):
        almacen.marcar_hecho(self.domingo, clave, self.ahora(), self.raiz)

    def enviar(self, aviso):
        self.refrescar()
        return self._enviar(aviso, self.env)

    def llamadas_del_domingo(self):
        """Llamadas hechas hoy, incluidas las que siguen en curso (las que no salieron no cuentan)."""
        return sum(e.get("intentos", 0) + (1 if e.get("en_curso") else 0) for e in self.estados.values())

    def tope_alcanzado(self):
        return self.llamadas_del_domingo() >= self.cal["tope_llamadas_por_domingo"]

    def fin_ventana(self):
        return _momento(self.domingo, self.cal["ventana_llamadas"]["hasta"])

    # ----------------------------------------------------------------- orden del latido

    def correr(self):
        self.domingo = domingo_de(self.inicio)
        if self.domingo is None:
            return  # hoy no es domingo de seguimiento (ni lunes en la mañana): nada que hacer
        if not self.correo_control:
            self.falla("Falta CORREO_CONTROL en .env: los correos de control no le llegan a nadie")

        aprobacion = almacen.leer_aprobacion(self.domingo, self.raiz)
        if aprobacion is None:
            self.avisar_sin_lista()
            return
        self.viajes = aprobacion["viajes"]
        self.estados = almacen.estados_de(self.domingo, self.viajes, self.raiz)

        self.resolver_en_curso()
        self.llamar_a_quien_toque()
        self.cerrar_ventana()
        self.correos_de_ronda()
        self.resumen_del_lunes()

    # ----------------------------------------------------------------- 2. sin lista

    def avisar_sin_lista(self):
        if self.inicio < _momento(self.domingo, self.cal["aprobar_hasta"]) or self.ya_hecho("sin_lista"):
            return
        ok = self.enviar(avisos.aviso_sin_lista(self.domingo.isoformat(), self.correo_control))
        if ok:
            self.marcar_hecho("sin_lista")  # si no salió, se intenta otra vez en el siguiente latido
        self.anota("No hay lista aprobada: " + ("se avisó a control." if ok else
                                                "no salió el aviso a control; se reintenta en el siguiente latido."))

    # ----------------------------------------------------------------- 3. llamadas en curso

    def resolver_en_curso(self):
        for viaje in self.viajes:
            if self.estados[viaje["viaje"]].get("en_curso"):
                self.resolver(viaje)

    def resolver(self, viaje):
        """Lee el resultado de la llamada en curso del viaje, decide y guarda el estado nuevo."""
        id_viaje = viaje["viaje"]
        estado = self.estados[id_viaje]
        en_curso = estado["en_curso"]
        conversacion = en_curso.get("conversacion_id")
        inicio = en_curso.get("inicio") or self.ahora()
        try:
            if not conversacion:
                raise ErrorTelefonia("la llamada en curso no tiene conversación")
            self.refrescar()
            resultado = self._esperar(conversacion, self.env, dormir=self.dormir_y_refrescar)
        except ErrorTelefonia as e:
            if self.ahora() - inicio < timedelta(minutes=MINUTOS_MAXIMOS_EN_CURSO):
                self.anota(f"Viaje {id_viaje}: todavía no hay resultado de la llamada ({e}); "
                           "se revisa en el siguiente latido.")
                return
            self.falla(f"Viaje {id_viaje}: no se pudo leer el resultado de la llamada en "
                       f"{MINUTOS_MAXIMOS_EN_CURSO} minutos ({e}); cuenta como sin respuesta")
            resultado = {}

        resultado = normalizar_fecha_estimada(viaje, resultado)
        decision = decidir(viaje, resultado, inicio)
        nuevo = aplicar(estado, decision, resultado, inicio, self.cal, conversacion)
        self.guardar_viaje(id_viaje, nuevo)
        self.anota(f"Viaje {id_viaje}: llamada {nuevo['intentos']} -> {decision} (queda en {nuevo['estado']}).")

    # ----------------------------------------------------------------- 4 y 5. llamadas

    def llamar_a_quien_toque(self):
        faltan = [n for n in VARIABLES_TELEFONIA if not (self.env.get(n) or "").strip()]
        sondeo_hecho = False
        while True:
            self.recargar()  # otro proceso pudo haber cambiado algo durante la llamada anterior
            momento = self.ahora()
            api = almacen.leer_estado_api(self.domingo, self.raiz)
            suspendida = api["suspendida_desde"]
            viaje = self.siguiente_por_llamar(momento, preferir_sin_fallas=suspendida is not None)
            if viaje is None:
                return
            detenido = self.detenido()
            if detenido:
                self.anota(f"Las llamadas de hoy están detenidas ({detenido.get('quien')}); no se llama.")
                return
            if faltan:
                self.falla("Falta en .env: " + ", ".join(faltan) + "; no se hace ninguna llamada")
                return
            if self.tope_alcanzado():
                self.falla(f"Se llegó al tope de {self.cal['tope_llamadas_por_domingo']} llamadas del domingo; "
                           "no se hace ninguna más")
                return
            if self.cal.get("ensayo") and not self.en_lista_blanca(viaje):
                self.bloqueados.add(viaje["viaje"])
                continue

            if suspendida is not None:
                hasta = suspendida + timedelta(minutes=MINUTOS_SUSPENSION_API)
                if momento < hasta:
                    self.anota(f"Llamadas suspendidas por fallas de la API hasta las {hasta:%H:%M}.")
                    return
                if sondeo_hecho:
                    return
                sondeo_hecho = True
                self.anota("Se prueba la API con una sola llamada (sigue la suspensión por fallas).")

            self.refrescar()
            falla = self.llamar(viaje, momento)
            if falla is None:
                if api["fallas_seguidas"] or suspendida is not None:
                    self.anota("La API de llamadas responde otra vez; se reanudan las llamadas.")
                    almacen.guardar_estado_api(self.domingo, {**api, "fallas_seguidas": 0, "suspendida_desde": None,
                                                              "aviso_enviado": False, "ultimas_fallas": []},
                                               self.raiz)
                continue

            api["fallas_seguidas"] += 1
            api["ultimas_fallas"] = (api["ultimas_fallas"] + [falla])[-MAX_FALLAS_API_SEGUIDAS:]
            if suspendida is not None:
                almacen.guardar_estado_api(self.domingo, api, self.raiz)
                self.anota("La prueba de la API falló; las llamadas siguen suspendidas.")
                self.avisar_fallas_api(api)  # por si el aviso de esta caída no salió antes
                return
            if api["fallas_seguidas"] >= MAX_FALLAS_API_SEGUIDAS:
                api["suspendida_desde"] = momento
                almacen.guardar_estado_api(self.domingo, api, self.raiz)
                self.suspender_por_fallas_api(api)
                return
            almacen.guardar_estado_api(self.domingo, api, self.raiz)

    def siguiente_por_llamar(self, momento, preferir_sin_fallas=False):
        """
        El primer viaje de la lista aprobada al que le toca llamada en este momento, o None. Para
        probar la API (preferir_sin_fallas) se escoge antes uno al que no le haya fallado la API, para
        no confundir un número que no marca con una caída.
        """
        candidatos = []
        for viaje in self.viajes:
            if viaje["viaje"] in self.bloqueados or viaje["viaje"] in self.fallaron_api:
                continue
            ultima = self.ultima_llamada_al_telefono(viaje["telefono"])
            if toca_llamar(viaje, self.estados[viaje["viaje"]], momento, self.cal, ultima):
                candidatos.append(viaje)
        if preferir_sin_fallas:
            for viaje in candidatos:
                if not self.estados[viaje["viaje"]].get("fallas_api"):
                    return viaje
        return candidatos[0] if candidatos else None

    def ultima_llamada_al_telefono(self, telefono):
        """
        La llamada más reciente a ese teléfono entre todos los viajes aprobados (o None). Un intento que
        no salió por falla de la API también cuenta, para no reintentarlo antes de 10 minutos.
        """
        momentos = []
        for viaje in self.viajes:
            if viaje["telefono"] != telefono:
                continue
            estado = self.estados[viaje["viaje"]]
            if estado.get("ultimo_intento"):
                momentos.append(estado["ultimo_intento"])
            if estado.get("en_curso") and estado["en_curso"].get("inicio"):
                momentos.append(estado["en_curso"]["inicio"])
            if estado.get("ultimo_fallo_api"):
                momentos.append(estado["ultimo_fallo_api"])
        return max(momentos, default=None)

    def en_lista_blanca(self, viaje):
        """En ensayo, el teléfono se revisa otra vez contra la lista blanca justo antes de llamar."""
        permitidos, problema = _cargar_permitidos(self.ruta_lista)
        if problema:
            self.falla(f"Viaje {viaje['viaje']}: no se llamó; {problema}")
            return False
        if viaje["telefono"] not in permitidos:
            self.falla(f"Viaje {viaje['viaje']}: no se llamó; el teléfono ({_ultimos_4(viaje['telefono'])}) "
                       "ya no está en la lista blanca")
            return False
        return True

    def llamar(self, viaje, momento):
        """
        Hace una llamada y la resuelve. Regresa None si la llamada salió, o el texto de la falla. Si la
        API falla no hubo llamada: no se gasta el intento, solo se anota y se espera para reintentar.
        """
        id_viaje = viaje["viaje"]
        estado = self.estados[id_viaje]
        numero = estado.get("intentos", 0) + 1
        try:
            conversacion = self._llamar(viaje, variables_de_llamada(viaje, momento), self.env)
        except ErrorTelefonia as e:
            texto = f"Viaje {id_viaje}: no se pudo llamar ({e})"
            nuevo = copy.deepcopy(estado)
            nuevo["fallas_api"] = estado.get("fallas_api", 0) + 1
            nuevo["ultimo_fallo_api"] = momento
            self.fallaron_api.add(id_viaje)
            if nuevo["fallas_api"] >= MAX_FALLAS_API_POR_VIAJE:
                # El problema puede ser de este número (ElevenLabs lo rechaza): que monitoreo lo siga
                _pasar_a_monitoreo(nuevo, momento, MOTIVO_NO_MARCA)
                self.guardar_viaje(id_viaje, nuevo)
                self.falla(f"{texto}; pasa a monitoreo tras {MAX_FALLAS_API_POR_VIAJE} fallas al marcar "
                           f"({MOTIVO_NO_MARCA.lower()})")
                return texto
            self.guardar_viaje(id_viaje, nuevo)
            self.falla(texto + "; no cuenta como intento y se reintenta en 10 minutos o más")
            return texto

        # Se guarda la conversación ANTES de esperar: si el proceso se cae, el siguiente latido la resuelve
        self.guardar_viaje(id_viaje, {**estado, "estado": "en_curso",
                                      "en_curso": {"conversacion_id": conversacion, "inicio": momento}})
        self.anota(f"Viaje {id_viaje}: llamada {numero} iniciada (conversación {conversacion}).")
        self.resolver(viaje)
        return None

    def suspender_por_fallas_api(self, api):
        """Suspende las llamadas y avisa a control una sola vez por caída."""
        self.anota(f"{MAX_FALLAS_API_SEGUIDAS} fallas seguidas de la API de llamadas: se suspenden las llamadas "
                   f"{MINUTOS_SUSPENSION_API} minutos.")
        self.avisar_fallas_api(api)

    def avisar_fallas_api(self, api):
        """Aviso de la caída a control, si no ha salido; solo se marca enviado si de verdad salió."""
        if api["aviso_enviado"]:
            return
        ok = self.enviar(avisos.aviso_fallas_api(self.domingo.isoformat(), api["ultimas_fallas"],
                                                 self.correo_control))
        if ok:
            api["aviso_enviado"] = True
            almacen.guardar_estado_api(self.domingo, api, self.raiz)
        self.anota("Aviso de fallas de la API " + ("enviado a control." if ok else
                                                   "NO se pudo enviar; se reintenta en la siguiente prueba."))

    # ----------------------------------------------------------------- 6. fin de la ventana y rondas

    def cerrar_ventana(self):
        """Desde el fin de la ventana (21:00), lo que no se pudo llamar pasa a monitoreo con aviso."""
        if self.ahora() < self.fin_ventana() or self.detenido():
            return
        momento = self.ahora()
        for viaje in self.viajes:
            estado = self.estados[viaje["viaje"]]
            if estado.get("estado") not in ("pendiente", "sin_respuesta"):
                continue
            nuevo = copy.deepcopy(estado)
            _pasar_a_monitoreo(nuevo, momento, MOTIVO_SIN_LLAMADA)
            self.guardar_viaje(viaje["viaje"], nuevo)
            self.anota(f"Viaje {viaje['viaje']}: pasa a monitoreo ({MOTIVO_SIN_LLAMADA.lower()} "
                       f"antes de las {self.cal['ventana_llamadas']['hasta']}).")

    def correos_de_ronda(self):
        if not self.ya_hecho("correo_1300") and self.ronda_terminada(self.cal["ronda"], solo_primera=True):
            self.cerrar_ronda("correo_1300", self.cal["ronda"])
        ultima = self.cal["reintentos"][-1]
        if not self.ya_hecho("correo_1930") and self.ronda_terminada(ultima, solo_primera=False):
            self.cerrar_ronda("correo_1930", ultima)

    def ronda_terminada(self, hora, solo_primera):
        """
        La ronda de esa hora terminó si ya es la hora y no queda nadie a quien llamar en ella: nadie
        pendiente o en curso (en la de las 13:00) o, además, nadie con un reintento por hacer.
        """
        ahora = self.ahora()
        if ahora < _momento(self.domingo, hora):
            return False
        if ahora >= self.fin_ventana() or self.detenido() or self.tope_alcanzado():
            return True
        return not any(self.le_falta_llamada(v, solo_primera) for v in self.viajes)

    def le_falta_llamada(self, viaje, solo_primera):
        if viaje["viaje"] in self.bloqueados:
            return False
        estado = self.estados[viaje["viaje"]]
        if solo_primera and estado.get("estado") == "pendiente" and estado.get("fallas_api"):
            return False  # ya se intentó y la API falló: no detiene los correos de la ronda de las 13:00
        if estado.get("estado") in ("pendiente", "en_curso"):
            return True
        if solo_primera or estado.get("estado") != "sin_respuesta":
            return False
        intentos = estado.get("intentos", 0)
        return intentos < self.cal["max_llamadas_por_viaje"] and intentos <= len(self.cal["reintentos"])

    def cerrar_ronda(self, clave, hora):
        """Avisos de los casos nuevos y correo de control. Se marca hecho aunque falle el envío."""
        self.enviar_casos()
        fallas = [f["texto"] for f in almacen.fallas_del_dia(self.domingo, self.raiz)]
        detenido = self.detenido()
        if detenido:
            fallas.insert(0, f"Las llamadas de hoy se detuvieron: las detuvo {detenido.get('quien')} "
                             f"a las {self._hora_de_iso(detenido.get('cuando'))}")
        aviso = avisos.aviso_de_control(self.domingo.isoformat(), hora, self.viajes, self.estados,
                                        self.correo_control, fallas)
        ok = self.enviar(aviso)
        self.marcar_hecho(clave)
        if ok:
            self.anota(f"Correo de control de la ronda de las {hora} enviado.")
        else:
            self.falla(f"No salió el correo de control de la ronda de las {hora}")

    def enviar_casos(self):
        """Un aviso por persona de monitoreo con sus casos pendientes de aviso; el que falla queda pendiente."""
        grupos = {}
        for viaje in self.viajes:
            grupos.setdefault(viaje.get("correo_monitoreo", ""), []).append(viaje)
        for correo, suyos in grupos.items():
            casos = [v for v in suyos if self.estados[v["viaje"]].get("aviso_pendiente")]
            for aviso in avisos.avisos_de_casos(suyos, self.estados, self.correo_control,
                                                domingo=self.domingo.isoformat()):
                destino = correo or "control (viajes sin persona de monitoreo)"
                if self.enviar(aviso):
                    for v in casos:
                        self.guardar_viaje(v["viaje"], {**self.estados[v["viaje"]], "aviso_pendiente": False})
                    self.anota(f"Aviso de {len(casos)} caso(s) enviado a {destino}.")
                else:
                    self.falla(f"No salió el aviso de {len(casos)} caso(s) a {destino}; "
                               "se reintenta en el siguiente envío")

    @staticmethod
    def _hora_de_iso(texto):
        try:
            return datetime.fromisoformat(texto).astimezone(ZONA_CDMX).strftime("%H:%M")
        except (TypeError, ValueError):
            return str(texto)

    # ----------------------------------------------------------------- 7. resumen del lunes

    def resumen_del_lunes(self):
        lunes = self.domingo + timedelta(days=1)
        if self.ahora() < _momento(lunes, self.cal["resumen_lunes"]) or self.ya_hecho("resumen"):
            return
        self.enviar_casos()  # los avisos que fallaron el domingo
        ruta_excel = almacen.carpeta(self.domingo, self.raiz) / "resumen.xlsx"
        lista = avisos.avisos_de_resumen(self.domingo.isoformat(), self.viajes, self.estados,
                                         self.correo_control, ruta_excel)
        for aviso in lista:
            destino = ", ".join(aviso.para) or "(sin destinatario)"
            if self.enviar(aviso):
                self.anota(f"Resumen enviado a {destino}.")
            else:
                self.falla(f"No salió el resumen a {destino}")
        self.marcar_hecho("resumen")


# --------------------------------------------------------------------------- línea de comandos

def _escribir_bitacora(lineas):
    """Agrega las líneas a resultados/domingo/latido.log, cada una con fecha y hora de CDMX."""
    if not lineas:
        return
    sello = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")
    ruta = RAIZ_DATOS / "latido.log"
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            for linea in lineas:
                f.write(f"{sello} {linea}\n")
    except OSError as e:
        print(f"No se pudo escribir la bitácora {ruta.name} ({type(e).__name__})", file=sys.stderr)


def main():
    """Un latido con las funciones reales. Regresa 0 (también con el candado ocupado) o 1 si algo truena."""
    try:
        cal = cargar_calendario()
        env, _ = cargar_env(VARIABLES_ENV)  # lo que falte se anota en la bitácora del latido
        bitacora = ejecutar_latido(datetime.now(ZONA_CDMX), cal, env, RAIZ_DATOS, telefonia.llamar,
                                   telefonia.esperar_resultado, avisos.enviar,
                                   reloj=lambda: datetime.now(ZONA_CDMX))
    except Exception as e:  # noqa: BLE001 - el programador de tareas no debe recibir trazas en cada latido
        mensaje = str(e).replace("\n", " ")[:200]
        _escribir_bitacora([f"Error inesperado ({type(e).__name__}): {mensaje}"])
        return 1
    _escribir_bitacora(bitacora)
    return 0


if __name__ == "__main__":
    sys.exit(main())
