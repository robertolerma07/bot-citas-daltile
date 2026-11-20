# Diseño — Seguimiento en ruta por voz (MVP)

Fecha: 2026-11-20 · Autor: Roberto (decisiones) con Claude (redacción)

## 1. Intención y porqué
Hoy el equipo de tráfico de Daltile llama **a mano a cada operador hasta 3 veces al día** mientras va en ruta, para saber si llegará a su cita de descarga. Hacerlo con un bot de voz a 50 líneas, 3 llamadas diarias de 2 minutos, costaría unos USD $1,270–1,900 al mes. Se busca **el mismo resultado con muchas menos llamadas y más cortas**: detectar a tiempo las unidades que no entrarán en la ventana de descarga, sin molestar ni distraer a las que van bien.

## 2. Objetivos, no objetivos y anti-objetivos
**Objetivos**
- Saber de cada unidad en ruta si va en tiempo para la ventana de descarga del día comprometido y, si no, su hora estimada y el motivo.
- Que el bot registre solo lo que va bien y entregue a una persona únicamente los casos con retraso.
- Bajar el costo a unos USD $100–200 al mes para 50 líneas (ver sección 7).

**No objetivos (en esta versión)**
- Leer el GPS de las líneas transportistas (eso es el enfoque A, para después).
- Avisar al cliente: lo hace una persona del equipo.
- Reprogramar citas o negociar con el operador.

**Anti-objetivos (aunque funcione, sería un fracaso si…)**
- El operador se distrae al manejar porque la llamada es larga o le pide anotar o buscar algo.
- El bot inventa o redondea una hora estimada que el operador no dijo.
- Un retraso real queda sin pasar a una persona.

## 3. Restricciones
- Misma plataforma que la prueba de concepto: agente de ElevenLabs con la voz de Sofía (Diana) y telefonía Twilio. Lo que se aprenda en la prueba aplica aquí.
- El operador contesta con manos libres o altavoz. **No hay regla de colgar si va manejando** (decisión de Roberto del 2026-11-20). La llamada debe ser muy corta y clara.
- Las mismas protecciones que la prueba de concepto: lista blanca, confirmación antes de gastar, horario permitido, keys en `.env`.
- El MVP con líneas reales requiere lo ya listado para el MVP: número mexicano propio, aprobación de TI, aviso de privacidad y conexión con la programación real.

## 4. Enfoques considerados
| Enfoque | Qué es | Costo aprox./mes (50 líneas) | Decisión |
|---|---|---|---|
| **A. Por excepción con GPS** | Se consulta el GPS; si va en tiempo, solo un WhatsApp de recordatorio; si va atrasado o sin señal, llamada corta | ~$150–250 | Para después: requiere integrar el GPS de cada línea (TI) |
| **B. Solo llamadas cortas, con frecuencia adaptable** | Sin GPS; llamadas de 20 a 30 s; se llama menos a quien va bien | ~$100–200 | **Elegido por Roberto** |
| C. Cambiar de proveedor de voz o de telefonía | Otra plataforma o proveedor mexicano | Ahorra 30–50% por minuto | Descartado por ahora: con pocos minutos el ahorro es chico y obliga a repetir las pruebas de calidad; queda como negociación de tarifa por volumen |
| Solo WhatsApp | Mensajes en vez de llamadas | El más barato | Descartado: un operador manejando no puede contestar por escrito |

Se eligió **B** porque no depende de las líneas transportistas ni de TI, y su llamada corta es la misma que usaría A cuando se tenga el GPS.

## 5. Lo decidido

### 5.1 Cuándo se llama (por viaje)
Dos momentos al día: **9:00 (mañana)** y **18:00 (fin del día)**, hora de Ciudad de México y dentro del horario permitido de 9:00 a 20:00. No hay llamada de mediodía. (Decisión de Roberto.)

```
Llamada de las 9:00: ¿Va en tiempo? ¿A qué hora calcula llegar?
 ├─ Llega antes del FIN de la ventana ──► se registra; sigue la llamada de las 18:00
 │     Llamada de las 18:00
 │      ├─ Llega antes del fin de la ventana ──► se registra; ya no se le vuelve a llamar en ese viaje ✔
 │      └─ Llega después, o no sabe ───────────► pasa a una persona; el bot deja de llamar
 └─ Llega después del fin de la ventana, o no sabe ──► pasa a una persona; el bot deja de llamar
```
- **Regla de la ventana (decisión de Roberto):** el bot compara la hora estimada que dijo el operador con el **fin de la ventana de descarga** de la cita.
  - Si llega antes del fin, aunque vaya algo retrasado, **solo se registra**.
  - Si llega después, o no sabe decir una hora, **pasa a una persona**.
