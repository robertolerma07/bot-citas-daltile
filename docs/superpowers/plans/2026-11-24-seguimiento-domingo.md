# Seguimiento de domingo por voz — Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usa superpowers:subagent-driven-development (elegido por Roberto: un revisor
> independiente por tarea) para implementar este plan tarea por tarea. Los pasos usan casillas (`- [ ]`).

**Meta:** Que cada domingo Sofía llame a los operadores de los viajes de una lista aprobada en una página web, registre a
los que llegan a tiempo y avise por correo a la persona de monitoreo de cada cliente de los que no.

**Arquitectura:** Un paquete nuevo `domingo/` en este repositorio:
- un **validador del Excel** de viajes y unas **reglas puras** que deciden a quién llamar y qué hacer con cada resultado;
- un **"latido"** (`python -m domingo.latido`) que el programador de tareas corre cada 5 minutos. Mira la hora de CDMX y
  el estado guardado, hace lo que toque (llamar, reintentar, mandar correos) y termina. Si el servidor se reinicia, el
  siguiente latido retoma donde se quedó;
- una **página web** pequeña (Flask servida con waitress) para subir, aprobar y detener;
- un agente nuevo **"Sofía - seguimiento"** en ElevenLabs, versionado como código igual que el de la prueba de concepto.

Las llamadas se hacen una por una con la integración nativa de Twilio de ElevenLabs. El resultado se consulta a
ElevenLabs al terminar cada llamada, sin webhook.

**Tecnología:** Python 3.12+, `requests`, `python-dotenv`, `tzdata`, `openpyxl`, `pytest`, `smtplib` (biblioteca
estándar), y nuevas: `flask` y `waitress`. Despliegue en Lightsail Ubuntu con Caddy (HTTPS), systemd y cron.

**Diseño:** `docs/superpowers/specs/2026-11-24-seguimiento-domingo-design.md`. Léelo completo junto con este plan;
manda sobre `2026-11-20-seguimiento-en-ruta-design.md` y reemplaza al plan `2026-11-20-seguimiento-en-ruta.md`.

## Restricciones globales
- Hora de referencia: `America/Mexico_City` (`lib.seguridad.ZONA_CDMX`). Toda comparación de horas se hace con
  `datetime` con zona; nunca con la hora del sistema sin zona.
- Calendario (en `config/domingo.json`, nunca en el código): aprobar hasta **domingo 12:00**; ronda **13:00**;
  reintentos **19:00** y **19:30**; **3 llamadas máximo por viaje**; ventana de llamadas **domingo 13:00 a 21:00**;
  rango de citas sin advertencia **domingo 13:00 a lunes 13:00**; resumen **lunes 7:00**; límite de cita de Día por
  omisión **16:00**; **10 minutos** mínimo entre llamadas al mismo teléfono; tope de **150** llamadas por domingo.
- A **todo** viaje de la lista aprobada se le llama. Solo se llama a viajes de la lista aprobada del domingo en curso.
- Mientras `config/domingo.json` tenga `"ensayo": true`, además solo a números de `config/numeros_permitidos.txt`, revisado
  al aprobar y otra vez justo antes de cada llamada.
- Quien queda "a tiempo" o "entregado" no recibe otra llamada; quien pasa a monitoreo, tampoco.
- La decisión la toma el código con los datos extraídos, nunca el agente. Las horas que dijo el operador se guardan tal
  como las dijo; el HH:MM solo si fue clara, nunca inventado.
- El código nuevo **no usa `lib.seguridad.detener`** (termina el proceso y tumbaría la página o el latido): regresa
  errores o lanza excepciones propias. Solo los `main()` de línea de comandos pueden terminar con código 1.
- Keys, contraseñas y tokens solo en `.env`; en pantalla y en correos, enmascarados con `lib.seguridad.enmascarar`. En la
  página los teléfonos de operador se muestran con solo los últimos 4 dígitos.
- Nada depende de AWS: el mismo código debe poder correr después en un servidor de la oficina (Windows o Linux).
- El agente de avisos de cita (`agente/`) no cambia de comportamiento.
- Código, comentarios, mensajes y textos en español, en el estilo de los scripts actuales. Después de cada commit,
  `git push` (regla de Roberto del 2026-11-24).

## Enfoque de revisión
1. **Celdas de Excel con tipo equivocado:** teléfono guardado como número (sin `+`, o en notación científica), fecha u
   hora guardadas como celda de fecha/hora de Excel, `8:00` en lugar de `08:00`. Se esperan lecturas correctas o un
   error claro con pista, nunca un teléfono mal leído que se llame. (Tarea 1)
2. **Dos latidos a la vez o reinicio a media llamada:** no se marca dos veces al mismo viaje; la llamada que quedó "en
   curso" se resuelve consultando su conversación. (Tarea 7)
3. **"Detener" a media ronda:** ninguna llamada nueva empieza después de detener; la que está en curso termina. (Tarea 7)
4. **ElevenLabs o Twilio fallan** (HTTP de error, sin saldo, tiempo agotado): cuenta como intento fallido, se anota y
   aparece en el correo de control; tras **3 fallas de API seguidas** se suspende la ronda y se avisa a Roberto, en vez
   de gastar los intentos de todos. (Tarea 7)
