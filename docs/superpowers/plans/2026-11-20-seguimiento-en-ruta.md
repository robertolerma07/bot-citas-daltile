# Seguimiento en ruta por voz — Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usa superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan casillas (`- [ ]`) para el seguimiento.

**Meta:** Un bot que, dos veces al día (9:00 y 18:00), llama a los operadores en ruta con una llamada de 20 a 30 segundos. Registra a los que llegan dentro de la ventana de descarga, pasa a una persona los que no, y avisa al equipo de tráfico por correo con un Excel.

**Arquitectura:** Es un segundo agente de ElevenLabs ("Sofía - seguimiento"), versionado como código igual que el de la prueba de concepto. Un comando `seguimiento.ronda` hace lo siguiente:
- lee los viajes de un CSV;
- decide con reglas puras (sin red) a quién toca llamar;
- llama con la integración nativa de Twilio de la Fase 4;
- guarda el estado de cada viaje en un JSON;
- escribe un Excel y manda un correo solo con los casos nuevos que pasan a una persona.

**Tecnología:** Python 3.12, `requests`, `twilio`, `python-dotenv`, `openpyxl`, `pytest`, y `smtplib` de la biblioteca estándar. Las APIs de ElevenLabs que se usan son las ya confirmadas en la prueba de concepto.

**Diseño:** `docs/superpowers/specs/2026-11-20-seguimiento-en-ruta-design.md`. Léelo junto con este plan.

**Cuándo:** se construye **después** de cerrar las Fases 3 a 6 de la prueba de concepto. Reutiliza lo que esas fases dejan.

## Restricciones globales
- Rondas a las **9:00** y a las **18:00**, hora America/Mexico_City. Las llamadas solo se hacen entre **9:00 y 20:00**, salvo con `--forzar` (`lib.seguridad.verificar_horario`).
- No contesta: **máximo 3 intentos por ronda**, con **al menos 30 minutos** entre intentos. Después del tercero, el caso **pasa a una persona**.
- Regla de la ventana:
  - si dice que llega **el día de la cita** a una hora **menor o igual al fin de la ventana**, se registra;
  - en cualquier otro caso (después del fin, otro día o sin hora clara) **pasa a una persona**.
- Si en la ronda de las 18:00 se registra, **ya no se llama más** en ese viaje. Si pasa a una persona, el bot **no vuelve a llamar** en ese viaje.
- No hay llamadas **después del día de la cita**.
- Si contesta otra persona, cuenta como intento sin respuesta. No se acepta la respuesta de un tercero.
- La hora estimada se guarda **tal como la dijo**. El formato HH:MM se llena solo si la dijo clara y **nunca se inventa**.
- Candados de la prueba que siguen igual:
  - lista blanca (`config/numeros_permitidos.txt`);
  - confirmación con `SI` antes de llamar (`lib.seguridad.confirmar_gasto`);
  - keys solo en `.env`;
  - nunca imprimir una key completa.
- La ronda **se corre a mano** (pide confirmación). Automatizarla con el Programador de tareas queda fuera de este plan.
- Código y comentarios en español, en el estilo de los scripts actuales.

## Enfoque de revisión
1. **Correr la misma ronda dos veces:** no debe volver a llamar a quien ya contestó en esa ronda ni a un caso ya cerrado o pasado a una persona. (Tarea 3)
2. **Hora estimada exactamente igual al fin de la ventana:** se registra, porque es "menor o igual". Una hora que no es HH:MM válida (vacía, "25:00", "8:5") pasa a una persona. (Tarea 3)
3. **Viaje con fecha de cita pasada:** no se llama, aunque nunca se haya cerrado. (Tarea 3)
4. **Falla el correo (SMTP caído o mal configurado):** el Excel se escribe igual, los casos quedan marcados `correo_pendiente` y se reenvían en la siguiente ronda; el script termina con aviso, no con traza. (Tarea 5 y Tarea 6)
5. **Un viaje con teléfono fuera de la lista blanca o con ventana inválida:** la ronda se detiene antes de llamar a nadie. (Tarea 1 y Tarea 6)

---

### Tarea 1: Datos de viajes y su validación

