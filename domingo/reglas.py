"""
Reglas del domingo de seguimiento: a quién se llama y qué significa cada resultado.

Todo aquí es lógica pura (sin archivos, sin red). Las horas se comparan siempre con fecha y hora
con zona (Ciudad de México); una hora sin zona lanza ValueError. La decisión la toma este código
con los datos extraídos de la llamada, nunca el agente.
"""

import copy
from datetime import date, datetime, timedelta

from domingo.calendario import DOMINGO, _en_cdmx, hora_de
from lib.seguridad import ZONA_CDMX

ESTADOS = ("pendiente", "en_curso", "sin_respuesta", "a_tiempo", "entregado", "monitoreo")

CAMPOS_EXTRAIDOS = (
    "hablo_con_operador", "llega_antes_de_la_cita", "entrega_realizada",
    "hora_estimada_dicha", "hora_estimada", "fecha_estimada", "motivo",
)


def estado_inicial():
    """Estado de un viaje recién aprobado."""
    return {
        "estado": "pendiente",
        "intentos": 0,
        "ultimo_intento": None,
        "en_curso": None,
        "historial": [],
        "aviso_pendiente": False,
        "fallas_api": 0,
    }


def _limite_de_la_cita(viaje):
    """Momento (con zona) en que vence la cita: fecha_cita + limite."""
    dia = date.fromisoformat(viaje["fecha_cita"])
    return datetime.combine(dia, hora_de(viaje["limite"]), tzinfo=ZONA_CDMX)


def cita_ya_paso(viaje, ahora):
    """True si 'ahora' es posterior a la fecha de la cita + su límite (hora de CDMX)."""
    return _en_cdmx(ahora) > _limite_de_la_cita(viaje)


def toca_llamar(viaje, estado, ahora, cal, ultima_llamada_al_telefono):
    """
    True si en este momento hay que llamar a este viaje: solo en domingo, dentro de la ventana de
    llamadas, en la ronda o el reintento que le corresponde, sin pasar de las llamadas máximas y
    respetando los minutos mínimos entre llamadas al mismo teléfono.
    """
    ahora = _en_cdmx(ahora)
    if ahora.weekday() != DOMINGO:
        return False
    if not hora_de(cal["ventana_llamadas"]["desde"]) <= ahora.time() < hora_de(cal["ventana_llamadas"]["hasta"]):
        return False

    intentos = estado.get("intentos", 0)
    if estado.get("estado") == "pendiente":
        if ahora.time() < hora_de(cal["ronda"]):
            return False
    elif estado.get("estado") == "sin_respuesta":
        reintentos = cal["reintentos"]
        if intentos >= cal["max_llamadas_por_viaje"] or not 1 <= intentos <= len(reintentos):
            return False
        if ahora.time() < hora_de(reintentos[intentos - 1]):
            return False
    else:
        return False  # en_curso y los estados finales no se llaman

    if ultima_llamada_al_telefono is not None:
        espera = timedelta(minutes=cal["minutos_entre_llamadas_mismo_telefono"])
        if _en_cdmx(ultima_llamada_al_telefono) + espera > ahora:
            return False
    return True


def _cifra_contradice(viaje, resultado):
    """
    True si lo que dijo el operador (fecha u hora) cae después del límite de la cita. Una cifra mal
    formada o vacía cuenta como "sin cifra": no contradice.
    """
    try:
        fecha = date.fromisoformat(resultado.get("fecha_estimada") or "")
    except (TypeError, ValueError):
        fecha = None
    try:
        hora = hora_de(resultado.get("hora_estimada") or "")
    except (TypeError, ValueError):
        hora = None

    dia_cita = date.fromisoformat(viaje["fecha_cita"])
    if fecha is not None and fecha > dia_cita:
        return True
    if fecha is not None and fecha < dia_cita:
        return False  # llega antes del día de la cita (la víspera), sin importar la hora
    # Misma fecha, o hora sin fecha (se toma como la del día de la cita, lo más prudente)
    return hora is not None and hora > hora_de(viaje["limite"])


def decidir(viaje, resultado, momento_llamada):
    """
    Qué significa el resultado de una llamada: "sin_respuesta", "a_tiempo", "entregado" o "monitoreo".
    Nunca regresa "a_tiempo" salvo que el operador haya dicho "sí" llega antes de la cita y ninguna
    cifra extraída lo contradiga.
    """
    if resultado.get("hablo_con_operador") is not True:
        return "sin_respuesta"

    if cita_ya_paso(viaje, momento_llamada):
        return "entregado" if _texto(resultado.get("entrega_realizada")) == "sí" else "monitoreo"

    if _texto(resultado.get("llega_antes_de_la_cita")) != "sí":
        return "monitoreo"
    if _cifra_contradice(viaje, resultado):
        return "monitoreo"
    return "a_tiempo"


def _texto(valor):
    """Normaliza una respuesta de texto ('Sí ', 'si' -> 'sí'); cualquier otra cosa no es texto válido."""
    if not isinstance(valor, str):
        return ""
    valor = valor.strip().casefold()
    return "sí" if valor == "si" else valor


def aplicar(estado, decision, resultado, ahora, cal, conversacion_id):
    """
    Estado nuevo del viaje después de una llamada (el anterior no se modifica). Un tercer "sin
    respuesta" (o el máximo de llamadas del calendario) pasa a monitoreo y deja el aviso pendiente.
    """
    ahora = _en_cdmx(ahora)
    nuevo = copy.deepcopy(estado)
    nuevo["intentos"] = estado.get("intentos", 0) + 1
    nuevo["ultimo_intento"] = ahora
    nuevo["en_curso"] = None

    if decision == "sin_respuesta":
        if nuevo["intentos"] >= cal["max_llamadas_por_viaje"]:
            nuevo["estado"] = "monitoreo"
            nuevo["aviso_pendiente"] = True
        else:
            nuevo["estado"] = "sin_respuesta"
    elif decision == "monitoreo":
        nuevo["estado"] = "monitoreo"
        nuevo["aviso_pendiente"] = True
    elif decision in ("a_tiempo", "entregado"):
        nuevo["estado"] = decision
    else:
        raise ValueError(f"Decisión desconocida: {decision!r}")

    entrada = {"fecha": ahora.isoformat(), "decision": decision, "conversacion_id": conversacion_id}
    for campo in CAMPOS_EXTRAIDOS:
        entrada[campo] = resultado.get(campo)
    nuevo["historial"].append(entrada)
    return nuevo