5. **Bordes de hora:** hora estimada igual al límite (a tiempo), un minuto después (monitoreo), llegada después de la
   medianoche para una cita del lunes, y "mañana" dicho el domingo (lo resuelve `fecha_estimada`). (Tarea 2)

---

### Task 1: Calendario y lista de viajes (Excel)

**Archivos:**
- Crear: `config/domingo.json`, `domingo/__init__.py`, `domingo/calendario.py`, `domingo/viajes.py`,
  `herramientas/generar_viajes_ejemplo.py`, `datos/viajes_prueba.xlsx`, `datos/viajes_con_errores.xlsx`,
  `plantillas/viajes_domingo.xlsx`
- Prueba: `tests/test_domingo_viajes.py`

**Interfaces:**
- Usa: `validar_citas.revisar_telefono(valor, campo)`, `validar_citas.ABREVIATURAS`, `lib.seguridad.cargar_lista_blanca`,
  `lib.seguridad.ZONA_CDMX`, `lib.formato_voz.fecha_texto`, `hora_texto`, `telefono_pares`, `telefono_digitos`.
- Produce:
  - `config/domingo.json` con las claves `ensayo`, `aprobar_hasta`, `ronda`, `reintentos`, `max_llamadas_por_viaje`,
    `minutos_entre_llamadas_mismo_telefono`, `ventana_llamadas`, `rango_citas`, `resumen_lunes`, `limite_dia_por_omision`,
    `tope_llamadas_por_domingo`, con los valores de las Restricciones globales (horas como `"HH:MM"`).
  - `domingo.calendario.cargar_calendario(ruta=RAIZ/"config"/"domingo.json") -> dict`
  - `domingo.calendario.domingo_de(ahora: datetime) -> date | None`: el domingo al que pertenece `ahora` (el mismo día
    si es domingo; el domingo anterior si es lunes antes de las 12:00, para el resumen); `None` en otro caso.
  - `domingo.calendario.domingo_para_aprobar(ahora: datetime, cal: dict) -> date | None`: el próximo domingo (hoy si es
    domingo antes de `aprobar_hasta`); `None` si es domingo después de `aprobar_hasta` (ese día ya no se aprueba).
  - `COLUMNAS_VIAJE = ["viaje", "linea", "operador", "telefono", "cliente", "destino", "fecha_cita", "tipo_cita", "hora",
    "correo_monitoreo", "telefono_monitoreo"]`
  - `domingo.viajes.leer_excel(ruta) -> tuple[list[str], list[dict]]`: columnas y filas como texto normalizado; cada fila
    trae `_fila` (renglón de Excel). Convierte celdas de fecha a `AAAA-MM-DD`, de hora a `HH:MM`, y `H:MM` a `HH:MM`.
  - `domingo.viajes.validar_viajes(ruta, domingo: date, ahora: datetime, cal: dict, ruta_lista=RUTA_LISTA_BLANCA)
    -> tuple[list[str], list[str], list[dict]]`: (errores, advertencias, viajes). Cada mensaje empieza con `Fila N`.
    Cada viaje válido trae además `limite` (`HH:MM`: la hora en Hora; la hora o `limite_dia_por_omision` en Día).
  - `domingo.viajes.variables_de_voz_viaje(viaje: dict) -> dict` con `operador`, `linea`, `cliente`, `destino`,
    `fecha_cita_texto`, `tipo_cita`, `limite_texto` (sin la "a " inicial), `tel_monitoreo_texto`,
    `tel_monitoreo_digitos`.

- [ ] **Paso 1: Escribe las pruebas que fallan.** Usa `domingo=2026-11-29`, `ahora=2026-11-27 18:00 CDMX` y
  `datos/numeros_demo.txt` como lista blanca.
  - `test_viajes_prueba_pasan`: `datos/viajes_prueba.xlsx` da 0 errores, 0 advertencias y 5 viajes (uno de Día sin hora,
    uno de Día con hora 14:00, tres de Hora).
  - `test_viajes_con_errores_fallan`: `datos/viajes_con_errores.xlsx` da exactamente un error por fila sembrada, que
    contienen: «columna», «telefono», «fecha_cita», «hora», «tipo_cita», «correo_monitoreo», «telefono_monitoreo»,
    «viaje repetido», «ya pasó» y «lista blanca».
  - `test_limite_de_dia_por_omision`: Día con `hora` vacía da `limite == "16:00"`; Día con `14:00` da `"14:00"`; Hora sin
    `hora` es error.
  - `test_telefono_como_numero`: celda numérica `525512345678` da un error que contiene «falta el '+'»; celda
    `5.25512E+11` da error; ninguna de las dos aparece en `viajes`.
  - `test_celdas_de_fecha_y_hora_de_excel`: una celda `datetime(2026,11,30)` y una celda `time(8,0)` se leen como
    `"2026-11-30"` y `"08:00"`; el texto `"8:00"` también da `"08:00"`.
  - `test_advertencias`: cita el martes da advertencia con «¿seguro?» y el viaje sí queda en `viajes`; el mismo teléfono
    en dos viajes da advertencia; `destino` con «Av.» da advertencia.
  - `test_sin_lista_blanca_fuera_de_ensayo`: con `cal["ensayo"] = False`, un teléfono fuera de la lista no es error.
  - `test_domingo_para_aprobar`: viernes 27 → domingo 29; domingo 29 a las 11:59 → 29; domingo 29 a las 12:00 → `None`;
    lunes 30 → domingo 6 de diciembre.
  - `test_variables_de_voz_viaje`: Hora 08:00 del 2026-11-30 da `fecha_cita_texto == "el lunes treinta de noviembre"` y
    `limite_texto == "las ocho de la mañana"`.
