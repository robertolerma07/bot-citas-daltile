r"""
Pruebas automáticas de la Fase 3 (revisión de pruebas del agente), con conversaciones inventadas.

Uso:
    .venv\Scripts\python -m pytest -q
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

from lib.formato_voz import variables_de_voz  # noqa: E402
from revisar_prueba import datos_sospechosos, evaluar, leer_csv, resumen_rondas  # noqa: E402
from validar_citas import leer_citas  # noqa: E402

_, CITAS = leer_citas(RAIZ / "datos" / "citas_prueba.csv")
CITA = CITAS[0]
VOZ = variables_de_voz(CITA)  # folio 458217, martes primero de diciembre, 08:30
ESPERADOS = {f["escenario"]: f for f in leer_csv(RAIZ / "pruebas" / "esperados.csv")}


def conversacion(turnos, datos=None, duracion=60):
    """Arma una conversación con el mismo formato que regresa ElevenLabs."""
    return {
        "transcript": [{"role": r, "message": m} for r, m in turnos],
        "analysis": {"data_collection_results": {k: {"value": v} for k, v in (datos or {}).items()}},
        "metadata": {"call_duration_secs": duracion},
    }


def nombres_ok(revisiones):
    return {n: ok for n, ok, _ in revisiones}


# ---------- Detección de datos sospechosos ----------

def test_no_marca_los_datos_correctos():
    conv = conversacion([("agent", f"La cita es {VOZ['fecha_cita_texto']}, {VOZ['hora_cita_texto']}.")])
    assert datos_sospechosos(conv, VOZ) == []


def test_no_marca_datos_correctos_sin_comas():
    """Antes, 'a la cita el martes...' se marcaba como hora inventada."""
    conv = conversacion([("agent", "Le confirmo que llega a la cita el martes primero de diciembre a las "
                                   "ocho y media de la mañana. Le llamo para la entrega de las ocho y media de la mañana.")])
    assert datos_sospechosos(conv, VOZ) == []


def test_marca_fecha_y_hora_inventadas():
    conv = conversacion([("agent", "La cita es el miércoles dos de diciembre, a las nueve de la mañana.")])
    assert len(datos_sospechosos(conv, VOZ)) == 2


def test_fecha_inventada_que_es_parte_de_otra():
    voz = dict(VOZ, fecha_cita_texto="el martes veintidós de diciembre")
    conv = conversacion([("agent", "La cita es el dos de diciembre.")])
    assert any("dos de diciembre" in s for s in datos_sospechosos(conv, voz))


def test_marca_cifras_pero_permite_marcar_1():
    assert any("número" in s for s in datos_sospechosos(conversacion([("agent", "El folio es 458217.")]), VOZ))
    assert datos_sospechosos(conversacion([("agent", "Puede decir sí o marcar 1.")]), VOZ) == []


def test_permite_repetir_la_hora_que_dijo_la_persona():
    conv = conversacion([("user", "Llegamos como a las tres de la tarde."),
                         ("agent", "Entendido, a las tres de la tarde.")])
    assert datos_sospechosos(conv, VOZ) == []


def test_frases_prohibidas_y_hablar_despues_de_despedirse():
    conv = conversacion([("agent", "¿Hay algo más en lo que le pueda ayudar?"),
                         ("agent", "Gracias. Que tenga buen día."),
                         ("user", "Bye"), ("agent", "¡Hasta luego!")])
    sospechas = datos_sospechosos(conv, VOZ)
    assert any("prohibida" in s for s in sospechas) and any("despedirse" in s for s in sospechas)


def test_no_repite_sospechas():
    conv = conversacion([("agent", "a las nueve de la mañana"), ("agent", "a las nueve de la mañana")])
    assert len(datos_sospechosos(conv, VOZ)) == 1


# ---------- Evaluación contra lo esperado ----------

def test_escenario_2_pasa_con_motivo_y_hora():
    conv = conversacion([("agent", "...")], {"estatus": "No puede", "con_quien_hablo": "Juan Pérez",
                                             "motivo": "Se descompuso la unidad",
                                             "hora_estimada": "a las tres de la tarde"}, duracion=70)
    revisiones, estatus, _ = evaluar(conv, ESPERADOS["2"], VOZ, "voz", CITA)
    assert estatus == "No puede" and all(nombres_ok(revisiones).values())


def test_escenario_3_falla_si_dio_el_folio_aunque_sea_sin_comas():
    conv = conversacion([("agent", "El folio es cuarenta y cinco ochenta y dos diecisiete.")],
                        {"estatus": "Reintentar", "con_quien_hablo": "Miguel"})
    assert not nombres_ok(evaluar(conv, ESPERADOS["3"], VOZ, "voz", CITA)[0])["No dio datos de la cita"]


def test_escenario_3_falla_si_dio_el_telefono_de_trafico():
    conv = conversacion([("agent", f"Comuníquese a tráfico al {VOZ['tel_trafico_texto']}.")],
                        {"estatus": "Reintentar", "con_quien_hablo": "Miguel"})
    assert not nombres_ok(evaluar(conv, ESPERADOS["3"], VOZ, "voz", CITA)[0])["No dio datos de la cita"]


def test_escenario_8_silencio_sin_extraccion_cuenta_como_sin_respuesta():
    conv = conversacion([("agent", "Buenas tardes, le habla Sofía... ¿Hablo con Juan Pérez?")], {"estatus": None})
    revisiones, estatus, _ = evaluar(conv, ESPERADOS["8"], VOZ, "voz", CITA)
    assert estatus == "Sin respuesta" and all(nombres_ok(revisiones).values())


def test_duracion_no_cuenta_en_modo_texto():
    conv = conversacion([("agent", "...")], {"estatus": "Confirmada", "con_quien_hablo": "Juan"}, duracion=300)
    assert all(nombres_ok(evaluar(conv, ESPERADOS["1"], VOZ, "texto", CITA)[0]).values())
    assert not all(nombres_ok(evaluar(conv, ESPERADOS["1"], VOZ, "voz", CITA)[0]).values())


def test_esperados_usan_folios_que_existen():
    folios = {c["folio"] for c in CITAS}
    assert len(ESPERADOS) == 8 and all(e["folio"] in folios for e in ESPERADOS.values())


# ---------- Resumen de rondas ----------

def filas_ronda(ronda, modo, fallas=(), reintento=None):
    filas = [{"ronda": str(ronda), "modo": modo, "escenario": str(e), "paso": "No" if e in fallas else "Sí"}
             for e in range(1, 9)]
    if reintento:
        filas.append({"ronda": str(ronda), "modo": modo, "escenario": str(reintento), "paso": "Sí"})
    return filas


def test_ronda_con_reintento_no_cuenta_como_completa():
    completas = resumen_rondas(filas_ronda(1, "texto", fallas=(3,), reintento=3))
    assert completas[1] is False


def test_dos_rondas_seguidas_completas():
    completas = resumen_rondas(filas_ronda(1, "texto") + filas_ronda(2, "voz"))
    assert completas == {1: True, 2: True}
