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

## 2026-11-19 — Fase 1: Datos

**Qué se hizo**
- `datos/citas_prueba.csv`: 3 citas ficticias (1 Despacho, 2 Operador), con columnas de cita y de resultado. Se agregó la columna `ultimo_intento` para los reintentos de la Fase 4.
- `datos/citas_con_errores.csv` (con errores a propósito) y `datos/numeros_demo.txt` (lista blanca de los teléfonos ficticios). Los genera `herramientas/generar_datos_ejemplo.py`.
- `lib/formato_voz.py`: convierte los datos en texto hablado, por ejemplo:
  - "el martes primero de diciembre";
  - "a las cuatro cuarenta y cinco de la tarde";
  - folio dígito por dígito;
  - teléfono de tráfico en pares, y dígito por dígito para cuando piden repetirlo.
- `validar_citas.py`. Revisa:
  - columnas faltantes o repetidas;
  - campos vacíos y valores de más;
  - teléfonos en formato `+52` y 10 dígitos, con pistas para el `1` antiguo y el `+` que borra Excel;
  - fechas y horas;
  - tipo de contacto;
  - folios repetidos, aunque cambie la escritura;
  - lista blanca;
  - citas con fecha pasada;
  - estatus e intentos.

  Avisa también si una dirección trae abreviaturas. Con `--mostrar-voz` enseña cómo dirá el bot cada cita.
- `tests/test_fase1.py`: 53 pruebas automáticas (`pytest`).

**Verificación**
- El archivo bueno pasa (0 errores) y el archivo con errores falla con los 8 errores sembrados más 1 advertencia.
- Con la lista blanca real, que todavía está vacía, el validador bloquea todo.
- 53 de 53 pruebas pasan.
- Una revisión independiente encontró 2 problemas importantes, ya corregidos con su prueba:
  - El bot iba a decir "con uno minutos" a la hora :01; ahora dice "con un minuto".
  - Un CSV con dos columnas `telefono` podía pasar la validación con un número y llamar a otro; ahora se rechaza.
- También se corrigieron puntos menores de esa revisión:
  - la medianoche se dice "de la noche";
  - las letras V y W se dicen "ve" y "doble u";
  - una fecha pasada ahora es error y no solo advertencia;
  - las filas con valores de más se marcan;
  - los números de fila coinciden con Excel aunque haya renglones vacíos.

**Decisiones**
- Fechas y números se formatean en Python antes de enviarlos al agente. El prompt usará `{{fecha_cita_texto}}`, `{{hora_cita_texto}}`, `{{folio_texto}}`, `{{tel_trafico_texto}}` y `{{tel_trafico_digitos}}`.
- Para la Fase 4: los scripts de llamada deben marcar **solo** con las filas que regresa `validar()`, sin volver a leer el CSV por su cuenta, y repetir `verificar_lista_blanca()` justo antes de cada llamada.

**Pendientes**
- Roberto: cuando se definan las personas del equipo que simularán cada escenario, poner sus celulares en las citas y en `config/numeros_permitidos.txt`.
- Si las pruebas pasan del 3 de diciembre, actualizar las fechas de las citas: el validador rechaza fechas pasadas.

## 2026-11-19 — Fase 2: El agente

**Qué se hizo**
- `agente/prompt.md`: tu prompt con ajustes mínimos:
  - usa las variables ya formateadas, incluida la nueva `direccion_texto`, que escribe en palabras el número de la calle;
  - acepta la tecla 1 como confirmación;
  - no deja datos en un buzón de voz;
  - define qué hacer cuando contesta otra persona.
- `agente/config.json`. Contiene:
  - voz con el modelo `eleven_flash_v2_5` (multilenguaje);
  - idioma `es` y LLM `gemini-2.5-flash` con temperatura 0;
  - primer mensaje con `{{saludo}}` según la hora (`lib/formato_voz.saludo`);
  - duración máxima de 120 s y fin de llamada tras 20 s de silencio;
  - tecla 1 (DTMF) y herramientas de terminar llamada y detectar buzón;
  - grabación activada con retención de 30 días;
  - extracción de `estatus` (fijo a los 4 valores), `con_quien_hablo`, `motivo` y `hora_estimada`.
- `agente/subir_agente.py`:
  - crea el agente (guarda su ID en `.env`) o lo actualiza;
  - agrega la voz a "Mis voces" si hace falta;
  - lee de vuelta lo guardado y lo compara campo por campo con lo pedido. `--revisar` solo compara.
- `agente/elegir_voces.py` genera `agente/voces_mexicanas.md` con 73 voces mexicanas que sí sirven para agentes, con enlaces para escucharlas.

**Verificación**
- El agente quedó creado en ElevenLabs (plan Free) y las 11 secciones de la comprobación coinciden con lo pedido; las interrupciones están activadas.
- Una prueba aparte confirma que la comprobación sí falla si cambia la voz, se desactiva la tecla 1 o sobra un campo.
- 73 de 73 pruebas automáticas pasan.

**Hallazgos (no venían en la documentación)**
- Una voz de la biblioteca debe agregarse a "Mis voces" antes de usarla en un agente (`POST /v1/voices/add/{public_owner_id}/{voice_id}`).
- Las voces con "moderación en vivo" no se pueden usar en agentes. Por eso la primera voz provisional, Ale Rodriguez, se descartó, aunque quedó agregada en Mis voces sin usarse. Se usa como provisional Diana - Warm, Expressive & Professional.

**Revisión independiente: correcciones aplicadas**
- Si el operador dice en cualquier momento que va manejando, Sofía se despide de inmediato.
- "Llego, pero tarde" cuenta como No puede, con motivo y hora estimada.
- "No sé, lo reviso" cuenta como Reintentar.
- Si ya confirmaron, el estatus se mantiene aunque la llamada se corte.
- Al repetir, se usan exactamente los mismos textos; el teléfono va dígito por dígito.
- Con ruido, si no marcan 1, no se toma como un sí.
- `hora_estimada` se guarda tal como la dijeron, sin convertirla.
- La voz solo se agrega a Mis voces si ElevenLabs dice que no está, y si falla el guardado en `.env` el script muestra el ID del agente.

**Decisión**
- La despedida al operador que maneja conserva el texto de Roberto ("No se preocupe, le marco más tarde; maneje con cuidado."). El revisor señaló que promete una llamada, pero el sistema sí reintenta.

**Pendientes**
- Roberto: elegir la voz definitiva y probar el agente una vez en el navegador.
- En la prueba en navegador, confirmar en *Advanced* que la entrada por teclado (DTMF) aparece activada. La API siempre regresa esa configuración, así que por API no se distingue si está activa.
- Fase 4: confirmar en una llamada real cómo llega la tecla 1 a la transcripción.
- Fase 4: el escenario 8 (no contesta) se marca con el estado de la llamada, porque si nadie contesta el agente nunca habla.