- [ ] **Paso 2:** `.venv\Scripts\python -m pytest tests/test_domingo_viajes.py -q` debe FALLAR (módulo inexistente).
- [ ] **Paso 3:** Escribe `config/domingo.json` y `herramientas/generar_viajes_ejemplo.py`, que genera con `openpyxl` los
  dos Excel de `datos/` (datos ficticios, teléfonos de `numeros_demo.txt`, citas del lunes 30 de noviembre de 2026) y la
  plantilla vacía con encabezados, columnas de teléfono como Texto y una hoja "Instrucciones" con las reglas de 5.2 del
  diseño. Córrelo.
- [ ] **Paso 4:** Implementa `domingo/calendario.py` y `domingo/viajes.py`. Errores y advertencias exactamente según 5.2
  del diseño; "ya pasó" se mide contra `ahora` con la fecha y el `limite` de la cita en CDMX.
- [ ] **Paso 5:** La misma corrida debe PASAR y todo `pytest -q` debe seguir verde.
- [ ] **Paso 6:** Commit y push: `Domingo: calendario y lista de viajes en Excel`.

### Task 2: Reglas (lógica pura)

**Archivos:**
- Crear: `domingo/reglas.py`
- Prueba: `tests/test_domingo_reglas.py`

**Interfaces:**
- Usa: `domingo.calendario.cargar_calendario` (solo en pruebas, para tener `cal`).
- Produce:
  - `ESTADOS = ("pendiente", "en_curso", "sin_respuesta", "a_tiempo", "entregado", "monitoreo")`
  - `estado_inicial() -> dict`: `{"estado": "pendiente", "intentos": 0, "ultimo_intento": None, "en_curso": None,
    "historial": [], "aviso_pendiente": False, "fallas_api": 0}`
  - `cita_ya_paso(viaje: dict, ahora: datetime) -> bool`: `ahora` es posterior a `fecha_cita` + `limite` en CDMX.
  - `toca_llamar(viaje, estado, ahora, cal, ultima_llamada_al_telefono: datetime | None) -> bool`
  - `decidir(viaje: dict, resultado: dict, momento_llamada: datetime) -> str`: `"sin_respuesta"`, `"a_tiempo"`,
    `"entregado"` o `"monitoreo"`. `resultado` trae los campos de extracción de la Tarea 3.
  - `aplicar(estado, decision, resultado, ahora, cal, conversacion_id: str | None) -> dict`: estado nuevo, sin modificar
    el anterior.

- [ ] **Paso 1: Escribe las pruebas que fallan.** Viaje Hora `fecha_cita=2026-11-30`, `limite=08:00`.
  - `toca_llamar`:
    - `test_ronda_1300`: pendiente a las 12:59 → False; 13:00 → True; 20:59 → True; 21:00 → False.
    - `test_reintentos`: sin_respuesta con 1 intento: 18:59 → False, 19:00 → True; con 2 intentos y último a las 19:00:
      19:29 → False, 19:30 → True; con 3 intentos → False.
    - `test_finales_no_se_llaman`: a_tiempo, entregado, monitoreo y en_curso → False a cualquier hora.
    - `test_solo_en_domingo`: lunes 13:00 → False.
    - `test_mismo_telefono_10_minutos`: última llamada a ese teléfono hace 9 minutos → False; hace 10 → True.
  - `decidir` (llamada el domingo 29 a las 13:05):
    - `hablo_con_operador=False` → sin_respuesta.
    - `llega_antes_de_la_cita="sí"` sin hora → a_tiempo.
    - `"sí"` con `hora_estimada="08:00"` y `fecha_estimada="2026-11-30"` → a_tiempo (igual al límite).
    - `"sí"` con `"08:01"` y `"2026-11-30"` → monitoreo (la cifra contradice el sí).
    - `"sí"` con `"23:30"` y `"2026-11-29"` → a_tiempo (llega la víspera).
    - `"sí"` con `"07:00"` y `"2026-12-01"` → monitoreo (llega otro día).
    - `"no"` y `"no sabe"` → monitoreo.
    - Cita ya pasada (llamada el 30 a las 09:00): `entrega_realizada="sí"` → entregado; `"no"` → monitoreo; `"no aplica"` →
      monitoreo.
  - `aplicar`:
    - `test_sin_respuesta_suma_intento`: intentos 0 → 1, `ultimo_intento=ahora`, estado sin_respuesta.
    - `test_tercer_sin_respuesta_pasa_a_monitoreo`: con 2 intentos → monitoreo y `aviso_pendiente=True`.
    - `test_a_tiempo_y_entregado_cierran_sin_aviso`.
    - `test_monitoreo_marca_aviso`.
    - `test_historial`: cada llamada agrega fecha, decisión, conversación y los campos extraídos.
    - `test_no_modifica_el_anterior`.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa las funciones sin E/S ni red. `decidir`: si no habló → sin_respuesta; si la cita ya pasó al
  momento de la llamada → según `entrega_realizada`; si no, a_tiempo solo si `llega_antes_de_la_cita == "sí"` y ninguna
  cifra extraída (`fecha_estimada` posterior a la cita, o misma fecha con `hora_estimada` mayor al límite) lo contradice.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit y push: `Domingo: reglas de llamada y decisión`.

