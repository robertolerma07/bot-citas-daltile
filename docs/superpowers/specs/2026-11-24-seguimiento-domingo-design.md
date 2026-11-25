# Diseño — Seguimiento de domingo por voz (MVP)

Fecha: 2026-11-24 · Autor: Roberto (decisiones) con Claude (redacción)

Este documento **reemplaza, para el MVP**, el horario y la forma de operar de
`2026-11-20-seguimiento-en-ruta-design.md` (llamadas a las 9:00 y 18:00 de lunes a viernes). De ese diseño se conservan
las reglas de la llamada corta, de no inventar datos y de pasar los retrasos a una persona. Donde los dos documentos
difieran, manda este.

## 1. Intención y porqué
En domingo no hay nadie en tráfico. Hoy, si una unidad que debe descargar el domingo en la tarde o el lunes temprano
viene retrasada, nadie se entera hasta que el equipo llega el lunes a las 7:30, y para entonces ya no hay margen para
avisar al cliente. Se quiere que **Sofía llame el domingo a los operadores de esos viajes**, registre a los que van
bien y **avise por correo a la persona de monitoreo de cada cliente** de los que no, para que actúe ese mismo día.

El MVP cubre **solo los domingos**. El diseño debe permitir agregar después el horario nocturno entre semana sin
rehacerlo (sección 5.9).

## 2. Objetivos, no objetivos y anti-objetivos
**Objetivos**
- Hablar el domingo con el operador de **cada viaje** de la lista aprobada y saber si llega a tiempo a su cita.
- Que la persona de monitoreo del cliente reciba por correo, el mismo domingo, los viajes que no llegan a tiempo, no
  saben o no contestaron.
- Que el equipo pueda preparar y aprobar la lista desde una página web, sin entrar al servidor.

**No objetivos (en esta versión)**
- Llamadas entre semana o de noche (queda preparado, no se construye).
- Avisar al cliente, reprogramar citas o negociar con el operador: lo hace la persona de monitoreo.
- Mensajes por WhatsApp o SMS (queda preparado, no se construye).
- Leer la programación de Daltile o el SRM: la lista viene de un Excel que arma el equipo.
- El agente de avisos de cita de la prueba de concepto no se toca.

**Anti-objetivos (aunque funcione, sería un fracaso si…)**
- Un viaje de la lista aprobada se queda sin llamar o sin resultado y nadie se entera.
- Un retraso real no le llega a la persona de monitoreo correcta.
- Sofía inventa o redondea una hora que el operador no dijo, o marca "a tiempo" algo vago.
- Se llama a un número que no venía en la lista aprobada, o se llama sin que nadie haya aprobado.
- El operador se distrae al manejar porque la llamada es larga o le pide anotar algo.

## 3. Restricciones
- Misma plataforma de la prueba de concepto: agente de ElevenLabs con la voz Diana y telefonía Twilio (integración
  nativa, `POST /v1/convai/twilio/outbound-call`). Python 3.12+, en este mismo repositorio.
- El operador contesta con manos libres o altavoz; no hay regla de colgar por ir manejando.
- Hora de referencia: `America/Mexico_City`.
- Keys y contraseñas solo en `.env` (nunca en git ni en pantalla completas).
- La prueba corre en un **servidor Lightsail nuevo, aparte del SRM** (`srm-piloto` no se toca). Lo crea Roberto desde su
  cuenta de AWS con instrucciones paso a paso. Después se moverá a un servidor virtual de la oficina, del que todavía no
  se conoce el sistema operativo: el código no debe depender de nada propio de AWS.
- Desde la red de la oficina no se puede entrar por SSH: todo lo que haga el equipo pasa por la página web.
- Para llamar a operadores reales hace falta antes: número mexicano en Twilio (trámite con documentos, se inicia ya),
  aviso de privacidad y aprobación de TI. Mientras tanto solo se llama a celulares del equipo.

