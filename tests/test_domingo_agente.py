r"""
Pruebas del agente "Sofía - seguimiento" (agente_seguimiento/) y de que el agente de avisos no cambió.
No usan la red: solo revisan los archivos versionados y el cuerpo que se mandaría a ElevenLabs.

Uso:
    .venv\Scripts\python -m pytest tests/test_domingo_agente.py -q
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "agente"))

from domingo.reglas import CAMPOS_EXTRAIDOS  # noqa: E402
from lib.formato_voz import fecha_texto  # noqa: E402
from lib.seguridad import ZONA_CDMX  # noqa: E402
import subir_agente  # noqa: E402

AVISO = RAIZ / "agente"
SEGUIMIENTO = RAIZ / "agente_seguimiento"

EXTRACCION_ESPERADA = {
    "hablo_con_operador": ("boolean", None),
    "llega_antes_de_la_cita": ("string", ["sí", "no", "no sabe"]),
    "entrega_realizada": ("string", ["sí", "no", "no aplica"]),
    "hora_estimada_dicha": ("string", None),
    "hora_estimada": ("string", None),
    "fecha_estimada": ("string", None),
    "motivo": ("string", None),
}


def leer_config(carpeta):
    return json.loads((carpeta / "config.json").read_text(encoding="utf-8"))


def leer_prompt(carpeta):
    return (carpeta / "prompt.md").read_text(encoding="utf-8")


def test_prompt_usa_solo_variables_conocidas():
    config = leer_config(SEGUIMIENTO)
    ejemplo = subir_agente.variables_de_ejemplo_seguimiento()
    usadas = set()
    for texto in (leer_prompt(SEGUIMIENTO), config["primer_mensaje"]):
        usadas |= set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", texto))
    assert usadas, "el prompt no usa ninguna variable"
    assert usadas <= set(ejemplo), f"variables sin valor de ejemplo: {sorted(usadas - set(ejemplo))}"
    # Las que sí se necesitan para el flujo de 5.4
    assert {"operador", "cliente", "destino", "fecha_cita_texto", "tipo_cita", "limite_texto",
            "tel_monitoreo_texto", "saludo", "cita_ya_paso", "hoy_texto"} <= usadas


def test_variables_de_ejemplo_seguimiento():
    ejemplo = subir_agente.variables_de_ejemplo_seguimiento()
    # Primer viaje de datos/viajes_prueba.xlsx
    assert ejemplo["viaje"] == "104512"
    assert ejemplo["operador"] == "Miguel Ángel Torres"
    assert ejemplo["fecha_cita_texto"] == "el lunes treinta de noviembre"
    assert ejemplo["tipo_cita"] == "Hora"
    assert ejemplo["limite_texto"] == "las ocho de la mañana"
    assert ejemplo["cita_ya_paso"] == "no"
    assert ejemplo["saludo"] in ("Buenos días", "Buenas tardes", "Buenas noches")
    assert ejemplo["hoy_texto"] == fecha_texto(datetime.now(ZONA_CDMX).date().isoformat())
    # El teléfono del operador nunca se le pasa al agente
    assert "telefono" not in ejemplo and "+525500000001" not in ejemplo.values()


def test_extraccion_exacta():
    extraccion = leer_config(SEGUIMIENTO)["extraccion_de_datos"]
    assert set(extraccion) == set(EXTRACCION_ESPERADA) == set(CAMPOS_EXTRAIDOS)
    for campo, (tipo, opciones) in EXTRACCION_ESPERADA.items():
        assert extraccion[campo]["type"] == tipo, campo
        assert extraccion[campo].get("enum") == opciones, campo
        assert extraccion[campo]["description"].strip(), campo


def test_misma_voz_y_privacidad():
    aviso, seguimiento = leer_config(AVISO), leer_config(SEGUIMIENTO)
    for clave in ("voz", "llm", "temperatura", "dtmf", "privacidad"):
        assert seguimiento[clave] == aviso[clave], clave
    assert seguimiento["duracion_maxima_seg"] == 60
    assert seguimiento["name"] != aviso["name"]


def test_cierre_whatsapp():
    prompt = leer_prompt(SEGUIMIENTO)
    assert "por WhatsApp al teléfono de Monitoreo" in prompt
    assert "Si algo cambia, por favor avise por WhatsApp al teléfono de Monitoreo, {{tel_monitoreo_texto}}" in prompt
    assert "{{tel_monitoreo_texto}}" in prompt


def test_aviso_sin_cambios():
    # tests/datos/cuerpo_aviso.json se generó con el subir_agente.py anterior a esta tarea (commit 1b16596)
    esperado = json.loads((RAIZ / "tests" / "datos" / "cuerpo_aviso.json").read_text(encoding="utf-8"))
    ejemplo = subir_agente.variables_de_ejemplo()
    ejemplo["saludo"] = "Buenas tardes"  # el saludo depende de la hora en que se corre
    cuerpo = subir_agente.armar_cuerpo(leer_config(AVISO), leer_prompt(AVISO), ejemplo)
    assert cuerpo == esperado


def test_agentes_registrados():
    assert subir_agente.AGENTES["aviso"]["carpeta"] == AVISO
    assert subir_agente.AGENTES["aviso"]["variable_env"] == "ELEVENLABS_AGENT_ID"
    assert subir_agente.AGENTES["seguimiento"]["carpeta"] == SEGUIMIENTO
    assert subir_agente.AGENTES["seguimiento"]["variable_env"] == "ELEVENLABS_AGENT_ID_SEGUIMIENTO"