### Task 3: Agente "Sofía - seguimiento" como código

**Archivos:**
- Crear: `agente_seguimiento/prompt.md`, `agente_seguimiento/config.json`
- Modificar: `agente/subir_agente.py`, `lib/formato_voz.py` (saludo), `.env.example`
- Prueba: `tests/test_domingo_agente.py`, y agrega casos a `tests/test_fase1.py::test_saludo`

**Interfaces:**
- Usa: `domingo.viajes.variables_de_voz_viaje`, `domingo.viajes.validar_viajes` (primer viaje de
  `datos/viajes_prueba.xlsx` como ejemplo).
- Produce:
  - `subir_agente.py --agente {aviso,seguimiento}` (por omisión `aviso`, que sigue igual). `seguimiento` usa la carpeta
    `agente_seguimiento/` y guarda el ID en `ELEVENLABS_AGENT_ID_SEGUIMIENTO`.
  - Variables dinámicas del agente: las de `variables_de_voz_viaje` más `saludo`, `cita_ya_paso` (`"sí"`/`"no"`) y
    `hoy_texto` (fecha de la llamada en palabras, para que resuelva "mañana").
  - Campos de extracción, exactamente: `hablo_con_operador` (boolean), `llega_antes_de_la_cita` (enum `sí`, `no`,
    `no sabe`), `entrega_realizada` (enum `sí`, `no`, `no aplica`), `hora_estimada_dicha` (string),
    `hora_estimada` (string `HH:MM` o vacío), `fecha_estimada` (string `AAAA-MM-DD` o vacío), `motivo` (string).

- [ ] **Paso 1: Escribe las pruebas que fallan** (sin red).
  - `test_prompt_usa_solo_variables_conocidas`: toda `{{var}}` del prompt y del primer mensaje existe en las variables
    de ejemplo.
  - `test_extraccion_exacta`: las claves de `extraccion_de_datos` son exactamente las 7 de arriba, con esos tipos y enums.
  - `test_misma_voz_y_privacidad`: `voz`, `llm`, `temperatura`, `dtmf` y `privacidad` iguales a `agente/config.json`;
    `duracion_maxima_seg == 60`.
  - `test_cierre_whatsapp`: el prompt contiene «por WhatsApp al teléfono de Monitoreo» y `{{tel_monitoreo_texto}}`.
  - `test_aviso_sin_cambios`: `armar_cuerpo` de `agente/` produce el mismo cuerpo que antes del cambio.
  - En `test_saludo`: `("00:30", "Buenas noches")`, `("04:59", "Buenas noches")`, `("05:00", "Buenos días")`.
- [ ] **Paso 2:** La corrida debe FALLAR.
- [ ] **Paso 3:** Escribe el prompt según 5.4 del diseño, en el estilo de `agente/prompt.md`:
  - las dos ramas (`cita_ya_paso` no / sí);
  - una sola vez "¿A qué hora calcula llegar?";
  - repetir día y hora completos para confirmar;
  - cierre textual «Si algo cambia, por favor avise por WhatsApp al teléfono de Monitoreo, {{tel_monitoreo_texto}}»,
    y terminar la llamada sin volver a hablar aunque le digan algo después;
  - otra persona: pedir al operador y, si no está, cerrar sin datos;
  - reglas heredadas: no inventar, no prometer, no reprogramar, interrupciones, buzón, «asistente automática», nunca
    «¿algo más…?».

  Las descripciones de extracción dicen cuándo va cada valor; `llega_antes_de_la_cita = sí` solo si lo dijo claro y lo
  confirmó al repetirle día y hora. Generaliza `subir_agente.py` y agrega `ELEVENLABS_AGENT_ID_SEGUIMIENTO=` a
  `.env.example`. Cambia `saludo` para que antes de las 5:00 diga «Buenas noches».