## 4. Enfoques considerados
| Decisión | Opciones | Elegido |
|---|---|---|
| Qué horario cubre el bot | Solo after hours / día y noche | **Solo after hours**, y en el MVP **solo domingo** (Roberto) |
| Cómo se entera el equipo | Aviso inmediato a guardia / correo / los dos según urgencia | **Correo**, con lugar para mensaje después (Roberto) |
| Cómo llega la lista al servidor | Página web con contraseña / correo al bot / subir por terminal | **Página web con aprobación** (Roberto) |
| Dónde corre | Computadora de la oficina / servidor del SRM / Lightsail aparte / Campaigns de ElevenLabs solas | **Lightsail aparte** para la prueba, después servidor virtual de la oficina (Roberto) |
| Quién marca y decide | Campaigns de ElevenLabs / script propio | **Script propio** que llama uno por uno (Claude): las Campaigns no se repiten cada semana ni aplican reglas propias, y el script ya está planeado |
| Cómo llegan los resultados | Webhook de ElevenLabs / consultar la conversación | **Consultar** al terminar cada llamada (Claude): funciona igual detrás del firewall de la oficina |

## 5. Lo decidido

### 5.1 Calendario del domingo (Roberto)
```
Hasta 12:00  El equipo sube y aprueba el Excel en la página (la última aprobación manda)
12:00        Si no hay lista aprobada para hoy: no se llama y se avisa por correo a Roberto
13:00        Ronda única: se llama a TODOS los viajes aprobados
             └─ al terminar: correo a cada persona de monitoreo con sus casos nuevos
19:00        Reintento 1: solo a quien no contestó a las 13:00
19:30        Reintento 2: solo a quien tampoco contestó a las 19:00
             └─ al terminar: correo con los casos nuevos (incluye los que no contestaron 3 veces)
21:00        Ya no se hace ninguna llamada
Lunes 7:00   Resumen: a cada persona de monitoreo sus viajes; a Roberto, todos
```
- **Tope: 3 llamadas por viaje** en todo el domingo (13:00, 19:00, 19:30).
- Quien contestó y quedó "a tiempo" **ya no recibe otra llamada**. Quien pasa a monitoreo, tampoco.
- Si alguna llamada de la ronda de las 13:00 no alcanza a hacerse a las 13:00 (por ejemplo, muchas en fila), se hace
  en cuanto se pueda; lo importante es que se haga antes de las 19:00.

### 5.2 La lista de viajes (Excel)
Una fila por viaje. La arma el equipo antes de irse. Columnas (Roberto/Claude):

| Columna | Ejemplo | Nota |
|---|---|---|
| viaje | 104512 | Identificador único en el archivo |
| linea | Fletes Rápidos de Occidente | |
| operador | Miguel Ángel Torres | Sofía pide hablar con él |
| telefono | +525512345678 | `+52` y 10 dígitos |
| cliente | Cerámicas y Acabados Tapatíos | |
| destino | Zapopan, Jalisco | Cómo lo dice Sofía, sin abreviaturas |
| fecha_cita | 2026-11-30 | |
| tipo_cita | Hora / Día | |
| hora | 08:00 | En **Hora**: la hora fija de la cita. En **Día**: el límite; vacío = 16:00 (algunos clientes tienen otro límite y se escribe aquí) |
| correo_monitoreo | persona@daltile.com | Persona de monitoreo asignada al cliente |
| telefono_monitoreo | +528112345678 | WhatsApp de monitoreo que Sofía da al cerrar; `+52` y 10 dígitos. Si es uno solo para todos, se repite en cada fila (Claude) |

- **A todo viaje que venga en el Excel aprobado se le llama** (Roberto).
- El validador (igual de estricto que `validar_citas.py`) marca **errores** que impiden aprobar: columnas faltantes o
  repetidas, campos vacíos (salvo `hora` en Día), teléfono mal formado, fecha u hora inválidas, tipo de cita distinto
  de Hora/Día, correo mal formado, viaje repetido, **cita que ya pasó** al momento de aprobar, y —mientras dure el
  ensayo— teléfono fuera de la lista blanca.
- Marca **advertencias** que no impiden aprobar: cita fuera de domingo 13:00 – lunes 13:00 ("¿seguro?"), dirección o
  destino con abreviaturas, el mismo teléfono en dos viajes.
- **Zona horaria (Claude):** la fecha y la hora del Excel son las de la cita tal como vienen en la programación, en la
  hora local del destino; Sofía las dice así y compara contra ellas la hora que dé el operador. Las revisiones de
  "cita que ya pasó" y del rango de domingo a lunes usan la hora de CDMX; en destinos con otra zona pueden fallar por
  una o dos horas, lo que se acepta en el MVP.
