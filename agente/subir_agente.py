r"""
Fase 2 — Crea o actualiza el agente "Sofía" en ElevenLabs a partir de los archivos versionados:
    agente\prompt.md     (instrucciones del agente)
    agente\config.json   (voz, idioma, modelo, tiempos, tecla 1, privacidad, extracción de datos)

- Si .env no tiene ELEVENLABS_AGENT_ID: crea el agente y guarda su ID en .env.
- Si ya lo tiene: actualiza ese agente.
- Al final lee el agente de vuelta y comprueba campo por campo que quedó como se pidió.

Crear o actualizar el agente NO hace llamadas ni gasta créditos de conversación.

Uso:
    .venv\Scripts\python agente\subir_agente.py            (crear o actualizar y comprobar)
    .venv\Scripts\python agente\subir_agente.py --revisar  (solo comprobar, sin cambiar nada)
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import set_key

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.formato_voz import saludo, variables_de_voz  # noqa: E402
from lib.seguridad import RAIZ, RUTA_ENV, ZONA_CDMX, cargar_env, detener  # noqa: E402
from validar_citas import leer_citas  # noqa: E402

API = "https://api.elevenlabs.io"
CARPETA = RAIZ / "agente"
# Datos de la cita que sí se le pasan al agente tal cual (el teléfono del contacto NO se le pasa;
# la dirección se pasa ya convertida a texto hablado en direccion_texto)
CAMPOS_CITA_PARA_AGENTE = ["contacto", "tipo_contacto", "linea", "origen", "destino",
                           "contacto_destino"]

# Secciones que se reportan al comprobar el agente guardado contra lo pedido
SECCIONES = [
    ("Nombre y etiquetas", ["name", "tags"]),
    ("Idioma y primer mensaje", ["conversation_config.agent.language", "conversation_config.agent.first_message"]),
    ("Prompt igual a prompt.md", ["conversation_config.agent.prompt.prompt"]),
    ("LLM y temperatura", ["conversation_config.agent.prompt.llm", "conversation_config.agent.prompt.temperature"]),
    ("Variables de ejemplo", ["conversation_config.agent.dynamic_variables"]),
    ("Herramientas: terminar llamada y detectar buzón", ["conversation_config.agent.prompt.built_in_tools"]),
    ("Voz y ajustes de voz", ["conversation_config.tts"]),
    ("Tiempos de turno", ["conversation_config.turn"]),
    ("Duración máxima y tecla 1 (DTMF)", ["conversation_config.conversation"]),
    ("Extracción de datos", ["platform_settings.data_collection"]),
    ("Privacidad (grabación y retención 30 días)", ["platform_settings.privacy"]),
]


def variables_de_ejemplo(folio=None):
    """
    Valores de ejemplo (placeholders) de una cita, para probar en el navegador.
    Si no se indica folio, se usa la primera cita de datos/citas_prueba.csv.
    """
    _, filas = leer_citas(RAIZ / "datos" / "citas_prueba.csv")
    if not filas:
        detener("datos/citas_prueba.csv no tiene citas para usar como ejemplo.")
    if folio:
        coincidencias = [f for f in filas if f["folio"] == folio]
        if not coincidencias:
            detener(f"El folio {folio} no está en datos/citas_prueba.csv. "
                    "Indica una cita que sí exista con --folio (o usa agente\\usar_cita_en_prueba.py).")
        cita = coincidencias[0]
    else:
        cita = filas[0]
    ejemplo = {c: cita[c] for c in CAMPOS_CITA_PARA_AGENTE}
    ejemplo.update(variables_de_voz(cita))
    ejemplo["saludo"] = saludo(datetime.now(ZONA_CDMX).strftime("%H:%M"))
    ejemplo["folio"] = cita["folio"]  # no lo usa el prompt; sirve para saber qué cita está cargada
    return ejemplo


def folio_cargado(agent_id, api_key):
    """Folio de la cita que tiene cargada el agente ahora (None si no se sabe)."""
    agente = llamar_api("GET", f"/v1/convai/agents/{agent_id}", api_key)
    variables = (agente.get("conversation_config", {}).get("agent", {}).get("dynamic_variables") or {})
    return (variables.get("dynamic_variable_placeholders") or {}).get("folio")


def armar_cuerpo(config, prompt, ejemplo):
    """Traduce config.json al formato que pide la API de ElevenLabs."""
    voz = config["voz"]
    return {
        "name": config["name"],
        "tags": config["tags"],
        "conversation_config": {
            "agent": {
                "first_message": config["primer_mensaje"],
                "language": config["idioma"],
                "dynamic_variables": {"dynamic_variable_placeholders": ejemplo},
                "prompt": {
                    "prompt": prompt,
                    "llm": config["llm"],
                    "temperature": config["temperatura"],
                    "built_in_tools": {
                        "end_call": {"name": "end_call",
                                     "params": {"system_tool_type": "end_call"}},
                        "voicemail_detection": {"name": "voicemail_detection",
                                                "params": {"system_tool_type": "voicemail_detection"}},
                    },
                },
            },
            "tts": {k: voz[k] for k in ("voice_id", "model_id", "stability", "similarity_boost", "speed")},
            "turn": config["turnos"],
            "conversation": {
                "max_duration_seconds": config["duracion_maxima_seg"],
                "dtmf_input_settings": config["dtmf"],
            },
        },
        "platform_settings": {
            "data_collection": config["extraccion_de_datos"],
            "privacy": config["privacidad"],
        },
    }


def revisar_variables(textos, ejemplo):
    """Detiene el script si el prompt usa una variable {{...}} que no tiene valor de ejemplo."""
    usadas = set()
    for t in textos:
        usadas |= set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", t))
    faltan = sorted(usadas - set(ejemplo))
    if faltan:
        detener(f"El prompt usa variables sin valor de ejemplo: {', '.join(faltan)}")
    return usadas


def llamar_api(metodo, ruta, api_key, cuerpo=None):
    """Hace la petición y detiene el script con el detalle del error si falla."""
    r = requests.request(metodo, f"{API}{ruta}", headers={"xi-api-key": api_key}, json=cuerpo, timeout=60)
    if r.status_code not in (200, 201):
        detalle = r.text[:2000]
        detener(f"ElevenLabs respondió HTTP {r.status_code} en {metodo} {ruta}:\n{detalle}")
    return r.json()


def asegurar_voz(voz, api_key):
    """
    Un agente solo puede usar voces que estén en "Mis voces". Si la voz elegida de la
    biblioteca todavía no está, la agrega (POST /v1/voices/add/{public_owner_id}/{voice_id}).
    """
    r = requests.get(f"{API}/v1/voices/{voz['voice_id']}", headers={"xi-api-key": api_key}, timeout=30)
    if r.status_code == 200:
        print(f"Voz '{voz['nombre']}' ya está en Mis voces")
        return
    # Solo se agrega si ElevenLabs dice que la voz no está; cualquier otro error detiene el script
    if not (r.status_code in (400, 404) and "voice_not_found" in r.text):
        detener(f"No se pudo revisar la voz (HTTP {r.status_code}):\n{r.text[:500]}")
    print(f"Agregando la voz '{voz['nombre']}' a Mis voces…")
    nombre = voz["nombre"].split(" (")[0][:60]
    respuesta = llamar_api("POST", f"/v1/voices/add/{voz['public_owner_id']}/{voz['voice_id']}",
                           api_key, {"new_name": f"Sofia - {nombre}"})
    if respuesta.get("voice_id") != voz["voice_id"]:
        detener(f"La voz quedó con otro ID ({respuesta.get('voice_id')}); actualiza voice_id en config.json.")
    print("✅ Voz agregada")


def diferencias(pedido, guardado, ruta=""):
    """
    Regresa la lista de rutas (p. ej. 'conversation_config.tts.voice_id') donde lo guardado
    en ElevenLabs no coincide con lo pedido. Los campos extra que agrega ElevenLabs se ignoran.
    """
    if isinstance(pedido, dict):
        if not isinstance(guardado, dict):
            return [ruta]
        salida = []
        for clave, valor in pedido.items():
            salida += diferencias(valor, guardado.get(clave), f"{ruta}.{clave}" if ruta else clave)
        return salida
    return [] if pedido == guardado else [ruta]


def comprobar(agente, cuerpo):
    """Compara campo por campo lo guardado en ElevenLabs contra lo pedido. Regresa True si todo coincide."""
    malas = diferencias(cuerpo, agente)
    # Campos de extracción que sobran en ElevenLabs (p. ej. de una versión anterior de config.json)
    guardados = set((agente.get("platform_settings", {}).get("data_collection") or {}))
    sobrantes = guardados - set(cuerpo["platform_settings"]["data_collection"])
    malas += [f"platform_settings.data_collection.{s} (sobra)" for s in sorted(sobrantes)]

    print("\nComprobación del agente guardado en ElevenLabs:")
    cubiertas = set()
    for nombre, prefijos in SECCIONES:
        fallas = [m for m in malas if any(m.startswith(p) for p in prefijos)]
        cubiertas.update(fallas)
        print(f"  {'✅' if not fallas else '❌'} {nombre}")
        for f in fallas:
            print(f"       no coincide: {f}")
    for m in malas:
        if m not in cubiertas:
            print(f"  ❌ no coincide: {m}")

    eventos = agente.get("conversation_config", {}).get("conversation", {}).get("client_events") or []
    print(f"  ℹ️  Interrupciones: {'activadas' if 'interruption' in eventos else 'NO aparecen en client_events'}")
    return not malas


def main():
    parser = argparse.ArgumentParser(description="Crea o actualiza el agente en ElevenLabs.")
    parser.add_argument("--revisar", action="store_true", help="solo comprobar, sin cambiar nada")
    parser.add_argument("--folio", help="cita cuyos datos se cargan como ejemplo (por defecto, la que ya tiene "
                                        "cargada el agente, o la primera de citas_prueba.csv)")
    args = parser.parse_args()

    valores, faltantes = cargar_env(["ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID"])
    if "ELEVENLABS_API_KEY" in faltantes:
        detener("Falta ELEVENLABS_API_KEY en .env")
    api_key = valores["ELEVENLABS_API_KEY"]
    agent_id = valores.get("ELEVENLABS_AGENT_ID")

    config = json.loads((CARPETA / "config.json").read_text(encoding="utf-8"))
    prompt = (CARPETA / "prompt.md").read_text(encoding="utf-8")
    folio = args.folio or (folio_cargado(agent_id, api_key) if agent_id else None)
    ejemplo = variables_de_ejemplo(folio)
    if args.revisar and agent_id:
        # El saludo depende de la hora: al solo revisar se compara contra el que ya está guardado
        guardado = llamar_api("GET", f"/v1/convai/agents/{agent_id}", api_key)
        ph = (((guardado.get("conversation_config") or {}).get("agent") or {}).get("dynamic_variables") or {}
              ).get("dynamic_variable_placeholders") or {}
        ejemplo["saludo"] = ph.get("saludo", ejemplo["saludo"])
    print(f"Cita de ejemplo cargada: folio {ejemplo['folio']} ({ejemplo['contacto']}, {ejemplo['tipo_contacto']})")
    usadas = revisar_variables([prompt, config["primer_mensaje"]], ejemplo)
    print(f"Variables usadas por el prompt: {len(usadas)} (todas con valor de ejemplo)")
    cuerpo = armar_cuerpo(config, prompt, ejemplo)

    if args.revisar:
        if not agent_id:
            detener("Todavía no hay ELEVENLABS_AGENT_ID en .env; corre el script sin --revisar.")
    elif agent_id:
        asegurar_voz(config["voz"], api_key)
        print(f"Actualizando el agente …{agent_id[-6:]}")
        llamar_api("PATCH", f"/v1/convai/agents/{agent_id}", api_key, cuerpo)
        print("✅ Agente actualizado")
    else:
        asegurar_voz(config["voz"], api_key)
        print("Creando el agente por primera vez…")
        agent_id = llamar_api("POST", "/v1/convai/agents/create", api_key, cuerpo)["agent_id"]
        print(f"✅ Agente creado: {agent_id}")
        try:
            set_key(RUTA_ENV, "ELEVENLABS_AGENT_ID", agent_id, quote_mode="never")
            print("   Su ID quedó guardado en .env")
        except OSError:
            # Si no se guarda, la siguiente corrida crearía un segundo agente
            detener(f"No se pudo escribir en .env (¿está abierto o bloqueado por OneDrive?). "
                    f"Agrega a mano la línea ELEVENLABS_AGENT_ID={agent_id}")

    agente = llamar_api("GET", f"/v1/convai/agents/{agent_id}", api_key)
    todo_bien = comprobar(agente, cuerpo)
    print(f"\nPara probarlo en el navegador: https://elevenlabs.io/app/agents/agents/{agent_id}")
    sys.exit(0 if todo_bien else 1)


if __name__ == "__main__":
    main()
