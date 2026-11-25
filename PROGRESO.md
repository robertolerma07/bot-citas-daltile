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

### 2026-11-20 — Primera prueba en navegador y cierre de la Fase 2
- **Voz definitiva:** Roberto eligió Diana - Warm, Expressive & Professional.
- **Prueba de Roberto en navegador** (conversación `conv_9301m7vrxv5hf45vvtnd028xhb30`, 107 s, 1,668 créditos, LLM USD $0.0237):
  - ✅ Dijo todos los datos exactamente como están en la tabla, sin inventar.
  - ✅ La extracción dio `estatus = Confirmada` y `con_quien_hablo = Juan Pérez`.
  - ✅ A una pregunta que no sabía contestó "no tengo esa información" y dio el teléfono de tráfico.
  - ✅ Cuando le preguntaron, dijo que es asistente automática.
- **Ajustes después de la prueba:**
  - El folio dígito por dígito sonaba raro; ahora se dice en pares ("cuarenta y cinco, ochenta y dos, diecisiete") y dígito por dígito solo si piden repetirlo (`folio_digitos`).
  - Se prohibió "¿hay algo más en lo que le pueda ayudar?", que alargaba la llamada.
  - Después del cierre, ahora cuelga de inmediato, sin esperar respuesta.
- **Costo:** una prueba de unos 2 minutos gastó 1,668 de los 10,000 créditos del plan Free. Con Free quedan unas 5 pruebas más; la Fase 3 (16 o más pruebas) necesita Starter.
- **La Fase 2 cumple su criterio de salida:** el agente existe con la voz elegida y las variables configuradas, y Roberto lo probó desde el navegador.

## 2026-11-20 — Fase 3: Pruebas en navegador (archivos listos)

**Qué se hizo**
- `pruebas/escenarios.md`: guía de los 8 escenarios (qué decir y qué se espera) y regla de salida.
- `pruebas/esperados.csv`: resultados esperados de cada escenario, para revisarlos en automático.
- `pruebas/bitacora.csv`: bitácora de pruebas, todavía vacía.
- `agente/usar_cita_en_prueba.py --escenario N`: carga la cita del escenario en el agente. `subir_agente.py` ahora acepta `--folio`, conserva la cita cargada y pone el saludo según la hora.
- `pruebas/revisar_prueba.py`. Hace esto:
  - trae la conversación y confirma que sea de la cita del escenario;
  - detecta si fue por voz o por texto;
  - compara estatus, nombre, motivo y hora estimada;
  - busca fechas y horas que no son de la cita, cifras con número, frases prohibidas, datos dichos en los escenarios 3 y 8, y si siguió hablando después de despedirse;
  - pregunta la parte humana y anota en la bitácora con el resumen de rondas. Un escenario reintentado en la misma ronda no cuenta como pasado.

**Verificación**
- 90 pruebas automáticas pasan, con conversaciones inventadas: datos correctos sin falsos positivos, fecha y hora inventadas, folio sin comas, teléfono de tráfico dicho en el escenario 3, silencio en el escenario 8, rondas con reintento.
- Con la prueba real de Roberto (`conv_9301…`), el script marca solos los dos problemas vistos a mano ("¿algo más…?" y hablar después de despedirse) y la duración de 107 s. Con un escenario equivocado, se detiene.
- La revisión independiente encontró falsos positivos del detector de horas, fugas no detectadas, riesgo de anotar la conversación de otro escenario y rondas que pasaban con reintentos. Todo se corrigió y se probó.

**Costos medidos**
- 1,668 créditos por 107 s (unos 935 créditos por minuto). Los 10,000 del plan Free alcanzan para unos 6 minutos.
- Starter (30,000 créditos) no alcanza para la Fase 3 y la Fase 4 completas por voz.
- Propuesta: ronda 1 por texto y ronda 2 por voz.

**Pendientes**
- Roberto: subir a Starter y correr la ronda 1.
- Hacer una prueba de silencio (escenario 8) antes de la ronda 1, para ver qué extrae ElevenLabs cuando nadie habla.

### 2026-11-20 — Decisión de Roberto: se elimina la regla de manejo
- Hoy los operadores contestan los seguimientos con manos libres o altavoz. Roberto decidió quitar la regla "si está manejando, se despide y Reintentar", tanto para el MVP como para esta prueba.
- **Prompt:** si dice que va manejando, Sofía no cuelga; es más breve y clara, y sigue con los datos. Se quitó "manejando" de la descripción de `Reintentar` en `config.json`.
- **Escenario 3:** ahora es "Contesta manejando con manos libres" y espera Confirmada en menos de 90 s. Las pruebas de fuga de datos se pasaron al escenario 8.
- Agente actualizado y comprobado; 90 pruebas pasan.