- **Mismo operador en dos viajes (Claude):** se hace una llamada por viaje, una después de la otra con al menos 10
  minutos de separación, y cada una lleva su propio tope de 3 llamadas.

### 5.3 La página web
- Una página con HTTPS y **una sola contraseña** para el equipo (en `.env`).
- Pasos: subir el Excel → ver errores y advertencias, o la lista de llamadas que se harán (viaje, operador, teléfono
  enmascarado salvo los últimos 4 dígitos, cita, monitoreo) → escribir su nombre → botón **"Aprobar N llamadas"**.
- La aprobación reemplaza el `SI` de los scripts: guarda la lista, quién aprobó y cuándo, y manda un correo de
  confirmación a Roberto con la lista y el total de llamadas.
- Se puede subir y aprobar **hasta el domingo a las 12:00**. Una aprobación nueva **reemplaza** a la anterior de ese
  domingo. Después de las 12:00 la página no deja aprobar para ese domingo.
- La página también muestra el estado del domingo en curso (a quién ya se llamó y con qué resultado), para que
  Roberto lo revise sin entrar al servidor (Claude).
- Botón **"Detener las llamadas de hoy"**, disponible también después de las 12:00: pide el nombre de quien detiene,
  no deja hacer ninguna llamada más ese domingo y avisa por correo a Roberto. Es el único freno si se aprobó una lista
  equivocada, porque nadie del equipo puede entrar al servidor (Claude).

### 5.4 La llamada (20 a 30 segundos)
Agente nuevo **"Sofía - seguimiento"**, misma voz (Diana), prompt y extracción propios, versionado como código igual
que el de la prueba de concepto (Claude).
1. Saluda según la hora, dice que es la asistente automática de Daltile y que la llamada se graba, y confirma que habla
   con el operador.
2. "Le llamo por su entrega en {cliente/destino}, el {día} a las {hora}" (o "antes de las {límite}" si es de Día).
   "¿Va a llegar a tiempo?"
3. Si no dio una hora: "¿A qué hora calcula llegar?" (una sola vez).
4. Solo si va retrasado: "¿Qué pasó?" (motivo).
5. Repite el día y la hora completos para confirmar: "¿Llega el lunes 30 antes de las 8 de la mañana?" — así "mañana"
   nunca queda ambiguo (Claude, por la prueba del 2026-11-24).
6. Cierra con: "Si algo cambia, por favor avise por WhatsApp al teléfono de Monitoreo, {telefono_monitoreo}" (Roberto)
   y **termina la llamada**, sin volver a hablar aunque le digan algo después de despedirse (falla vista en la prueba
   del 2026-11-24).
- **Si la cita ya pasó** al momento de la llamada (por ejemplo, un reintento de las 19:00 para una cita del domingo a
  las 15:00), Sofía no pregunta si va a tiempo: pregunta **si ya realizó la entrega con el cliente** (Roberto). Si dice
  que no, pregunta qué pasó y a qué hora calcula llegar. Los domingos normalmente no hay citas ni entregas, así que es
  un caso raro: casi todas las citas son del lunes en la mañana.
- Si contesta otra persona: pide hablar con el operador; si no está, cuenta como **sin respuesta**. No se acepta la
  respuesta de un tercero.
- Buzón de voz: no deja datos y cuelga; cuenta como sin respuesta.
- Heredado de la prueba de concepto: no inventar datos, no prometer nada, no reprogramar, aceptar interrupciones,
  decir que es asistente automática si le preguntan.

### 5.5 Qué se registra y cómo se decide
Datos a extraer de cada llamada: `hablo_con_operador` (sí/no), `hora_estimada_dicha` (tal como la dijo),
`hora_estimada` (HH:MM, solo si la dijo clara; si no, vacío y nunca inventado), `llega_antes_de_la_cita` (sí / no /
no sabe), `entrega_realizada` (sí / no / no aplica; solo cuando la cita ya pasó), `motivo`.

Regla (Roberto, sin tolerancia):
- **A tiempo** → solo se registra: dio una hora **igual o anterior** a la hora de la cita (o al límite en una cita de
  Día), o dijo con claridad "antes de las {hora}" y lo confirmó en el paso 5.