**Archivos:**
- Crear: `seguimiento/__init__.py`, `seguimiento/viajes.py`, `datos/viajes_prueba.csv`, `datos/viajes_con_errores.csv`
- Prueba: `tests/test_seguimiento_viajes.py`

**Interfaces:**
- Usa: `validar_citas.revisar_telefono(valor, campo)`, `validar_citas.leer_citas(ruta)` (lector CSV con BOM y detección de columnas repetidas), `lib.seguridad.cargar_lista_blanca`, `lib.formato_voz.fecha_texto`, `lib.formato_voz.hora_texto`, `lib.formato_voz.telefono_pares`.
- Produce:
  - `COLUMNAS_VIAJE = ["id_viaje", "linea", "operador", "telefono", "destino", "fecha_cita", "ventana_inicio", "ventana_fin", "tel_trafico"]`
  - `validar_viajes(ruta_csv, ruta_lista, hoy) -> tuple[list[str], list[dict]]`, que regresa (errores, viajes)
  - `variables_de_voz_viaje(viaje: dict) -> dict`, con estas claves:
    - `operador`, `linea`, `destino`;
    - `fecha_cita_texto`;
    - `ventana_inicio_texto` y `ventana_fin_texto`, con `hora_texto` sin la "a " inicial;
    - `tel_trafico_texto`.

- [ ] **Paso 1: Escribe las pruebas que fallan**
  - `test_viajes_prueba_pasan`: `datos/viajes_prueba.csv` contra `datos/numeros_demo.txt` da 0 errores y 3 viajes.
  - `test_viajes_con_errores_fallan`: `datos/viajes_con_errores.csv` da errores que contienen «ventana_fin», «ventana_inicio», «lista blanca» e «id_viaje repetido».
  - `test_ventana_fin_debe_ser_mayor_que_inicio`: con `ventana_inicio=14:00` y `ventana_fin=08:00` hay un error que contiene «ventana».
  - `test_variables_de_voz_viaje`: para `fecha_cita=2026-12-01`, `ventana_inicio=08:00` y `ventana_fin=14:00`, se cumple:
    - `fecha_cita_texto == "el martes primero de diciembre"`;
    - `ventana_inicio_texto == "las ocho de la mañana"`;
    - `ventana_fin_texto == "las dos de la tarde"`.

- [ ] **Paso 2:** `.venv\Scripts\python -m pytest tests/test_seguimiento_viajes.py -q` debe FALLAR (módulo inexistente).
- [ ] **Paso 3:** Crea los dos CSV.
  - `viajes_prueba.csv`: 3 viajes ficticios con los teléfonos de `datos/numeros_demo.txt` y fechas futuras.
  - `viajes_con_errores.csv`: un error por fila, igual que `citas_con_errores.csv`.

  Implementa `validar_viajes` y `variables_de_voz_viaje`, reutilizando las funciones de la lista "Usa". Las horas deben ser HH:MM válidas y el fin debe ser mayor que el inicio.
- [ ] **Paso 4:** La misma corrida debe PASAR, y todo `pytest -q` debe seguir verde.
- [ ] **Paso 5:** Commit: `Seguimiento: datos de viajes y validación`.

### Tarea 2: Agente "Sofía - seguimiento" como código

**Archivos:**
- Crear: `agente_seguimiento/prompt.md`, `agente_seguimiento/config.json`
- Modificar: `agente/subir_agente.py`
- Prueba: `tests/test_seguimiento_agente.py`

**Interfaces:**
- Usa: `seguimiento.viajes.variables_de_voz_viaje`.
- Produce:
  - `subir_agente.py --agente seguimiento`: usa la carpeta `agente_seguimiento/`, guarda el ID en `ELEVENLABS_AGENT_ID_SEGUIMIENTO` y toma las variables de ejemplo del primer viaje de `datos/viajes_prueba.csv`. Sin `--agente` todo sigue igual que hoy.
  - Campos de extracción que leen las tareas 3 y 6:
    - `hablo_con_operador` (boolean);
    - `llega_el_dia_de_la_cita` (boolean);
    - `hora_estimada_texto` (string);
    - `hora_estimada_hhmm` (string HH:MM, 24 horas, o vacío);
    - `motivo` (string).