## 2026-11-20 — Diseño y plan del seguimiento en ruta (MVP)
- Lluvia de ideas sobre el costo con Roberto: las 3 llamadas diarias son de seguimiento en ruta. Se eligió el enfoque B (solo llamadas cortas, con frecuencia adaptable) en vez del de GPS (A) o de cambiar de proveedor (C).
- Diseño aprobado: `docs/superpowers/specs/2026-11-20-seguimiento-en-ruta-design.md`.
- Plan de construcción en 6 tareas: `docs/superpowers/plans/2026-11-20-seguimiento-en-ruta.md`. Se construye después de cerrar las Fases 3 a 6.
- Costo estimado del MVP de seguimiento: unos USD $100–200 al mes para 50 líneas, contra $1,270–1,900 del esquema original.
- Forma de construcción elegida por Roberto: **un revisor independiente por tarea** (subagent-driven-development), cuando se cierren las Fases 3 a 6.

## 2026-11-24 — Respaldo en GitHub
- Repositorio **privado**: https://github.com/robertolerma07/bot-citas-daltile (rama `master`, 13 commits subidos).
- Antes de subir se verificó que `.env`, `config/numeros_permitidos.txt` y `resultados/` están ignorados, y que ningún archivo versionado contiene keys ni SIDs.
- De aquí en adelante, después de cada commit se hace `git push`.

## 2026-11-25 — Seguimiento de domingo (MVP): Tareas 1 a 9
Rama `domingo-mvp`, juntada con `master` el 2026-11-25 tras la revisión final (316 pruebas). Diseño: `docs/superpowers/specs/2026-11-24-seguimiento-domingo-design.md`; plan: `docs/superpowers/plans/2026-11-24-seguimiento-domingo.md`.

**Qué se hizo**
- Reglas de llamada y decisión; agente "Sofía - seguimiento" como código (no da por buena una respuesta vaga).
- Aprobación y estado guardados (archivos con permisos 0600); llamadas por Twilio y lectura del resultado.
- Avisos por correo (uno por persona de monitoreo, solo con sus casos) y resumen en Excel.
- Latido (`domingo.latido`): llama, reintenta (19:00 y 19:30) y avisa; candado vivo y sin gastar intentos cuando falla la API; un número que no marca pasa a monitoreo sin detener la ronda.
- Página web (`domingo.servir`): subir, aprobar exactamente lo revisado, detener; sesión ligada a la contraseña y teléfonos ocultos.
- Tarea 9: guía para Roberto (`docs/guia-servidor-domingo.md`) y archivos de despliegue en `despliegue/` (`instalar.sh`, servicio de systemd, Caddy con sslip.io, crontab del latido).

**Decisiones**
- Servidor nuevo en Lightsail (`bot-domingo`), separado de `srm-piloto`. Usuario `sofia` dueño del código, `.venv` y `resultados/`; la página y `cron` corren con ese mismo usuario.
- HTTPS con Caddy y dominio `<IP-con-guiones>.sslip.io`; solo puertos 22, 80 y 443.
- Llave de despliegue de GitHub de solo lectura; la rama a desplegar es una variable (`RAMA`, por omisión `master`).
- El `.env` y `config/numeros_permitidos.txt` se crean a mano en el servidor; `instalar.sh` no activa la página si faltan.
- El código usa hora de CDMX, así que la zona horaria del servidor no importa.

**Verificación**
- `bash -n despliegue/instalar.sh` sin errores (`shellcheck` no está instalado en esta PC). 299 pruebas pasan en la PC. El script NO se ha corrido en un servidor real.

