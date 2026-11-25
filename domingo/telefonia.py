"""
Seguimiento de domingo: llamada de salida por la integración nativa de ElevenLabs con Twilio y lectura
del resultado que ElevenLabs extrae de la conversación.

- llamar(): pide a ElevenLabs que llame al operador y regresa el conversation_id.
- esperar_resultado(): consulta la conversación hasta que termine y regresa los 7 campos de extracción.

Documentación consultada (2026-11-25):
  https://elevenlabs.io/docs/api-reference/twilio/outbound-call   (POST /v1/convai/twilio/outbound-call)
  Cuerpo: agent_id, agent_phone_number_id, to_number y conversation_initiation_client_data.dynamic_variables.
  Respuesta: success, message, conversation_id y callSid.

Este módulo no termina el proceso: si algo falla lanza ErrorTelefonia, con un mensaje que nunca trae la key,
el Account SID, el token ni un teléfono completo (los errores de red y el cuerpo de las respuestas se descartan).
"""

import time

import requests

from domingo.reglas import CAMPOS_EXTRAIDOS

API = "https://api.elevenlabs.io"
TIMEOUT_SEG = 30
PAUSA_SEG = 10  # entre consultas de la conversación

# Valores seguros cuando ElevenLabs no regresa un campo o regresa algo fuera de lo esperado
VALORES_ENUM = {
    "llega_antes_de_la_cita": ("sí", "no", "no sabe"),
    "entrega_realizada": ("sí", "no", "no aplica"),
}
POR_OMISION = {
    "hablo_con_operador": False,
    "llega_antes_de_la_cita": "no sabe",
    "entrega_realizada": "no aplica",
    "hora_estimada_dicha": "",
    "hora_estimada": "",
    "fecha_estimada": "",
    "motivo": "",
}


class ErrorTelefonia(Exception):
    """Falló la llamada o la lectura del resultado. El mensaje no trae keys, SIDs ni teléfonos."""


def _encabezados(env):
    api_key = (env.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        raise ErrorTelefonia("Falta ELEVENLABS_API_KEY en .env")
    return {"xi-api-key": api_key}


def llamar(viaje, variables, env, http=requests):
    """
    Llama al teléfono del viaje con el agente de seguimiento y regresa el conversation_id.
    'variables' son las dynamic_variables que se le pasan al agente (no incluyen el teléfono del operador).
    """
    faltan = [n for n in ("ELEVENLABS_AGENT_ID_SEGUIMIENTO", "ELEVENLABS_PHONE_NUMBER_ID")
              if not (env.get(n) or "").strip()]
    if faltan:
        raise ErrorTelefonia("Falta en .env: " + ", ".join(faltan))
    cuerpo = {
        "agent_id": env["ELEVENLABS_AGENT_ID_SEGUIMIENTO"].strip(),
        "agent_phone_number_id": env["ELEVENLABS_PHONE_NUMBER_ID"].strip(),
        "to_number": viaje["telefono"],
        "conversation_initiation_client_data": {"dynamic_variables": variables},
    }
    try:
        r = http.post(f"{API}/v1/convai/twilio/outbound-call", headers=_encabezados(env), json=cuerpo,
                      timeout=TIMEOUT_SEG)
    except requests.RequestException as e:
        # El texto de la excepción puede traer la URL o el número: solo se dice el tipo de error
        raise ErrorTelefonia(f"No se pudo conectar con ElevenLabs para llamar ({type(e).__name__})") from None
    if r.status_code != 200:
        raise ErrorTelefonia(f"ElevenLabs rechazó la llamada (HTTP {r.status_code})")
    try:
        conversation_id = r.json().get("conversation_id")
    except ValueError:
        conversation_id = None
    if not conversation_id:
        raise ErrorTelefonia("ElevenLabs no regresó el conversation_id de la llamada")
    return conversation_id


def _valor(analisis, campo):
    """Valor extraído de un campo, o el de por omisión si falta o no es válido."""
    entrada = ((analisis or {}).get("data_collection_results") or {}).get(campo)
    valor = entrada.get("value") if isinstance(entrada, dict) else None
    if campo == "hablo_con_operador":
        if isinstance(valor, bool):
            return valor
        return isinstance(valor, str) and valor.strip().lower() == "true"
    if campo in VALORES_ENUM:
        return valor if valor in VALORES_ENUM[campo] else POR_OMISION[campo]
    return valor.strip() if isinstance(valor, str) else POR_OMISION[campo]


def _resultado(conv):
    """Los 7 campos de extracción más duracion_seg y estado_conversacion."""
    analisis = conv.get("analysis")
    resultado = {campo: _valor(analisis, campo) for campo in CAMPOS_EXTRAIDOS}
    duracion = (conv.get("metadata") or {}).get("call_duration_secs")
    es_numero = isinstance(duracion, (int, float)) and not isinstance(duracion, bool)
    resultado["duracion_seg"] = duracion if es_numero else 0
    resultado["estado_conversacion"] = conv.get("status")
    return resultado


def esperar_resultado(conversation_id, env, http=requests, dormir=time.sleep, max_seg=600):
    """
    Consulta la conversación cada 10 segundos hasta que ElevenLabs la marque 'done' o 'failed' (cualquier otro
    estado: initiated, in-progress, processing... no ha terminado). Si falló o no hubo análisis, los campos
    quedan en sus valores seguros. Si se agota el tiempo, lanza ErrorTelefonia.
    """
    encabezados = _encabezados(env)
    transcurrido = 0
    while True:
        try:
            r = http.get(f"{API}/v1/convai/conversations/{conversation_id}", headers=encabezados,
                         timeout=TIMEOUT_SEG)
        except requests.RequestException as e:
            raise ErrorTelefonia(f"No se pudo consultar la conversación ({type(e).__name__})") from None
        if r.status_code != 200:
            raise ErrorTelefonia(f"No se pudo consultar la conversación (HTTP {r.status_code})")
        try:
            conv = r.json()
        except ValueError:
            raise ErrorTelefonia("ElevenLabs regresó una respuesta ilegible al consultar la conversación") from None
        if conv.get("status") in ("done", "failed"):
            return _resultado(conv)
        if transcurrido >= max_seg:
            raise ErrorTelefonia(f"La conversación no terminó en {max_seg} segundos "
                                 f"(último estado: {conv.get('status')})")
        dormir(PAUSA_SEG)
        transcurrido += PAUSA_SEG