- [ ] **Paso 1: Escribe las pruebas que fallan** (sin red)
  - `test_prompt_usa_solo_variables_con_ejemplo`: toda `{{var}}` de `agente_seguimiento/prompt.md` y de su `primer_mensaje` existe en `variables_de_voz_viaje(primer viaje)` más `saludo`.
  - `test_config_extraccion`: las claves de `extraccion_de_datos` son exactamente los 5 campos de arriba.
  - `test_armar_cuerpo_seguimiento`: `armar_cuerpo` con la config de seguimiento trae `conversation.max_duration_seconds == 60` y la misma `tts.voice_id` que `agente/config.json`.

- [ ] **Paso 2:** La corrida debe FALLAR.
- [ ] **Paso 3:** Escribe el prompt y la config.
  - **Prompt**, según la sección 5.2 del diseño:
    - saludo con identidad automática y aviso de grabación;
    - confirmar que habla con `{{operador}}`;
    - "¿Va en tiempo para su descarga {{fecha_cita_texto}}, entre {{ventana_inicio_texto}} y {{ventana_fin_texto}}?";
    - "¿A qué hora calcula llegar?";
    - el motivo, solo si va retrasado;
    - cierre con `{{tel_trafico_texto}}` y colgar.
  - **Reglas heredadas del prompt actual:** no inventar, no prometer, no reprogramar, aceptar interrupciones, no preguntar "¿algo más?".
  - **Config:** igual a `agente/config.json` en voz, LLM, DTMF y privacidad, con `max_duration_seconds: 60`.
  - **Descripciones de extracción:**
    - `hora_estimada_hhmm` se llena solo si la hora fue clara e incluye mañana o tarde, o se puede deducir sin duda; si no, queda vacío.
    - `llega_el_dia_de_la_cita` es true solo si dijo que llega el mismo día de la descarga.

  Generaliza `subir_agente.py` con `--agente {aviso,seguimiento}` (por defecto `aviso`).
- [ ] **Paso 4:** Las pruebas deben PASAR, y todo `pytest -q` debe seguir verde. Corre `.venv\Scripts\python agente\subir_agente.py --agente seguimiento`: crea el agente y las 11 secciones deben salir con ✅.
- [ ] **Paso 5:** Commit: `Seguimiento: agente Sofía - seguimiento como código`.

### Tarea 3: Reglas de la ronda (lógica pura)

**Archivos:**
- Crear: `seguimiento/reglas.py`
- Prueba: `tests/test_seguimiento_reglas.py`

**Interfaces:**
- Produce:
  - `ETAPAS = ("manana", "tarde", "cerrado", "humano")`
  - `estado_inicial() -> dict`, que regresa `{"etapa": "manana", "intentos": 0, "ultimo_intento": None, "historial": [], "correo_pendiente": False}`
  - `toca_llamar(viaje: dict, estado: dict, momento: str, ahora: datetime) -> bool`, donde `momento` es `"manana"` o `"tarde"`
  - `decidir(viaje: dict, resultado: dict) -> str`, que regresa `"registrar"`, `"humano"` o `"sin_respuesta"`; `resultado` trae los 5 campos de extracción
  - `aplicar(viaje: dict, estado: dict, momento: str, decision: str, resultado: dict, ahora: datetime) -> dict`, que regresa el estado nuevo, sin modificar el anterior

