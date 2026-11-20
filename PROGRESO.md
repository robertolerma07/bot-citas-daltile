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
- Credenciales de Twilio reales verificadas: la cuenta es de prueba (Trial), está activa, tiene 0 números verificados y saldo de 0.0 USD (usa los minutos gratis de prueba).
- La consulta del permiso para México por API respondió HTTP 401: la cuenta de prueba no deja leer ese dato. Hay que revisarlo a mano en Voice → Settings → Geo permissions.
- **La Fase 0 cumple el criterio de salida:** `verificar_conexion.py` confirma que las keys de ElevenLabs y Twilio funcionan, sin hacer llamadas.

**Pendientes de Roberto antes de la Fase 4** (no bloquean las Fases 1 a 3)
- Obtener el número de prueba de Twilio y ponerlo en `TWILIO_NUMERO`.
- Verificar los celulares del equipo en Twilio (máximo 5).
- Confirmar que México está habilitado en Geo permissions.
- Llenar `config/numeros_permitidos.txt`.

### Hallazgo sobre la cuenta de prueba de Twilio (2026-11-19)
- La cuenta de prueba **no trae número gratis**: la consola pide upgrade para cualquier número.
- **Voice → Settings** (y con eso Geo permissions) también pide upgrade.
- **Conclusión:** la cuenta de prueba no sirve para las llamadas del bot, aunque sus credenciales sí funcionan para la API.
- **Decisión:** el upgrade se hace justo antes de la Fase 4. Las Fases 1 a 3 no usan Twilio, y el número cobra USD $1.15 al mes desde que se compra.
- **Al hacer el upgrade:**
  - Roberto mete el pago; la carga mínima probable es de USD $20, que es saldo y no gasto.
  - La recarga automática se deja **apagada**.
  - Se compra un número de EE. UU. con voz y se confirma que México esté habilitado.
  - Después del upgrade, Twilio ya no limita a números verificados, así que la lista blanca de los scripts queda como la protección principal.
- **Pendiente de decisión de Roberto:** medir el tope de USD $10 como consumo y no como saldo cargado.
