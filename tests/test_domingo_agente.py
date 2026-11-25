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
    assert seguimiento["duracion_maxima_seg"] == 90  # 60 s cortó el cierre en la prueba del 2026-11-25
    assert seguimiento["name"] != aviso["name"]


def test_cierre_whatsapp():
    prompt = leer_prompt(SEGUIMIENTO)
    assert "por WhatsApp al teléfono de Monitoreo" in prompt
    assert "Si algo cambia, por favor avise por WhatsApp al teléfono de Monitoreo, {{tel_monitoreo_texto}}" in prompt
    assert "{{tel_monitoreo_texto}}" in prompt


RESPUESTAS_VAGAS = ["creo que sí", "a ver si llego", "temprano", "más tarde", "depende del tráfico", "no sé",
                    "ahorita", "en un rato", "no estoy seguro", "a la una o a las dos"]


def test_respuestas_vagas_iguales_en_prompt_y_extraccion():
    prompt = leer_prompt(SEGUIMIENTO)
    extraccion = leer_config(SEGUIMIENTO)["extraccion_de_datos"]
    for frase in RESPUESTAS_VAGAS:
        assert f'"{frase}"' in prompt, frase
        assert f"'{frase}'" in extraccion["llega_antes_de_la_cita"]["description"], frase
        assert f"'{frase}'" in extraccion["hora_estimada"]["description"], frase


def test_no_ofrece_el_limite_para_que_diga_que_si():
    # Sofía solo confirma la hora que dijo el operador; nunca pregunta "¿llega antes de {limite}?"
    prompt = leer_prompt(SEGUIMIENTO)
    assert "¿Entonces llega {{fecha_cita_texto}}" not in prompt
    assert "a más tardar a {{limite_texto}}" not in prompt
    assert "Nunca le ofrezcas la hora de la cita ni el límite" in prompt


def test_confirmacion_dice_la_parte_del_dia():
    prompt = leer_prompt(SEGUIMIENTO)
    assert 'no trae "de la mañana", "de la tarde" o "de la noche"' in prompt
    descripcion = leer_config(SEGUIMIENTO)["extraccion_de_datos"]["hora_estimada"]["description"]
    assert "Nunca la tomes de la hora de la cita ni del límite que dijo Sofía" in descripcion
    assert "parte del día" in descripcion


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


def test_pregunta_que_paso_antes_de_confirmar_si_va_retrasado():
    # Prueba en navegador del 2026-11-25: "a las doce" para una cita a las ocho y Sofía no preguntó el motivo
    prompt = leer_prompt(SEGUIMIENTO)
    paso_6 = prompt.index("6. Antes de confirmar")
    paso_7 = prompt.index("7. Confirma una sola vez")
    assert paso_6 < paso_7
    assert "pregunta siempre" in prompt[paso_6:paso_7]
    assert "a las doce" in prompt[paso_6:paso_7]


def test_cierre_y_end_call_van_juntos():
    # Prueba en navegador del 2026-11-25: se despidió y la llamada siguió abierta hasta los 60 s
    prompt = leer_prompt(SEGUIMIENTO)
    cierre = prompt[prompt.index("## Cierre"):prompt.index("# Respuestas vagas")]
    assert "`end_call`" in cierre
    assert "mismo turno" in cierre
    assert leer_config(SEGUIMIENTO)["turnos"]["silence_end_call_timeout"] <= 12


def test_no_confirma_rangos_ni_horas_inseguras():
    # Prueba en navegador del 2026-11-25: "a la una o a las dos, no estoy seguro" y Sofía intentó confirmar
    prompt = leer_prompt(SEGUIMIENTO)
    paso_7 = prompt[prompt.index("7. Confirma una sola vez"):prompt.index("## Cuando la cita ya pasó")]
    assert "dio un rango" in paso_7
    assert "no confirmes nada" in paso_7


def test_gracias_con_energia():
    # Roberto (2026-11-25): el "Gracias." del cierre sonaba acartonado
    prompt = leer_prompt(SEGUIMIENTO)
    cierre = prompt[prompt.index("## Cierre"):prompt.index("# Respuestas vagas")]
    assert '"¡Muchas gracias! Si algo cambia' in cierre
    assert "con energía" in cierre
    assert '"Gracias. Si algo cambia' not in prompt