- [ ] **Paso 1: Escribe las pruebas que fallan.** Usa un viaje con `fecha_cita=2026-12-01`, `ventana_fin=14:00` y `ahora=2026-11-30 09:00 CDMX`.
  - `toca_llamar`:
    - `test_manana_toca_en_etapa_manana`: True.
    - `test_tarde_no_toca_si_etapa_es_manana`: con momento "tarde" y etapa "manana" da False. La ronda de la tarde solo llama a quien la de las 9:00 dejó en etapa "tarde".
    - `test_no_toca_si_cerrado_o_humano`: False para etapa "cerrado" y para "humano".
    - `test_reintento_espera_30_minutos`: con intentos=1 y último intento hace 29 minutos da False; hace 30 minutos da True.
    - `test_maximo_3_intentos`: intentos=3 da False.
    - `test_no_toca_despues_del_dia_de_la_cita`: con `ahora=2026-12-02 09:00` da False.
  - `decidir`:
    - `test_decidir`:
      - `hablo_con_operador=False` → "sin_respuesta";
      - mismo día y "13:30" → "registrar";
      - mismo día y "14:00" → "registrar" (igual al fin);
      - mismo día y "14:01" → "humano";
      - `llega_el_dia_de_la_cita=False` → "humano";
      - "" → "humano";
      - "25:00" → "humano";
      - "8:5" → "humano".
  - `aplicar`:
    - `test_aplicar_manana_registrar_pasa_a_tarde`: la etapa pasa a "tarde" e intentos a 0.
    - `test_aplicar_tarde_registrar_cierra`: la etapa pasa a "cerrado".
    - `test_aplicar_humano`: la etapa pasa a "humano" y `correo_pendiente` a True.
    - `test_tercer_sin_respuesta_pasa_a_humano`: con intentos=2, "sin_respuesta" deja etapa "humano" y `correo_pendiente` True.
    - `test_sin_respuesta_cuenta_intento`: con intentos=0 deja intentos=1 y `ultimo_intento=ahora`.
    - `test_historial_guarda_resultado`: el historial gana una entrada con fecha, momento, decisión y los 5 campos.
    - `test_misma_ronda_dos_veces_no_vuelve_a_llamar`: después de `aplicar(..."registrar"...)` en la mañana, `toca_llamar(..., "manana", ...)` da False.

- [ ] **Paso 2:** La corrida debe FALLAR.
- [ ] **Paso 3:** Implementa las 4 funciones en `seguimiento/reglas.py`, sin E/S ni red.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit: `Seguimiento: reglas de la ronda`.

### Tarea 4: Estado persistente

**Archivos:**
- Crear: `seguimiento/estado.py`
- Prueba: `tests/test_seguimiento_estado.py`

**Interfaces:**
- Usa: `seguimiento.reglas.estado_inicial`.
- Produce:
  - `RUTA_ESTADO = RAIZ / "resultados" / "seguimiento_estado.json"`
  - `cargar_estado(ruta=RUTA_ESTADO) -> dict[str, dict]`, con llave `id_viaje`; los viajes nuevos toman `estado_inicial()`
  - `guardar_estado(estados, ruta=RUTA_ESTADO) -> None`, con escritura atómica: archivo temporal más `os.replace`

- [ ] **Paso 1: Escribe las pruebas que fallan.**
  - `test_archivo_inexistente_da_dict_vacio`.
  - `test_guardar_y_cargar_ida_y_vuelta`: incluye un `datetime` con zona horaria en `ultimo_intento`.
  - `test_guardar_no_deja_archivo_a_medias`: si `json.dump` falla, el archivo anterior queda intacto.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa. Las fechas se guardan en ISO 8601. `resultados/` ya está en `.gitignore`.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit: `Seguimiento: estado de viajes en JSON`.

### Tarea 5: Excel y correo al equipo

**Archivos:**
- Crear: `seguimiento/reporte.py`
- Modificar: `.env.example`, al que se agregan `SMTP_HOST=`, `SMTP_PUERTO=587`, `SMTP_USUARIO=`, `SMTP_PASSWORD=` y `CORREO_TRAFICO=`
- Prueba: `tests/test_seguimiento_reporte.py`

**Interfaces:**
- Usa: `lib.seguridad.cargar_env`.
- Produce:
  - `escribir_excel(viajes, estados, ruta) -> Path`, con dos hojas:
    - "Viajes": id_viaje, linea, operador, destino, fecha_cita, ventana, etapa, última decisión, hora estimada (texto), motivo, intentos;
    - "Historial": una fila por llamada.
  - `casos_para_correo(viajes, estados) -> list[dict]`, con los viajes que tienen `correo_pendiente`.
  - `enviar_correo(casos, valores_env, enviar=smtplib.SMTP) -> bool`, que regresa True si se envió. El parámetro `enviar` permite probar sin red.