- [ ] **Paso 4:** Las pruebas deben PASAR y todo `pytest -q` verde. Corre
  `.venv\Scripts\python agente\subir_agente.py --agente seguimiento`: crea el agente y todas las secciones salen ✅.
  Corre `.venv\Scripts\python agente\subir_agente.py --revisar` para el agente de avisos: todo ✅ (no cambió).
- [ ] **Paso 5:** Prueba en navegador con Roberto (gasta créditos; pide permiso antes): un caso a tiempo, uno tarde y uno
  con la cita ya pasada. Anota en `PROGRESO.md` los IDs, la duración y si la extracción salió como se esperaba.
- [ ] **Paso 6:** Commit y push: `Domingo: agente Sofía - seguimiento como código`.

### Task 4: Aprobación y estado guardados

**Archivos:**
- Crear: `domingo/almacen.py`
- Prueba: `tests/test_domingo_almacen.py`

**Interfaces:**
- Usa: `domingo.reglas.estado_inicial`.
- Produce (todo bajo `resultados/domingo/AAAA-MM-DD/`, ya ignorado por git):
  - `carpeta(domingo: date, raiz=RAIZ/"resultados"/"domingo") -> Path`
  - `guardar_aprobacion(domingo, viajes: list[dict], archivo_excel: bytes, quien: str, ahora: datetime, raiz=...) -> None`:
    escribe `viajes.xlsx` y `aprobacion.json` (`quien`, `cuando`, `viajes`). Reemplaza la anterior.
  - `leer_aprobacion(domingo, raiz=...) -> dict | None`
  - `cargar_estados(domingo, raiz=...) -> dict[str, dict]` (llave `viaje`; viajes sin estado toman `estado_inicial()`
    al leerse junto con la aprobación) y `guardar_estados(domingo, estados, raiz=...) -> None`
  - `detener(domingo, quien, ahora, raiz=...) -> None`, `detenido(domingo, raiz=...) -> dict | None`
  - `marcar_hecho(domingo, clave: str, ahora, raiz=...) -> None` y `ya_hecho(domingo, clave, raiz=...) -> bool`, para
    los envíos de una sola vez (`"sin_lista"`, `"correo_1300"`, `"correo_1930"`, `"resumen"`, `"aviso_fallas"`).
  - `candado(raiz=...)`: administrador de contexto con un archivo de candado creado con `os.O_CREAT | os.O_EXCL`; si ya
    existe y tiene menos de 2 horas, lanza `CandadoOcupado`; si es más viejo, lo reemplaza.
  - Toda escritura es atómica (archivo temporal en la misma carpeta y `os.replace`); fechas en ISO 8601 con zona.

- [ ] **Paso 1: Escribe las pruebas que fallan** (con `tmp_path` como `raiz`).
  - `test_aprobacion_ida_y_vuelta` y `test_nueva_aprobacion_reemplaza`.
  - `test_estados_ida_y_vuelta_con_fechas_con_zona`.
  - `test_escritura_atomica`: si la serialización falla, el archivo anterior queda intacto.
  - `test_detener_y_detenido`.
  - `test_marcar_hecho_una_vez`.
  - `test_candado`: un segundo `candado()` dentro del primero lanza `CandadoOcupado`; un archivo de candado de hace 3 horas
    se reemplaza.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa `domingo/almacen.py`.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit y push: `Domingo: aprobación y estado guardados`.

### Task 5: Llamadas por Twilio y lectura del resultado

**Archivos:**
- Crear: `domingo/telefonia.py`, `herramientas/registrar_numero.py`
- Modificar: `.env.example` (`ELEVENLABS_PHONE_NUMBER_ID=`), `verificar_conexion.py` (revisa que el número esté
  registrado en ElevenLabs, solo lectura)
- Prueba: `tests/test_domingo_telefonia.py`

**Interfaces:**
- Usa: `lib.seguridad.cargar_env`, `lib.seguridad.enmascarar`.
- Produce:
  - `class ErrorTelefonia(Exception)` (mensaje sin keys ni SIDs).
  - `llamar(viaje: dict, variables: dict, env: dict, http=requests) -> str`: `POST /v1/convai/twilio/outbound-call` con
    `agent_id` = `ELEVENLABS_AGENT_ID_SEGUIMIENTO`, `agent_phone_number_id` = `ELEVENLABS_PHONE_NUMBER_ID`, `to_number`
    y `conversation_initiation_client_data.dynamic_variables`; regresa el `conversation_id` o lanza `ErrorTelefonia`.
  - `esperar_resultado(conversation_id, env, http=requests, dormir=time.sleep, max_seg=600) -> dict`: consulta
    `GET /v1/convai/conversations/{id}` cada 10 s hasta `done` o `failed`; regresa los 7 campos de extracción (vacíos si
    falló o no hubo análisis) más `duracion_seg` y `estado_conversacion`; si se agota el tiempo, lanza `ErrorTelefonia`.
  - `registrar_numero.py`: registra el número de Twilio del `.env` en ElevenLabs (`POST /v1/convai/phone-numbers`, con
    confirmación `SI`) y guarda el `phone_number_id` en `.env`, como `subir_agente.py` guarda el ID del agente.

