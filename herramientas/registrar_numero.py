r"""
Registra en ElevenLabs el número de Twilio del .env y guarda el phone_number_id en .env
(ELEVENLABS_PHONE_NUMBER_ID), igual que subir_agente.py guarda el ID del agente.

Es lo que permite que ElevenLabs llame por Twilio (POST /v1/convai/twilio/outbound-call). Registrar el número
no hace llamadas ni gasta saldo, pero cambia la configuración de la cuenta de ElevenLabs: pide escribir SI.

Documentación consultada (2026-11-25):
  https://elevenlabs.io/docs/api-reference/phone-numbers/create   (POST /v1/convai/phone-numbers)
  Cuerpo para Twilio: phone_number, label, sid (Account SID), token (Auth Token) y provider "twilio".
  Respuesta: phone_number_id.

Uso:
    .venv\Scripts\python herramientas\registrar_numero.py
"""

import sys
from pathlib import Path

import requests
from dotenv import set_key

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.seguridad import RUTA_ENV, cargar_env, detener, enmascarar  # noqa: E402

API = "https://api.elevenlabs.io"
ETIQUETA = "Sofía - seguimiento"
REQUERIDAS = ["ELEVENLABS_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_NUMERO"]


class ErrorRegistro(Exception):
    """No se pudo registrar el número. El mensaje no trae keys, SIDs, tokens ni el número."""


def registrar(env, http=requests):
    """Registra el número de Twilio en ElevenLabs y regresa su phone_number_id."""
    cuerpo = {
        "phone_number": env["TWILIO_NUMERO"],
        "label": ETIQUETA,
        "provider": "twilio",
        "sid": env["TWILIO_ACCOUNT_SID"],
        "token": env["TWILIO_AUTH_TOKEN"],
    }
    try:
        r = http.post(f"{API}/v1/convai/phone-numbers", headers={"xi-api-key": env["ELEVENLABS_API_KEY"]},
                      json=cuerpo, timeout=60)
    except requests.RequestException as e:
        # El texto de la excepción puede traer la URL o los datos de Twilio: solo se dice el tipo
        raise ErrorRegistro(f"No se pudo conectar con ElevenLabs ({type(e).__name__})") from None
    if r.status_code not in (200, 201):
        raise ErrorRegistro(f"ElevenLabs rechazó el registro (HTTP {r.status_code}). "
                            "Revisa el Account SID, el Auth Token y el número de Twilio en .env.")
    try:
        phone_number_id = r.json().get("phone_number_id")
    except ValueError:
        phone_number_id = None
    if not phone_number_id:
        raise ErrorRegistro("ElevenLabs no regresó el phone_number_id")
    return phone_number_id


def main():
    valores, faltantes = cargar_env(REQUERIDAS)
    if faltantes:
        detener("Faltan en .env: " + ", ".join(faltantes))
    existente, _ = cargar_env(["ELEVENLABS_PHONE_NUMBER_ID"])
    if existente:
        detener("Ya hay un ELEVENLABS_PHONE_NUMBER_ID en .env; no se registra otra vez. "
                "Bórralo de .env solo si de verdad quieres registrar el número de nuevo.")
    print(f"Se va a registrar en ElevenLabs el número de Twilio …{valores['TWILIO_NUMERO'][-4:]} "
          f"(Account SID {enmascarar(valores['TWILIO_ACCOUNT_SID'])}) como '{ETIQUETA}'.")
    try:
        respuesta = input("Escribe SI (en mayúsculas) para continuar: ").strip()
    except EOFError:
        respuesta = ""
    if respuesta != "SI":
        detener("Cancelado por el usuario. No se registró nada.")
    try:
        phone_number_id = registrar(valores)
    except ErrorRegistro as e:
        detener(str(e))
    print(f"✅ Número registrado: …{phone_number_id[-6:]}")
    try:
        set_key(RUTA_ENV, "ELEVENLABS_PHONE_NUMBER_ID", phone_number_id, quote_mode="never")
        print("   Su ID quedó guardado en .env")
    except OSError:
        detener(f"No se pudo escribir en .env (¿está abierto o bloqueado por OneDrive?). "
                f"Agrega a mano la línea ELEVENLABS_PHONE_NUMBER_ID={phone_number_id}")


if __name__ == "__main__":
    main()