- **Entregado** → solo se registra: la cita ya había pasado y el operador dijo que ya realizó la entrega.
- **Pasa a monitoreo** → la cita ya pasó y no entregó (o no lo dice claro), hora posterior, respuesta vaga ("creo que sí", "depende del tráfico"), sin hora después de
  preguntarla, llega otro día, o 3 llamadas sin respuesta.
- **Sin respuesta** → no contestó, buzón, otra persona sin el operador o la llamada falló; se reintenta según 5.1.
- La decisión la toma el script con los datos extraídos, no el agente.

### 5.6 Correos
- Salen de una **cuenta de Gmail dedicada al bot** (contraseña de aplicación en `.env`) (Roberto acordó; Claude: el
  correo corporativo difícilmente deja enviar desde AWS).
- **Después de cada ronda** (13:00 y 19:30): un correo **a cada persona de monitoreo solo con sus casos nuevos** que
  pasan a monitoreo, con copia a Roberto. Si no hay casos nuevos, no se manda.
- Cada caso trae: viaje, línea, operador y teléfono, cliente, cita, qué dijo (hora tal como la dijo y motivo), cuántas
  llamadas se hicieron y el ID de la conversación.
- **Lunes 7:00**: resumen a cada persona de monitoreo con todos sus viajes del domingo y su estado; a Roberto, el de
  todos, con un Excel adjunto.
- **Correo de control a Roberto (Claude):** al terminar cada ronda, aunque no haya casos nuevos, un correo corto con
  cuántas llamadas se hicieron, cuántos a tiempo, cuántos a monitoreo y cuántos pendientes. Si no llega, es señal de
  que el bot no corrió. Una alarma desde fuera del servidor queda fuera del MVP.
- Si un correo falla, el caso queda marcado como pendiente de aviso y se reintenta en la siguiente ronda o en el
  resumen; la falla se anota y queda visible en la página.
- El envío pasa por un solo punto (un "aviso" con canal correo) para poder agregar WhatsApp o SMS después sin tocar
  las reglas (Claude).

### 5.7 Candados
- Solo se llama a viajes de la **lista aprobada** del domingo en curso, y como máximo 3 veces cada uno.
- Mientras dure el ensayo, además, solo a números de `config/numeros_permitidos.txt` (se revisa al aprobar y otra vez
  justo antes de cada llamada).
- Ventana de llamadas: **domingo de 13:00 a 21:00**, hora de CDMX. Fuera de ella el script no marca (el `--forzar`
  actual solo para pruebas a mano).
- Tope de llamadas por domingo configurable (por ejemplo 150) como freno ante un error.
- La recarga automática de Twilio se queda apagada.
- Keys enmascaradas en todo lo que se imprima o se muestre.

### 5.8 Etapas
1. **Ensayo** (uno o dos domingos): celulares del equipo que simulan operadores con casos distintos (a tiempo, tarde,
   vago, no contesta, contesta otra persona), número de Twilio de EE. UU., servidor Lightsail aparte.
2. **Operadores reales**: con número mexicano, aviso de privacidad y aprobación de TI; se quita la lista blanca y la
   lista aprobada pasa a ser el único candado de números.
3. **Servidor de la oficina**: se mueve igual, cuando se conozca el servidor.

### 5.9 Preparado para extender a las noches
El calendario (días, horas de ronda, reintentos, ventana de llamadas y rango de citas) vive en un archivo de
configuración, no en el código, para poder agregar después rondas nocturnas entre semana. El saludo dice "Buenas
noches" entre la medianoche y las 5:00 (Claude).

## 6. Lo que queda a quien lo construya
- La tecnología de la página (sugerencia: algo pequeño en Python, en este mismo repositorio) y cómo se sirve con HTTPS en
  Lightsail.
- Cómo se programan las rondas (cron o Programador de tareas) y cómo se guarda el estado de cada viaje entre rondas.
- El texto exacto del prompt de "Sofía - seguimiento" según 5.4, y su configuración de extracción según 5.5.
- El formato exacto de los correos y del Excel del resumen.
- Las instrucciones paso a paso para que Roberto cree el servidor Lightsail.
- Las pruebas automáticas y los escenarios del ensayo.
- Lo que se reutiliza de la prueba de concepto (`lib/seguridad.py`, `lib/formato_voz.py`, `validar_citas.py`,
  `subir_agente.py`) y lo que se construye nuevo, incluida la llamada saliente por Twilio que la Fase 4 todavía no
  tiene.