- [ ] **Paso 1: Escribe las pruebas que fallan** con un `http` falso (sin red).
  - `test_llamar_arma_la_peticion`: URL, encabezado `xi-api-key` y cuerpo exactos; regresa el `conversation_id`.
  - `test_llamar_error_http`: HTTP 400/402/500 lanza `ErrorTelefonia` cuyo mensaje trae el código y no trae la key.
  - `test_llamar_sin_red`: `requests.ConnectionError` lanza `ErrorTelefonia`.
  - `test_esperar_resultado_hasta_done`: dos respuestas `in-progress` y luego `done` con `data_collection_results`;
    regresa los campos y `dormir` se llamó dos veces con 10.
  - `test_esperar_resultado_failed`: `failed` regresa `hablo_con_operador` falso.
  - `test_esperar_resultado_tiempo_agotado`.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa. Antes de escribir `registrar_numero.py`, confirma en la documentación vigente de
  ElevenLabs el cuerpo de `POST /v1/convai/phone-numbers` para Twilio y anota la URL en un comentario.
- [ ] **Paso 4:** Las pruebas deben PASAR y todo `pytest -q` verde.
- [ ] **Paso 5:** Commit y push: `Domingo: llamadas por Twilio y lectura del resultado`.

### Task 6: Avisos por correo y Excel del resumen

**Archivos:**
- Crear: `domingo/avisos.py`
- Modificar: `.env.example` (`SMTP_HOST=smtp.gmail.com`, `SMTP_PUERTO=587`, `SMTP_USUARIO=`, `SMTP_PASSWORD=`,
  `CORREO_CONTROL=`)
- Prueba: `tests/test_domingo_avisos.py`

**Interfaces:**
- Usa: `lib.seguridad.cargar_env`, `lib.seguridad.enmascarar`.
- Produce:
  - `class Aviso` (dataclass): `para: list[str]`, `copia: list[str]`, `asunto: str`, `cuerpo: str`,
    `adjunto: Path | None`.
  - `enviar(aviso: Aviso, env: dict, canal: str = "correo", smtp=smtplib.SMTP) -> bool`: único punto de envío; hoy solo
    canal `"correo"` (STARTTLS, 587); otro canal lanza `NotImplementedError`. Regresa False (sin traza) si falta
    configuración o falla el envío.
  - Constructores, cada uno regresa `list[Aviso]`:
    - `avisos_de_casos(viajes, estados, correo_control) -> list[Aviso]`: uno por `correo_monitoreo` con sus viajes en
      `aviso_pendiente`, copia a `correo_control`; cada caso con viaje, línea, operador y teléfono, cliente, cita, lo que
      dijo (`hora_estimada_dicha`, `motivo`), llamadas hechas y conversación.
    - `aviso_de_control(domingo, momento: str, viajes, estados, correo_control, fallas: list[str])` (siempre se arma,
      aunque no haya casos).
    - `aviso_de_aprobacion(domingo, aprobacion, correo_control)`, `aviso_sin_lista(domingo, correo_control)`,
      `aviso_detenido(domingo, quien, cuando, correo_control)`, `aviso_fallas_api(domingo, fallas, correo_control)`.
    - `avisos_de_resumen(domingo, viajes, estados, correo_control, ruta_excel: Path)`: uno por persona de monitoreo con
      sus viajes y uno a `correo_control` con todos y el Excel adjunto.
  - `escribir_excel_resumen(viajes, estados, ruta) -> Path`, hojas "Viajes" (una fila por viaje con estado final) e
    "Historial" (una fila por llamada).

- [ ] **Paso 1: Escribe las pruebas que fallan** con un SMTP falso.
  - `test_avisos_de_casos_por_persona`: 3 casos de dos personas de monitoreo dan 2 avisos, cada uno solo con los suyos y
    copia a control; un viaje a_tiempo no aparece.
  - `test_aviso_de_control_sin_casos`: sin casos, igual hay aviso con los conteos «llamadas», «a tiempo», «monitoreo» y
    «pendientes».
  - `test_resumen_y_excel`: el Excel tiene las dos hojas y una fila por viaje; el aviso a control lo adjunta.
  - `test_enviar_ok`, `test_enviar_falla_sin_traza` (`OSError` → False), `test_enviar_sin_config` (no conecta),
    `test_canal_no_implementado`.
  - `test_ninguna_key_en_el_cuerpo`: con `SMTP_PASSWORD` en `env`, no aparece en ningún aviso ni en lo impreso.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa con `email.message.EmailMessage` y `openpyxl`.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit y push: `Domingo: avisos por correo y resumen en Excel`.

### Task 7: El latido

**Archivos:**
- Crear: `domingo/latido.py`
- Prueba: `tests/test_domingo_latido.py`