- La llamada de las 18:00 se hace aunque la de las 9:00 se haya contestado tarde, por reintentos.
- "Ya no se le vuelve a llamar" aplica al **viaje completo**, aunque dure más de un día.
- **Fin del viaje (decisión de Claude):** el viaje termina el día de la cita; después de ese día no hay llamadas.
- **No contesta:** se reintenta hasta 3 veces, con al menos 30 minutos entre intentos. **Si después del tercer intento no se pudo hablar con él, pasa a una persona (decisión de Claude).** Lo mismo aplica si confirmó a las 9:00 pero a las 18:00 no contesta.
- **Contesta otra persona (decisión de Claude):** Sofía pide hablar con el operador. Si no está, cuenta como intento sin respuesta. No se acepta la respuesta de un tercero, porque solo el operador sabe dónde va.

### 5.2 Qué pregunta Sofía (20 a 30 segundos)
1. Saluda, dice que es la asistente automática de Daltile y que la llamada se graba, y confirma que habla con el operador.
2. "¿Va en tiempo para su descarga del [día], que es entre las [inicio] y las [fin de la ventana]?"
3. "¿A qué hora calcula llegar?"
4. Solo si va retrasado: "¿Qué pasó?" (motivo).
- Las horas de la cita se dicen en la hora local del destino, tal como vienen en la programación (decisión de Claude).
5. Cierra con el teléfono de tráfico y cuelga.

Reglas que se heredan de la prueba de concepto: no inventar datos, no prometer nada, no reprogramar, aceptar interrupciones y ser breve.

### 5.3 Qué hace el bot con la respuesta
- **Registra en cada llamada:**
  - fecha y hora de la llamada;
  - si dice que va en tiempo;
  - la hora estimada **tal como la dijo**, más la misma hora en formato HH:MM si la dijo clara; si no la dio, el campo queda vacío y nunca se inventa;
  - el motivo;
  - la duración y el ID de la conversación.
- Con la hora estimada y el fin de la ventana decide si **se registra** o **pasa a una persona**, según 5.1.
- **Cómo se entera el equipo (decisión de Roberto):** después de cada ronda de llamadas (9:00 y 18:00) se genera un **Excel** con todos los viajes y su estado, y se manda un **correo** al equipo de tráfico **solo con los casos nuevos** que pasan a una persona (retraso fuera de ventana, no sabe o no contestó). La persona decide si avisa al cliente.

### 5.4 Agente y datos
- **Agente separado (decisión de Claude):** "Sofía - seguimiento", con la misma voz (Diana), su propio prompt y sus propios datos a registrar. El agente de la prueba de concepto (aviso de cita) no se toca.
- **Datos que necesita cada viaje:** ID del viaje, línea, operador, teléfono del operador, destino, fecha de la cita y **ventana de descarga (inicio y fin)**. Mientras no haya conexión con la programación real, se cargan desde un archivo, igual que en la prueba de concepto.

## 6. Lo que queda a quien lo construya
- Cómo se guarda el estado de cada viaje (en qué llamada va y si ya se cerró) y cómo se programan las llamadas de las 9:00 y las 18:00.
- Con qué cuenta de correo se envía el aviso (la del equipo, sin integrar sistemas de Daltile).
- El formato del registro de resultados y de la lista de casos para el equipo.
- El texto exacto del prompt del seguimiento, siguiendo la sección 5.2 y las lecciones de la prueba de concepto.
- Las pruebas automáticas y los escenarios de prueba.

## 7. Estimado de costo (por confirmar con datos reales de la Fase 4)
- Llamada de unos 30 s: ElevenLabs más LLM más Twilio ≈ USD $0.07–0.12 (Twilio cobra el minuto completo: $0.0473).
- Si la mayoría va en tiempo, un viaje recibe ~2 llamadas (9:00 y 18:00 del primer día).
- 50 líneas con viajes continuos dan **~USD $100–200 al mes**, contra $1,270–1,900 del esquema de 3 llamadas diarias de 2 minutos.
