# Bitácora del proyecto

## 2026-11-19 — Fase 0: Preparación

**Qué se hizo**
- Se revisó la documentación vigente de ElevenLabs Agents y de la cuenta de prueba de Twilio, y se aprobó el plan por fases.
- Se creó el proyecto en `Escritorio\bot-citas-daltile` con `git`, `.gitignore`, `.env.example`, `README.md`, `requirements.txt` y el entorno virtual `.venv` (Python 3.12).
- `lib/seguridad.py`: lista blanca, horario 9:00–20:00 CDMX con `--forzar`, confirmación con `SI` y keys enmascaradas.
- `verificar_conexion.py`: solo lectura. Revisa la key de ElevenLabs y la cuenta de Twilio (tipo, números verificados, saldo y permiso para México).

**Decisiones**
- La API de ElevenLabs se usa por REST directo (`requests`), con endpoints confirmados en la documentación, en lugar del SDK, porque el nombre de algunos métodos del SDK no está documentado.
- `config/numeros_permitidos.txt` también queda fuera de git porque contiene celulares reales; se versiona solo `numeros_permitidos.ejemplo.txt`.
- La llamada en lote se hará con un script propio, no con la llamada en lote de ElevenLabs (que será reemplazada por Campaigns).

**Pendientes**
- Roberto: crear cuentas, llenar `.env` y la lista blanca, y verificar celulares en Twilio.
- Correr `verificar_conexion.py` con keys reales y reportar si México está habilitado.
- Riesgo abierto: el aviso de la cuenta de prueba de Twilio podría estorbar al agente (se confirma en la Fase 4).

**Verificación**
- Sin `.env`, `verificar_conexion.py` se detiene con un mensaje claro.
- Con keys falsas, las dos APIs responden HTTP 401 y la salida muestra las keys enmascaradas.
- Sin red, el script reporta el error sin mostrar la URL ni el SID.
- Candados probados:
  - número fuera de la lista y lista vacía;
  - formato `+521…` antiguo;
  - archivo con BOM o en ANSI;
  - dígitos no ASCII;
  - horario a las 22:30, con `--forzar` y con hora en UTC;
  - confirmación con "si" en minúsculas, sin consola y con 0 llamadas.
- Un revisor independiente encontró 3 problemas medios: un error de red que mostraba el SID, el script que se caía sin red, y `detener()`, que podía fallar con la salida redirigida. Los 3 se corrigieron y se volvieron a probar.
- La key real de ElevenLabs funciona: es restringida (ElevenAgents y Voces en escritura, Usuario con acceso), el plan es Free con 0 de 10,000 créditos usados y no hay agentes. Twilio sigue pendiente.
- `verificar_conexion.py` ahora revisa cada servicio por separado, para poder verificar ElevenLabs aunque Twilio todavía no esté configurado.
