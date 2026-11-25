r"""
Crea o actualiza un agente "Sofía" en ElevenLabs a partir de los archivos versionados de su carpeta:
    prompt.md     (instrucciones del agente)
    config.json   (voz, idioma, modelo, tiempos, tecla 1, privacidad, extracción de datos)

Hay dos agentes:
    aviso         agente\              avisos de cita (Fase 2); su ID va en ELEVENLABS_AGENT_ID
    seguimiento   agente_seguimiento\  seguimiento de domingo; su ID va en ELEVENLABS_AGENT_ID_SEGUIMIENTO

- Si .env no tiene el ID del agente: crea el agente y guarda su ID en .env.
- Si ya lo tiene: actualiza ese agente.
- Al final lee el agente de vuelta y comprueba campo por campo que quedó como se pidió.

Crear o actualizar el agente NO hace llamadas ni gasta créditos de conversación.

Uso:
    .venv\Scripts\python agente\subir_agente.py                       (avisos: crear o actualizar y comprobar)
    .venv\Scripts\python agente\subir_agente.py --revisar             (solo comprobar, sin cambiar nada)
    .venv\Scripts\python agente\subir_agente.py --agente seguimiento  (agente de seguimiento de domingo)
    .venv\Scripts\python agente\subir_agente.py --agente seguimiento --revisar
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import set_key

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from domingo.calendario import cargar_calendario  # noqa: E402
from domingo.viajes import validar_viajes, variables_de_voz_viaje  # noqa: E402
from lib.formato_voz import fecha_texto, saludo, variables_de_voz  # noqa: E402
from lib.seguridad import RAIZ, RUTA_ENV, ZONA_CDMX, cargar_env, detener  # noqa: E402
from validar_citas import leer_citas  # noqa: E402

API = "https://api.elevenlabs.io"
CARPETA = RAIZ / "agente"

# Cada agente: carpeta con prompt.md y config.json, y la variable de .env donde va su ID
AGENTES = {
    "aviso": {"carpeta": CARPETA, "variable_env": "ELEVENLABS_AGENT_ID"},
    "seguimiento": {"carpeta": RAIZ / "agente_seguimiento", "variable_env": "ELEVENLABS_AGENT_ID_SEGUIMIENTO"},
}
# Variables de ejemplo que dependen del momento en que se corre el script: al solo revisar
# se comparan contra las que ya están guardadas en el agente
VARIABLES_DEL_MOMENTO = ("saludo", "hoy_texto")

# Viaje de ejemplo del agente de seguimiento: el primero de datos/viajes_prueba.xlsx, validado
# como si se aprobara el viernes antes de ese domingo (así la cita no "pasa" con el tiempo)
VIAJES_EJEMPLO = RAIZ / "datos" / "viajes_prueba.xlsx"
LISTA_EJEMPLO = RAIZ / "datos" / "numeros_demo.txt"
DOMINGO_EJEMPLO = date(2026, 11, 29)
AHORA_EJEMPLO = datetime(2026, 11, 27, 18, 0, tzinfo=ZONA_CDMX)

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


def variables_de_ejemplo_seguimiento():
    """
    Valores de ejemplo (placeholders) del agente de seguimiento: los del primer viaje de
    datos/viajes_prueba.xlsx más los que se agregan al momento de llamar (saludo según la hora
    de CDMX, cita_ya_paso y hoy_texto). El teléfono del operador NO se le pasa al agente.
    """
    errores, _, viajes = validar_viajes(VIAJES_EJEMPLO, DOMINGO_EJEMPLO, AHORA_EJEMPLO, cargar_calendario(),
                                        LISTA_EJEMPLO)
    if errores or not viajes:
        detener("datos/viajes_prueba.xlsx no tiene un viaje válido para usar como ejemplo:\n"
                + "\n".join(errores))
    viaje = viajes[0]
    ahora = datetime.now(ZONA_CDMX)
    ejemplo = variables_de_voz_viaje(viaje)
    ejemplo["saludo"] = saludo(ahora.strftime("%H:%M"))
    ejemplo["cita_ya_paso"] = "no"
    ejemplo["hoy_texto"] = fecha_texto(ahora.date().isoformat())
    ejemplo["viaje"] = viaje["viaje"]  # no lo usa el prompt; sirve para saber qué viaje está cargado
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
    parser.add_argument("--agente", choices=sorted(AGENTES), default="aviso",
                        help="agente a crear o actualizar (por defecto, aviso)")
    parser.add_argument("--revisar", action="store_true", help="solo comprobar, sin cambiar nada")
    parser.add_argument("--folio", help="solo agente aviso: cita cuyos datos se cargan como ejemplo (por defecto, "
                                        "la que ya tiene cargada el agente, o la primera de citas_prueba.csv)")
    args = parser.parse_args()
    if args.folio and args.agente != "aviso":
        detener("--folio solo sirve para el agente aviso.")

    carpeta = AGENTES[args.agente]["carpeta"]
    variable_env = AGENTES[args.agente]["variable_env"]
    valores, faltantes = cargar_env(["ELEVENLABS_API_KEY", variable_env])
    if "ELEVENLABS_API_KEY" in faltantes:
        detener("Falta ELEVENLABS_API_KEY en .env")
    api_key = valores["ELEVENLABS_API_KEY"]
    agent_id = valores.get(variable_env)

    config = json.loads((carpeta / "config.json").read_text(encoding="utf-8"))
    prompt = (carpeta / "prompt.md").read_text(encoding="utf-8")
    if args.agente == "aviso":
        folio = args.folio or (folio_cargado(agent_id, api_key) if agent_id else None)
        ejemplo = variables_de_ejemplo(folio)
    else:
        ejemplo = variables_de_ejemplo_seguimiento()
    if args.revisar and agent_id:
        # El saludo (y la fecha de hoy) dependen del momento: al solo revisar se comparan contra lo ya guardado
        guardado = llamar_api("GET", f"/v1/convai/agents/{agent_id}", api_key)
        ph = (((guardado.get("conversation_config") or {}).get("agent") or {}).get("dynamic_variables") or {}
              ).get("dynamic_variable_placeholders") or {}
        for clave in VARIABLES_DEL_MOMENTO:
            if clave in ejemplo:
                ejemplo[clave] = ph.get(clave, ejemplo[clave])
    if args.agente == "aviso":
        print(f"Cita de ejemplo cargada: folio {ejemplo['folio']} ({ejemplo['contacto']}, "
              f"{ejemplo['tipo_contacto']})")
    else:
        print(f"Viaje de ejemplo cargado: viaje {ejemplo['viaje']} ({ejemplo['operador']}, "
              f"cita de {ejemplo['tipo_cita']})")
    usadas = revisar_variables([prompt, config["primer_mensaje"]], ejemplo)
    print(f"Variables usadas por el prompt: {len(usadas)} (todas con valor de ejemplo)")
    cuerpo = armar_cuerpo(config, prompt, ejemplo)

    if args.revisar:
        if not agent_id:
            detener(f"Todavía no hay {variable_env} en .env; corre el script sin --revisar.")
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
            set_key(RUTA_ENV, variable_env, agent_id, quote_mode="never")
            print("   Su ID quedó guardado en .env")
        except OSError:
            # Si no se guarda, la siguiente corrida crearía un segundo agente
            detener(f"No se pudo escribir en .env (¿está abierto o bloqueado por OneDrive?). "
                    f"Agrega a mano la línea {variable_env}={agent_id}")

    agente = llamar_api("GET", f"/v1/convai/agents/{agent_id}", api_key)
    todo_bien = comprobar(agente, cuerpo)
    print(f"\nPara probarlo en el navegador: https://elevenlabs.io/app/agents/agents/{agent_id}")
    sys.exit(0 if todo_bien else 1)


if __name__ == "__main__":
    main()