**Interfaces:**
- Usa: todo lo producido por las Tareas 1 a 6.
- Produce: `ejecutar_latido(ahora, cal, env, raiz, llamar, esperar_resultado, enviar) -> list[str]` (bitácora de lo que
  hizo) y `main()` para `.venv\Scripts\python -m domingo.latido` (sin argumentos; conecta las funciones reales y escribe
  la bitácora en `resultados/domingo/latido.log`).

  En cada latido, dentro de `almacen.candado()` (si está ocupado, termina sin hacer nada), en este orden:
  1. Domingo en curso con `calendario.domingo_de(ahora)`; si no hay, termina.
  2. Domingo ≥ 12:00 sin aprobación y sin `sin_lista` hecho → `aviso_sin_lista`, marca `sin_lista`.
  3. Resuelve los viajes `en_curso` (latido anterior interrumpido) con `esperar_resultado` de su conversación.
  4. Mientras haya viajes a los que `toca_llamar`, no esté `detenido`, no se pase el tope del domingo y no haya 3 fallas de
     API seguidas: revisa la lista blanca si es ensayo, guarda `en_curso` con la conversación **antes** de esperar, llama,
     espera, `decidir`, `aplicar` y guarda el estado. Una `ErrorTelefonia` cuenta como intento sin respuesta y suma a las
     fallas seguidas.
  5. Con 3 fallas de API seguidas → `aviso_fallas_api` una sola vez y no llama más ese latido.
  6. Si la ronda de las 13:00 ya no tiene a nadie por llamar y no está `correo_1300` → avisos de casos y de control,
     limpia `aviso_pendiente` solo de los que se enviaron bien, marca `correo_1300`. Igual con la de las 19:30
     (`correo_1930`), contando ahí como monitoreo a los que agotaron sus 3 llamadas. Un aviso de caso que falla queda
     pendiente para el siguiente envío.
  7. Lunes ≥ 7:00 sin `resumen` → Excel y avisos de resumen, marca `resumen`.

- [ ] **Paso 1: Escribe las pruebas que fallan** con reloj fijo, `tmp_path` y funciones falsas.
  - `test_fuera_de_domingo_no_hace_nada`.
  - `test_sin_lista_avisa_una_vez`: dos latidos a las 12:05 mandan un solo aviso.
  - `test_ronda_1300_llama_a_todos_y_manda_correos`: 3 viajes (a tiempo, tarde, no contesta) → 3 llamadas; un aviso a la
    persona de monitoreo del tarde y uno de control; estados a_tiempo, monitoreo, sin_respuesta.
  - `test_segundo_latido_no_vuelve_a_llamar`: otro latido a las 13:30 no llama a nadie.
  - `test_reintentos_1900_y_1930`: el que no contesta se llama a las 19:00 y 19:30 y queda en monitoreo con aviso en
    `correo_1930`.
  - `test_detenido_no_llama`: con `detener` hecho antes, no hay llamadas.
  - `test_en_curso_se_resuelve`: un viaje `en_curso` con conversación se resuelve sin volver a marcar.
  - `test_candado_ocupado_no_hace_nada`.
  - `test_tres_fallas_api_suspenden`: `llamar` que siempre lanza `ErrorTelefonia` → 3 intentos, 1 aviso de fallas, ninguna
    llamada más en ese latido.
  - `test_aviso_que_falla_queda_pendiente`: `enviar` que regresa False deja `aviso_pendiente=True`.
  - `test_lista_blanca_en_ensayo`: un viaje cuyo teléfono se quitó de la lista blanca después de aprobar no se llama y
    aparece en el correo de control como falla.
  - `test_resumen_lunes_una_vez`.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa `ejecutar_latido` y `main()`.
- [ ] **Paso 4:** Las pruebas deben PASAR y todo `pytest -q` verde.
- [ ] **Paso 5:** Commit y push: `Domingo: latido que llama, reintenta y avisa`.

### Task 8: La página web

**Archivos:**
- Crear: `domingo/pagina.py`, `domingo/plantillas_html/` (base, entrar, subir, revisar, estado), `domingo/servir.py`
- Modificar: `requirements.txt` (`flask>=3.0`, `waitress>=3.0`), `.env.example` (`PAGINA_PASSWORD=`, `PAGINA_SECRETO=`)
- Prueba: `tests/test_domingo_pagina.py`

**Interfaces:**
- Usa: `domingo.viajes.validar_viajes`, `domingo.calendario`, `domingo.almacen`, `domingo.avisos`.
- Produce: `crear_app(raiz, env, cal, reloj=lambda: datetime.now(ZONA_CDMX), enviar=avisos.enviar) -> Flask` y
  `servir.py`, que la sirve con waitress en `127.0.0.1:8080`.
  - `GET/POST /entrar`: una contraseña (`PAGINA_PASSWORD`, comparada con `hmac.compare_digest`); tras 5 intentos fallidos
    desde la misma IP, 15 minutos sin dejar entrar.
  - `GET /`: domingo para aprobar, aprobación vigente (quién, cuándo, cuántas llamadas) y estado del domingo en curso por
    viaje (operador, teléfono con los últimos 4 dígitos, cita, estado, intentos), los avisos que quedaron pendientes por
    falla de envío y las fallas de llamada del día.
  - `POST /subir`: solo `.xlsx` de hasta 2 MB; guarda el archivo en una carpeta temporal y muestra errores y advertencias,
    o la lista de llamadas con el botón «Aprobar N llamadas» y un campo obligatorio de nombre.
  - `POST /aprobar`: vuelve a validar el mismo archivo con la hora actual; si sigue sin errores y
    `domingo_para_aprobar` no es `None`, `guardar_aprobacion` y `aviso_de_aprobacion`.
  - `POST /detener`: con nombre obligatorio, `almacen.detener` y `aviso_detenido`; disponible también después de las 12:00.
  - Todo POST lleva un token CSRF de la sesión; cookie de sesión `Secure`, `HttpOnly` y `SameSite=Lax`.

