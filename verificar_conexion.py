"""
Fase 0 — Verifica que las credenciales de ElevenLabs y Twilio funcionan.

SOLO HACE CONSULTAS DE LECTURA. No crea agentes, no compra números, no hace llamadas,
no gasta saldo.

Uso:
    .venv\\Scripts\\python verificar_conexion.py
"""

import sys

import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from lib.seguridad import cargar_env, enmascarar

API_ELEVENLABS = "https://api.elevenlabs.io"


def revisar_sin_filtrar(nombre, funcion, *args):
    """
    Ejecuta la revisión de un servicio. Si falla la red (internet, proxy, DNS), muestra
    solo el tipo de error: el mensaje completo traería la URL con el Account SID.
    """
    try:
        return funcion(*args)
    except Exception as e:
        print(f"❌ {nombre}: error de conexión ({type(e).__name__}). Revisa tu internet e intenta de nuevo.")
        return False


def revisar_elevenlabs(api_key):
    """Lista los agentes (prueba de la key) y consulta el plan contratado. Regresa True si la key sirve."""
    print(f"\n=== ElevenLabs (key {enmascarar(api_key)}) ===")
    encabezados = {"xi-api-key": api_key}

    # 1) Prueba principal: listar agentes. Si esto funciona, la key sirve para Agents.
    r = requests.get(f"{API_ELEVENLABS}/v1/convai/agents", headers=encabezados,
                     params={"page_size": 100}, timeout=20)
    if r.status_code != 200:
        print(f"❌ No se pudo listar agentes (HTTP {r.status_code}). Revisa la key y sus permisos de Agents.")
        return False
    agentes = r.json().get("agents", [])
    print(f"✅ Key válida. Agentes en la cuenta: {len(agentes)}")
    for a in agentes:
        print(f"   - {a.get('name')} (id …{(a.get('agent_id') or '')[-6:]})")

    # 2) Informativo: plan contratado. Si la key no tiene permiso de lectura de usuario, solo avisa.
    r = requests.get(f"{API_ELEVENLABS}/v1/user/subscription", headers=encabezados, timeout=20)
    if r.status_code == 200:
        s = r.json()
        print(f"✅ Plan: {s.get('tier')} (estado: {s.get('status')}); "
              f"créditos usados {s.get('character_count')} de {s.get('character_limit')}")
    else:
        print(f"⚠️  No se pudo leer el plan (HTTP {r.status_code}); la key quizá no tiene permiso de 'User'. No es grave.")
    return True


def revisar_twilio(sid, token, numero):
    """Consulta la cuenta, números verificados, saldo y permiso para llamar a México. Regresa True si funciona."""
    print(f"\n=== Twilio (Account SID {enmascarar(sid)}, token {enmascarar(token)}) ===")
    cliente = Client(sid, token)

    # 1) Prueba principal: leer la cuenta.
    try:
        cuenta = cliente.api.v2010.accounts(sid).fetch()
    except TwilioRestException as e:
        print(f"❌ No se pudo leer la cuenta (HTTP {e.status}). Revisa Account SID y Auth Token.")
        return False
    print(f"✅ Credenciales válidas. Tipo de cuenta: {cuenta.type} · estado: {cuenta.status}")
    if cuenta.type == "Trial":
        print("   ℹ️  Cuenta de PRUEBA: solo llama a números verificados y reproduce un aviso de Twilio al inicio.")

    # 2) Números verificados (los únicos a los que puede llamar una cuenta de prueba).
    try:
        verificados = cliente.outgoing_caller_ids.list(limit=50)
        print(f"✅ Números verificados: {len(verificados)}")
        for v in verificados:
            print(f"   - {v.friendly_name or ''} …{v.phone_number[-4:]}")
    except TwilioRestException as e:
        print(f"⚠️  No se pudieron listar los números verificados (HTTP {e.status}).")

    # 3) Saldo.
    try:
        saldo = cliente.api.v2010.account.balance.fetch()
        print(f"✅ Saldo: {saldo.balance} {saldo.currency}")
    except TwilioRestException as e:
        print(f"⚠️  No se pudo leer el saldo (HTTP {e.status}).")

    # 4) Permiso geográfico para llamar a México.
    try:
        mx = cliente.voice.v1.dialing_permissions.countries("MX").fetch()
        if mx.low_risk_numbers_enabled:
            print("✅ Llamadas a México: HABILITADAS en Geo permissions")
        else:
            print("❌ Llamadas a México: DESHABILITADAS. Actívalas en Voice → Settings → Geo permissions.")
    except TwilioRestException as e:
        print(f"⚠️  No se pudo consultar el permiso de México (HTTP {e.status}).")

    # 5) Número de Twilio configurado en .env (solo se muestra, no se usa).
    if numero:
        print(f"ℹ️  Número de Twilio en .env: …{numero[-4:]}")
    else:
        print("⚠️  TWILIO_NUMERO está vacío en .env (se necesitará en la Fase 4).")
    return True


def main():
    print("Verificación de conexión — solo lectura, sin llamadas ni gastos.")
    valores, faltantes = cargar_env(
        ["ELEVENLABS_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_NUMERO"]
    )
    # Cada servicio se revisa solo si sus datos ya están en .env (TWILIO_NUMERO es opcional aquí).
    if "ELEVENLABS_API_KEY" in valores:
        ok_el = revisar_sin_filtrar("ElevenLabs", revisar_elevenlabs, valores["ELEVENLABS_API_KEY"])
    else:
        print("\n❌ ElevenLabs: falta ELEVENLABS_API_KEY en el archivo .env.")
        ok_el = False

    if "TWILIO_ACCOUNT_SID" in valores and "TWILIO_AUTH_TOKEN" in valores:
        ok_tw = revisar_sin_filtrar("Twilio", revisar_twilio, valores["TWILIO_ACCOUNT_SID"],
                                    valores["TWILIO_AUTH_TOKEN"], valores.get("TWILIO_NUMERO"))
    else:
        faltan_tw = [f for f in faltantes if f in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")]
        print("\n❌ Twilio: faltan en el archivo .env: " + ", ".join(faltan_tw))
        ok_tw = False

    print("\n=== Resumen ===")
    print(f"ElevenLabs: {'✅' if ok_el else '❌'}   Twilio: {'✅' if ok_tw else '❌'}")
    sys.exit(0 if (ok_el and ok_tw) else 1)


if __name__ == "__main__":
    main()