- [ ] **Paso 1: Escribe las pruebas que fallan.**
  - `test_excel_tiene_dos_hojas_y_una_fila_por_viaje`.
  - `test_casos_para_correo_solo_pendientes`.
  - `test_enviar_correo_arma_mensaje`: con un SMTP falso, el asunto contiene «Seguimiento» y el número de casos, y el cuerpo trae operador, destino, hora estimada y motivo de cada caso.
  - `test_enviar_correo_falla_sin_traza`: si el SMTP falso lanza `OSError`, regresa False.
  - `test_sin_config_smtp_regresa_false`: si faltan variables, regresa False con un aviso y nunca intenta conectar.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa con `openpyxl`, `smtplib` y `email.message.EmailMessage`, con STARTTLS en el puerto 587. Nunca imprimas `SMTP_PASSWORD`.
- [ ] **Paso 4:** Las pruebas deben PASAR.
- [ ] **Paso 5:** Commit: `Seguimiento: Excel y correo al equipo`.

### Tarea 6: Comando de la ronda

**Archivos:**
- Crear: `seguimiento/ronda.py`
- Modificar: `README.md` (tabla de scripts y sección de seguimiento) y `PROGRESO.md`
- Prueba: `tests/test_seguimiento_ronda.py`

**Interfaces:**
- Usa:
  - `seguimiento.viajes.validar_viajes` y `variables_de_voz_viaje`;
  - `seguimiento.reglas` (todas);
  - `seguimiento.estado`;
  - `seguimiento.reporte`;
  - `lib.seguridad`: `verificar_lista_blanca`, `verificar_horario`, `confirmar_gasto` y `cargar_env`;
  - de la Fase 4: la función que hace una llamada saliente con `POST /v1/convai/twilio/outbound-call` y regresa el `conversation_id`;
  - de la Fase 5: la que trae una conversación terminada con sus `data_collection_results`. Si sus nombres difieren, usa los que existan.
- Produce: `.venv\Scripts\python -m seguimiento.ronda --momento {manana,tarde} [--viajes datos/viajes_prueba.csv] [--forzar]`

- [ ] **Paso 1: Escribe las pruebas que fallan.** Inyecta funciones falsas de llamar y de traer conversación, con un reloj fijo y sin red.
  - `test_ronda_detiene_si_hay_errores_en_viajes`: termina con código 1 y no llama a nadie.
  - `test_ronda_llama_solo_a_quien_toca_y_guarda_estado`.
  - `test_ronda_reintenta_hasta_3_veces_con_espera`: la función de espera falsa recibe 30 minutos entre intentos, y después del tercero el viaje queda en "humano".
  - `test_ronda_escribe_excel_y_marca_correo_enviado`: tras enviar, `correo_pendiente` queda en False.
  - `test_ronda_conserva_correo_pendiente_si_falla_el_envio`.
- [ ] **Paso 2:** Las pruebas deben FALLAR.
- [ ] **Paso 3:** Implementa `ejecutar_ronda(momento, ruta_viajes, ahora, llamar, traer_conversacion, esperar, entrada=input) -> int` y un `main()` que conecte las funciones reales. Orden:
  1. validar;
  2. lista blanca de todos los teléfonos a llamar;
  3. horario;
  4. `confirmar_gasto` con la lista;
  5. llamar a cada viaje que toca;
  6. esperar el análisis de cada conversación;
  7. `decidir` y `aplicar`, guardando el estado después de cada viaje;
  8. esperar 30 minutos y reintentar a quien quedó "sin_respuesta" con menos de 3 intentos (con nueva confirmación);
  9. Excel en `resultados/seguimiento_AAAA-MM-DD_<momento>.xlsx`;
  10. correo.
- [ ] **Paso 4:** Las pruebas deben PASAR y todo `pytest -q` debe seguir verde.
- [ ] **Paso 5:** Prueba real con el equipo:
  - una ronda `--momento manana` con los 3 viajes de prueba apuntando a celulares del equipo que estén en la lista blanca;
  - uno contesta "voy en tiempo", otro "llego mañana" y el tercero no contesta.

  Debe pasar esto:
  - el estado queda en tarde, humano y, tras los 3 intentos, humano;
  - el Excel trae los 3 viajes;
  - llega un correo con 2 casos.

  Anota en `PROGRESO.md` los IDs de conversación, las duraciones y el costo.
- [ ] **Paso 6:** Commit: `Seguimiento: comando de la ronda`.