- [ ] **Paso 1: Escribe las pruebas que fallan** con `app.test_client()`, `tmp_path` y reloj fijo.
  - `test_sin_entrar_redirige`, `test_contrasena_mala`, `test_bloqueo_tras_5_intentos`.
  - `test_subir_con_errores_no_ofrece_aprobar`: con `viajes_con_errores.xlsx` la página muestra los errores y no el botón.
  - `test_subir_y_aprobar`: con `viajes_prueba.xlsx` aparece «Aprobar 5 llamadas»; al aprobar con nombre se guarda la
    aprobación y se envía un aviso a control.
  - `test_aprobar_sin_nombre_falla`.
  - `test_no_aprueba_domingo_despues_de_las_12`.
  - `test_aprobar_revalida`: entre subir y aprobar pasa la hora de una cita; aprobar falla con «ya pasó».
  - `test_detener`: queda detenido y se avisa a control.
  - `test_csrf`: un POST sin token da 400.
  - `test_telefono_enmascarado`: la página nunca muestra un teléfono completo de operador.
  - `test_archivo_que_no_es_xlsx`.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa. HTML simple y legible en el teléfono, sin JavaScript obligatorio.
- [ ] **Paso 4:** Las pruebas deben PASAR y todo `pytest -q` verde.
- [ ] **Paso 5:** Commit y push: `Domingo: página para subir, aprobar y detener`.

### Task 9: Servidor de prueba en Lightsail y ensayo

**Archivos:**
- Crear: `docs/guia-servidor-domingo.md`, `despliegue/Caddyfile`, `despliegue/bot-domingo-pagina.service`,
  `despliegue/crontab.txt`, `despliegue/instalar.sh`
- Modificar: `README.md` (sección del seguimiento de domingo y tabla de scripts), `PROGRESO.md`

**Interfaces:**
- Usa: `domingo.servir`, `domingo.latido`, `verificar_conexion.py`, `herramientas/registrar_numero.py`,
  `agente/subir_agente.py --agente seguimiento`.

- [ ] **Paso 1:** Escribe `docs/guia-servidor-domingo.md`, paso a paso para Roberto, sin dar nada por sabido:
  - crear en su cuenta de AWS una instancia Lightsail **nueva** (Ubuntu 24.04, el plan más pequeño), separada de
    `srm-piloto`;
  - IP estática y puertos 80 y 443 abiertos;
  - entrar con *Connect using SSH* del navegador;
  - llave de despliegue de solo lectura en GitHub y clonar el repositorio;
  - correr `despliegue/instalar.sh` (Python, `.venv`, dependencias, Caddy con dominio `sslip.io`, servicio de la página y
    `crontab` con el latido cada 5 minutos y `TZ` irrelevante porque el código usa CDMX);
  - llenar el `.env` a mano en el servidor, incluida la contraseña de aplicación del Gmail del bot;
  - `verificar_conexion.py`.

  Lo que hace Roberto fuera del servidor también queda en la guía: upgrade de Twilio (recarga automática apagada) y
  número de EE. UU.; `registrar_numero.py`; crear el Gmail del bot con verificación en dos pasos y contraseña de
  aplicación; iniciar el trámite del número mexicano.
- [ ] **Paso 2:** Prueba en seco en el servidor (sin llamar): con `"ensayo": true` y `datos/viajes_prueba.xlsx`, subir y
  aprobar desde la página; correr `python -m domingo.latido` a mano un día que no es domingo y confirmar que no hace nada;
  confirmar que llega el correo de aprobación.
- [ ] **Paso 3:** Ensayo real un domingo (gasta créditos y saldo; Roberto aprueba la lista en la página): 4 o 5 celulares
  del equipo simulan los casos del diseño 5.8 (a tiempo, tarde, vago, no contesta, contesta otra persona). Revisa:
  - estados finales;
  - un correo por persona de monitoreo solo con sus casos;
  - correo de control a las 13:00 y a las 19:30;
  - reintentos a las 19:00 y 19:30;
  - resumen del lunes a las 7:00 con el Excel.
- [ ] **Paso 4:** Anota en `PROGRESO.md` IDs de conversación, duraciones, costo real por llamada y lo que haya que
  ajustar; actualiza `README.md`.
- [ ] **Paso 5:** Commit y push: `Domingo: servidor de prueba y ensayo`.