**Pendientes**
- Roberto, fuera del servidor (detalle en la guía, Parte A): subir Twilio a cuenta pagada con recarga automática apagada, comprar el número de EE. UU., confirmar México en Geo permissions, correr `registrar_numero.py`, crear el Gmail del bot con verificación en dos pasos y contraseña de aplicación, subir el plan de ElevenLabs, y empezar el trámite del número mexicano (Regulatory Compliance).
- Crear la instancia y correr `instalar.sh` (guía, Partes B y C). Si el instalador falla en el servidor real, anotar el error aquí.
- **Prueba en seco en el servidor (sin llamar):** con `"ensayo": true`, subir `datos/viajes_prueba.xlsx` y aprobarlo desde la página; correr `.venv/bin/python -m domingo.latido` a mano un día que no sea domingo y confirmar que no hace nada (revisar `resultados/domingo/latido.log`); confirmar que llega el correo de aprobación.
- **Ensayo real un domingo** (gasta créditos y saldo): 4 o 5 celulares del equipo simulan los casos del diseño 5.8 (a tiempo, tarde, vago, no contesta, contesta otra persona). Revisar: estados finales; un correo por persona de monitoreo solo con sus casos; correo de control a las 13:00 y a las 19:30; reintentos a las 19:00 y 19:30; resumen del lunes a las 7:00 con el Excel. Anotar aquí IDs de conversación, duraciones, costo real por llamada y ajustes.
- Prueba en navegador de "Sofía - seguimiento" (se aplazó; solo se verificó por API).
- ✅ 2026-11-25: `domingo-mvp` juntada con `master` después de la revisión final; se despliega `master`.

### 2026-11-25 — Primera prueba en navegador de «Sofía - seguimiento»
- Conversación `conv_7501m89rvz7kem89my24kfaeyy0h` (60 s, voz, 1,023 créditos). Respuesta "no sé, a lo mejor sí" → preguntó la hora una vez → "a las doce" → confirmó "el lunes treinta de noviembre a las doce de la tarde". Extracción correcta (`llega_antes_de_la_cita = no`, `hora_estimada = 12:00`, `fecha_estimada = 2026-11-30`); decisión del bot: **monitoreo**, correcta.
- Fallas encontradas y corregidas en `agente_seguimiento/`:
  - No preguntó "¿Qué pasó?" aunque la hora era después de la cita: el paso 6 ahora compara antes de confirmar y pregunta siempre el motivo si va retrasado.
  - Se despidió y no colgó (la llamada llegó al tope de 60 s): el cierre ahora pide usar `end_call` en el mismo turno, y el colgado por silencio baja de 20 a 12 s.
- Agente actualizado (todas las secciones ✅); 318 pruebas pasan. Falta repetir las pruebas a tiempo, tarde, vaga y "ya entregué".

### 2026-11-25 — Segunda prueba en navegador y tope de 90 s (decisión de Roberto)
- Conversación `conv_8101m89v38k1fkgv44q5mbntfrzg` (60 s, 1,089 créditos): "no sé, depende del tráfico" → "a la una o a las dos, no estoy seguro" → Sofía **sí preguntó "¿Qué pasó?"** (motivo "el tráfico"); `hora_estimada` vacía, sin inventar; decisión: **monitoreo**, correcta.
- Falla: intentó confirmar una hora insegura y la llamada llegó al tope de 60 s antes del cierre, así que el operador no oyó el WhatsApp de Monitoreo (tampoco se pudo comprobar que cuelgue sola).
- Ajustes: un rango de horas o "no estoy seguro" cuentan como respuesta vaga (no se confirman; se va directo al cierre), en el prompt y en la extracción. **Decisión de Roberto:** la duración máxima sube de 60 a 90 s como red de seguridad; la meta sigue siendo ~30 s. Costo: solo las llamadas de más de 60 s cobran un minuto más en Twilio (~USD 0.05) y unos 450 créditos más.
- Créditos de ElevenLabs: 5,996 de 10,000 usados. Antes del domingo de ensayo hay que subir a Starter.

### 2026-11-25 — Tercera prueba y ajustes de voz (decisiones de Roberto)
- Conversación `conv_9601m89wh46wfby84ehzee5a8615` (49 s, 685 créditos): no confirmó la hora insegura, dio el WhatsApp de Monitoreo y **colgó sola con `end_call`**; decisión: monitoreo, correcta.
- **Teléfono de Monitoreo:** ahora se dice en grupos 2-2-3-3 (los dos primeros pares y los últimos 6 en dos grupos de 3): "ochenta y uno... ochenta y tres... cero cero cuatro... quinientos" (`lib/formato_voz.telefono_por_grupos`). Al repetirlo, los mismos grupos dígito por dígito. El agente de avisos de cita no cambia.
- **Despedida:** el "Gracias." sonaba acartonado; ahora es "¡Muchas gracias! … ¡Que tenga muy buen día!" con la instrucción de decirlo con energía y calidez.
