r"""
Fase 2 — Lista voces de la biblioteca de ElevenLabs en español con acento mexicano.

Solo consulta (no gasta créditos). Escribe agente\voces_mexicanas.md con los enlaces para
escuchar cada voz, para que Roberto elija una y su voice_id se ponga en agente\config.json.

Uso:
    .venv\Scripts\python agente\elegir_voces.py
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.seguridad import RAIZ, cargar_env, detener  # noqa: E402

API = "https://api.elevenlabs.io"
SALIDA = RAIZ / "agente" / "voces_mexicanas.md"


def buscar_voces(api_key):
    """Pide a la biblioteca todas las voces con idioma español y acento mexicano."""
    r = requests.get(f"{API}/v1/shared-voices", headers={"xi-api-key": api_key},
                     params={"language": "es", "accent": "mexican", "page_size": 100}, timeout=30)
    if r.status_code != 200:
        detener(f"La biblioteca de voces respondió HTTP {r.status_code}.")
    return r.json().get("voices", [])


def main():
    valores, faltantes = cargar_env(["ELEVENLABS_API_KEY"])
    if faltantes:
        detener("Falta ELEVENLABS_API_KEY en .env")
    todas = buscar_voces(valores["ELEVENLABS_API_KEY"])
    # Las voces con moderación en vivo no se pueden usar en agentes (ElevenLabs las rechaza)
    voces = [v for v in todas if not v.get("live_moderation_enabled")]
    print(f"Se descartan {len(todas) - len(voces)} voces con moderación en vivo (no sirven para agentes).")

    # Primero las que pueden usar cuentas gratuitas, luego las más usadas
    voces.sort(key=lambda v: (not v.get("free_users_allowed"), -(v.get("cloned_by_count") or 0)))

    renglones = ["# Voces en español con acento mexicano", "",
                 "Generado por `agente/elegir_voces.py`. Solo aparecen voces que un agente puede usar "
                 "(sin moderación en vivo). Haz clic en **Escuchar** para oír cada voz.", "",
                 "| # | Nombre | Género | Edad | Uso | ¿Plan Free? | Escuchar | voice_id | public_owner_id |",
                 "|---|---|---|---|---|---|---|---|---|"]
    print(f"Voces con acento mexicano: {len(voces)}\n")
    for i, v in enumerate(voces, start=1):
        free = "Sí" if v.get("free_users_allowed") else "No"
        nombre = (v.get("name") or "").replace("|", "/")
        renglones.append(f"| {i} | {nombre} | {v.get('gender')} | {v.get('age')} | {v.get('use_case')} | "
                         f"{free} | [Escuchar]({v.get('preview_url')}) | `{v.get('voice_id')}` | "
                         f"`{v.get('public_owner_id')}` |")
        print(f"{i:>2}. {nombre[:40]:<40} {v.get('gender') or '':<7} {v.get('use_case') or '':<22} Free: {free}")
    SALIDA.write_text("\n".join(renglones) + "\n", encoding="utf-8")
    print(f"\nTabla con enlaces para escuchar: {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
