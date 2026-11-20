r"""
Fase 3 — Revisa una prueba del agente y la anota en pruebas\bitacora.csv.

1. Trae de ElevenLabs la conversación (por defecto, la más reciente del agente) y confirma
   que sea del escenario indicado (misma cita) y si fue por voz o por texto.
2. Compara lo extraído (estatus, con quién habló, motivo, hora estimada) contra pruebas\esperados.csv.
3. Busca en lo que dijo Sofía fechas, horas o cifras que no estén en la cita, frases prohibidas
   y si siguió hablando después de despedirse.
4. Pregunta quién probó, si dijo algún dato incorrecto, si cumplió lo específico del escenario,
   la naturalidad (1 a 5) y comentarios.
5. Agrega un renglón a la bitácora y muestra cómo van las rondas.

Solo consulta ElevenLabs (no gasta créditos).

Uso:
    .venv\Scripts\python pruebas\revisar_prueba.py --escenario 1 --ronda 1
    .venv\Scripts\python pruebas\revisar_prueba.py --escenario 1 --ronda 1 --conversacion conv_xxx --sin-anotar
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from lib.formato_voz import variables_de_voz  # noqa: E402
from lib.seguridad import ZONA_CDMX, cargar_env, detener  # noqa: E402
from validar_citas import leer_citas  # noqa: E402

API = "https://api.elevenlabs.io"
BITACORA = RAIZ / "pruebas" / "bitacora.csv"
COLUMNAS_BITACORA = ["fecha", "ronda", "modo", "escenario", "quien_probo", "folio", "id_conversacion",
                     "estatus_obtenido", "estatus_esperado", "dijo_dato_incorrecto", "datos_a_revisar",
                     "naturalidad_1a5", "duracion_seg", "paso", "comentarios"]

# Todo se busca sobre texto normalizado: minúsculas, sin acentos ni signos de puntuación
DIAS = r"lunes|martes|miercoles|jueves|viernes|sabado|domingo"
MESES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
HORAS = r"una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce"
PATRON_HORA = re.compile(rf"\ba las? (?:{HORAS})\b(?: [a-z]+){{0,4}}? "
                         r"(?:de la manana|de la tarde|de la noche|de la madrugada|del dia)\b")
PATRON_FECHA = re.compile(rf"\b(?:(?:{DIAS}) )?(?:primero|[a-z]+(?: y [a-z]+)?) de (?:{MESES})\b")
# Frases que el prompt prohíbe
FRASES_PROHIBIDAS = ["algo mas en lo que", "reprogram", "le van a llamar", "alguien le llama",
                     "alguien le va a llamar", "le llamaran"]
CIERRE = "que tenga buen dia"


def normalizar(texto):
    """Minúsculas, sin acentos y sin signos de puntuación (solo letras, números y un espacio entre palabras)."""
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9ñ]+", " ", texto).split())


def contiene(texto, frase):
    """True si la frase aparece completa (por palabras) dentro del texto, ambos ya normalizados."""
    return bool(frase) and re.search(rf"(?:^| ){re.escape(frase)}(?: |$)", texto) is not None


def leer_csv(ruta):
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def traer_conversacion(api_key, agent_id, conv_id):
    """Trae la conversación indicada o la más reciente; espera a que ElevenLabs termine de analizarla."""
    h = {"xi-api-key": api_key}
    if not conv_id:
        r = requests.get(f"{API}/v1/convai/conversations", headers=h,
                         params={"agent_id": agent_id, "page_size": 1}, timeout=30)
        if r.status_code != 200:
            detener(f"No se pudo listar las conversaciones (HTTP {r.status_code}).")
        lista = r.json().get("conversations", [])
        if not lista:
            detener("El agente todavía no tiene conversaciones.")
        conv_id = lista[0]["conversation_id"]
    for _ in range(12):  # hasta ~1 minuto
        r = requests.get(f"{API}/v1/convai/conversations/{conv_id}", headers=h, timeout=30)
        if r.status_code != 200:
            detener(f"No se pudo leer la conversación {conv_id} (HTTP {r.status_code}).")
        conv = r.json()
        if conv.get("status") in ("done", "failed"):
            return conv
        print("  …ElevenLabs sigue analizando la conversación, espero 5 segundos")
        time.sleep(5)
    detener("La conversación no terminó de analizarse; intenta de nuevo en un minuto.")


def variables_de_la_conversacion(conv):
    """Variables con las que se hizo la conversación (para saber qué cita y si fue por texto)."""
    datos = conv.get("conversation_initiation_client_data") or {}
    return datos.get("dynamic_variables") or {}


def datos_sospechosos(conv, voz):
    """
    Revisa lo que dijo Sofía y regresa una lista (sin repetidos) de cosas a revisar:
    fechas u horas que no son las de la cita ni las que dijo antes la persona, cifras escritas
    con número, frases prohibidas y turnos después de la despedida.
    """
    permitidos = [normalizar(v) for v in voz.values()]
    dicho_por_usuario = ""
    sospechas = []
    ya_cerro = False

    def agregar(texto):
        if texto not in sospechas:
            sospechas.append(texto)

    for turno in conv.get("transcript", []):
        original = turno.get("message") or ""
        texto = normalizar(original)
        if turno.get("role") == "user":
            dicho_por_usuario += " " + texto
            continue
        if not texto:
            continue
        if ya_cerro:
            agregar(f"siguió hablando después de despedirse: «{original[:60]}»")
        # Cifras con número; se permite "marcar 1"
        if re.search(r"[0-9]", re.sub(r"\bmarcar 1\b", "", texto)):
            agregar(f"dijo cifras con número: «{original[:80]}»")
        for patron in (PATRON_HORA, PATRON_FECHA):
            for m in patron.finditer(texto):
                frase = m.group()
                if not any(contiene(p, frase) for p in permitidos) and not contiene(dicho_por_usuario, frase):
                    agregar(f"«{frase}» no coincide con la cita")
        for prohibida in FRASES_PROHIBIDAS:
            if prohibida in texto:
                agregar(f"frase prohibida: «{prohibida}»")
        if CIERRE in texto:
            ya_cerro = True
    return sospechas


def evaluar(conv, esperado, voz, modo, cita):
    """Compara la conversación contra lo esperado. Regresa (lista de (revisión, ok, detalle), estatus, duración)."""
    resultados = {k: (v or {}).get("value") for k, v in
                  ((conv.get("analysis") or {}).get("data_collection_results") or {}).items()}
    estatus = resultados.get("estatus") or ""
    turnos = conv.get("transcript", [])
    habló_la_persona = any(t.get("role") == "user" and (t.get("message") or "").strip() for t in turnos)
    nota_estatus = ""
    if not estatus and not habló_la_persona and esperado["estatus"] == "Sin respuesta":
        # Si nadie habla, ElevenLabs puede no extraer nada: eso equivale a "Sin respuesta"
        estatus, nota_estatus = "Sin respuesta", " (nadie habló y no hubo extracción)"
    duracion = (conv.get("metadata") or {}).get("call_duration_secs") or 0
    texto_agente = normalizar(" ".join(t.get("message") or "" for t in turnos if t.get("role") == "agent"))

    revisiones = [("Estatus", estatus == esperado["estatus"],
                   f"obtenido «{estatus}», esperado «{esperado['estatus']}»{nota_estatus}")]
    for campo, columna in (("con_quien_hablo", "con_quien_hablo_contiene"), ("motivo", "motivo_contiene"),
                           ("hora_estimada", "hora_estimada_contiene")):
        if esperado[columna]:
            valor = resultados.get(campo) or ""
            revisiones.append((campo, normalizar(esperado[columna]) in normalizar(valor),
                               f"obtenido «{valor}», debe contener «{esperado[columna]}»"))
    if esperado["no_debe_decir_folio"] == "Sí":
        # Ningún dato de la cita: folio, dirección, fecha, hora, contacto en destino ni teléfono de tráfico
        candidatos = {"folio": voz["folio_texto"], "folio dígito por dígito": voz["folio_digitos"],
                      "fecha": voz["fecha_cita_texto"], "hora": voz["hora_cita_texto"],
                      "teléfono de tráfico": voz["tel_trafico_texto"], "destino": cita["destino"],
                      "contacto en destino": cita["contacto_destino"]}
        dichos = [n for n, v in candidatos.items() if contiene(texto_agente, normalizar(v))]
        revisiones.append(("No dio datos de la cita", not dichos,
                           "dijo: " + ", ".join(dichos) if dichos else "no dijo ningún dato"))
    if esperado["max_duracion_seg"] and modo == "voz":
        revisiones.append((f"Duración < {esperado['max_duracion_seg']} s",
                           duracion < int(esperado["max_duracion_seg"]), f"{duracion} s"))
    return revisiones, estatus, duracion


def preguntar(texto, opciones=None):
    """Pregunta en consola sin respuesta por defecto; acepta 'si', 'sí', 's', 'no', 'n' sin importar acentos."""
    equivalencias = {"si": "Sí", "s": "Sí", "no": "No", "n": "No"}
    while True:
        r = input(f"{texto}: ").strip()
        if not opciones:
            return r
        r = equivalencias.get(normalizar(r), r)
        if r in opciones:
            return r
        print(f"  Responde una de: {', '.join(opciones)}")


def resumen_rondas(filas):
    """
    Muestra cada ronda (por modo): un escenario cuenta como pasado solo si TODOS sus intentos
    de esa ronda pasaron. Dice si las dos últimas rondas completas pasaron seguidas.
    """
    rondas = {}
    for f in filas:
        rondas.setdefault((int(f["ronda"]), f["modo"]), {}).setdefault(f["escenario"], []).append(f["paso"])
    completas = {}
    for (ronda, modo) in sorted(rondas):
        esc = rondas[(ronda, modo)]
        marcas = []
        for e in range(1, 9):
            intentos = esc.get(str(e), [])
            if not intentos:
                marcas.append(f"{e}:·")
            else:
                ok = all(p == "Sí" for p in intentos)
                extra = f"({len(intentos)})" if len(intentos) > 1 else ""
                marcas.append(f"{e}:{'✅' if ok else '❌'}{extra}")
        paso_todo = all(esc.get(str(e)) and all(p == "Sí" for p in esc[str(e)]) for e in range(1, 9))
        # Una ronda cuenta como completa si en algún modo (voz o texto) pasaron los 8 escenarios
        completas[ronda] = completas.get(ronda, False) or paso_todo
        print(f"  Ronda {ronda} ({modo}): " + "  ".join(marcas) + ("  → completa ✅" if paso_todo else ""))
    seguidas = [r for r in sorted(completas) if completas[r]]
    if any(r + 1 in seguidas for r in seguidas):
        print("🎉 Dos rondas seguidas con los 8 escenarios pasados: se cumple la salida de la Fase 3.")
    return completas


def main():
    parser = argparse.ArgumentParser(description="Revisa una prueba del agente y la anota en la bitácora.")
    parser.add_argument("--escenario", type=int, required=True, choices=range(1, 9))
    parser.add_argument("--ronda", type=int, required=True, help="número de ronda (1, 2, ...)")
    parser.add_argument("--conversacion", help="ID de la conversación (por defecto, la más reciente)")
    parser.add_argument("--sin-anotar", action="store_true", help="solo revisar, sin escribir en la bitácora")
    args = parser.parse_args()

    valores, faltantes = cargar_env(["ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID"])
    if faltantes:
        detener("Faltan en .env: " + ", ".join(faltantes))
    esperado = next((f for f in leer_csv(RAIZ / "pruebas" / "esperados.csv")
                     if f["escenario"] == str(args.escenario)), None)
    if not esperado:
        detener(f"El escenario {args.escenario} no está en pruebas/esperados.csv")
    _, citas = leer_citas(RAIZ / "datos" / "citas_prueba.csv")
    cita = next((c for c in citas if c["folio"] == esperado["folio"]), None)
    if not cita:
        detener(f"El folio {esperado['folio']} del escenario no está en datos/citas_prueba.csv")
    voz = variables_de_voz(cita)

    if not args.sin_anotar:
        # Revisar antes de las preguntas que la bitácora se pueda escribir (p. ej. que no esté abierta en Excel)
        try:
            with BITACORA.open("a", encoding="utf-8"):
                pass
        except PermissionError:
            detener("No se puede escribir pruebas/bitacora.csv. ¿Está abierta en Excel? Ciérrala e intenta de nuevo.")
        ya_anotadas = {f["id_conversacion"] for f in leer_csv(BITACORA)} if BITACORA.stat().st_size > 3 else set()

    conv = traer_conversacion(valores["ELEVENLABS_API_KEY"], valores["ELEVENLABS_AGENT_ID"], args.conversacion)
    variables = variables_de_la_conversacion(conv)
    modo = "texto" if str(variables.get("system__is_text_only", "")).lower() == "true" else "voz"
    inicio = (conv.get("metadata") or {}).get("start_time_unix_secs")
    cuando = datetime.fromtimestamp(inicio, ZONA_CDMX).strftime("%Y-%m-%d %H:%M") if inicio else "¿?"
    print(f"\nEscenario {args.escenario}: {esperado['nombre']} — conversación {conv['conversation_id']} "
          f"({cuando}, por {modo})\n")

    # ¿La conversación usó la cita de este escenario? (se compara contacto y destino, que no dependen
    # del formato de voz)
    usada = (variables.get("contacto"), variables.get("destino"))
    if usada[0] and usada != (cita["contacto"], cita["destino"]):
        detener(f"Esta conversación usó otra cita ({usada[0]}, {usada[1]}), no la del escenario {args.escenario} "
                f"(folio {esperado['folio']}, {cita['contacto']}). Carga la cita con agente\\usar_cita_en_prueba.py "
                f"--escenario {args.escenario} y repite la prueba, o indica la conversación correcta con --conversacion.")
    if not args.sin_anotar and conv["conversation_id"] in ya_anotadas:
        detener("Esta conversación ya está anotada en la bitácora. ¿Ya hiciste la siguiente prueba?")

    for t in conv.get("transcript", []):
        if t.get("message"):
            quien = "Sofía" if t.get("role") == "agent" else "Persona"
            print(f"  {t.get('time_in_call_secs', 0):>4}s {quien:<7}: {t['message']}")

    revisiones, estatus, duracion = evaluar(conv, esperado, voz, modo, cita)
    sospechas = datos_sospechosos(conv, voz)
    print("\nRevisión automática:")
    for nombre, ok, detalle in revisiones:
        print(f"  {'✅' if ok else '❌'} {nombre}: {detalle}")
    print(f"  {'⚠️ ' if sospechas else '✅'} Cosas a revisar en lo que dijo Sofía: {len(sospechas)}")
    for s in sospechas:
        print(f"       - {s}")
    print("  ℹ️  Revisa tú también lo específico del escenario en pruebas/escenarios.md")

    if args.sin_anotar:
        return
    print()
    quien = preguntar("¿Quién probó?")
    incorrecto = preguntar("¿Dijo algún dato incorrecto o algo que no debía? (Sí/No)", ["Sí", "No"])
    especifico = preguntar("¿Cumplió lo específico del escenario? (Sí/No)", ["Sí", "No"])
    naturalidad = preguntar("Naturalidad del 1 al 5", ["1", "2", "3", "4", "5"])
    comentarios = preguntar("Comentarios (opcional)")
    paso = all(ok for _, ok, _ in revisiones) and incorrecto == "No" and especifico == "Sí"

    nueva = BITACORA.stat().st_size <= 3  # vacía o solo con la marca BOM
    with BITACORA.open("w" if nueva else "a", encoding="utf-8-sig" if nueva else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_BITACORA)
        if nueva:
            w.writeheader()
        w.writerow({
            "fecha": datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M"), "ronda": args.ronda, "modo": modo,
            "escenario": args.escenario, "quien_probo": quien, "folio": esperado["folio"],
            "id_conversacion": conv["conversation_id"], "estatus_obtenido": estatus,
            "estatus_esperado": esperado["estatus"], "dijo_dato_incorrecto": incorrecto,
            "datos_a_revisar": " | ".join(sospechas), "naturalidad_1a5": naturalidad,
            "duracion_seg": duracion, "paso": "Sí" if paso else "No", "comentarios": comentarios,
        })
    print(f"\n{'✅ PASA' if paso else '❌ NO PASA'} — anotado en pruebas/bitacora.csv\n")
    resumen_rondas(leer_csv(BITACORA))


if __name__ == "__main__":
    main()
