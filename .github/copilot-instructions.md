# Instrucciones para GitHub Copilot en este repositorio

Copilot lee este archivo en cada conversación del repositorio. Antes de proponer cambios grandes, lee `docs/ENTREGA.md`
(mapa del proyecto, diagramas, estado y pendientes) y, para reglas de negocio,
`docs/superpowers/specs/2026-11-24-seguimiento-domingo-design.md`.

## Qué es
Bot de voz "Sofía" (ElevenLabs Agents + Twilio) que el domingo llama a operadores de transporte para saber si llegan a
tiempo a su cita de entrega; los casos dudosos se mandan por correo a Monitoreo. Python 3.12+, Flask + waitress, pytest.
Paquete principal: `domingo/`. Agente actual: `agente_seguimiento/`. La carpeta `agente/` es la prueba de concepto de
avisos (no es el producto actual).

## Idioma y estilo
- Responde y escribe **en español de México**: código (nombres de funciones y variables), docstrings, comentarios,
  mensajes de commit, textos de la página y del bot. Sigue el estilo de los archivos existentes.
- Explica en lenguaje sencillo: el dueño no es programador.
- Cambios mínimos y enfocados. No reformatees archivos completos ni agregues dependencias sin preguntar.

## Seguridad (obligatorio)
- **Nunca** muestres, imprimas, copies ni subas a git el contenido de `.env`, keys, tokens, contraseñas ni
  `config/numeros_permitidos.txt` (celulares reales). No pidas que te los peguen en el chat.
- **Nunca** quites ni debilites los candados de `lib/seguridad.py` ni de `domingo/` (lista blanca, modo ensayo, ventana
  de 13:00 a 21:00, tope de 3 llamadas por viaje, tope por domingo, aprobación en la página).
- **No ejecutes nada que llame o gaste** sin que la persona lo pida explícitamente en ese momento:
  `python -m domingo.latido`, scripts con `--forzar`, cualquier llamada a `/v1/convai/twilio/outbound-call`. Las pruebas
  por voz en el navegador de ElevenLabs gastan ~1,000 créditos cada una; avisa antes de sugerir otra.
- `agente/subir_agente.py` **no** hace llamadas ni gasta créditos; se puede correr libremente.
- **Nunca toques el servidor de AWS `srm-piloto`** (es de otro sistema). El bot va en la instancia `bot-domingo`.
- No cambies `"ensayo": true` en `config/domingo.json` a `false` salvo que Roberto lo pida (requiere número mexicano,
  aviso de privacidad y aprobación de TI).

## Reglas de negocio que no se negocian
- **La decisión la toma el código** (`domingo/reglas.py → decidir()`), nunca el agente.
- "a_tiempo" **solo** si `llega_antes_de_la_cita == "sí"`, `hora_estimada` es un HH:MM no posterior al límite y
  ninguna fecha lo contradice. Cualquier duda → "monitoreo". Citas de tipo Hora: sin tolerancia.
- Sofía nunca inventa datos, nunca acepta la respuesta de otra persona, nunca deja datos en buzón y siempre cierra con
  el teléfono de Monitoreo y `end_call` en el mismo turno.
- Fechas, horas y teléfonos se convierten a texto hablado en Python (`lib/formato_voz.py`), no en el prompt. El
  teléfono de Monitoreo se dice en grupos 2-2-3-3.
- Si una regla no está en el diseño, **pregunta**; no la inventes.

## Flujo de trabajo
1. Para cambiar a Sofía: edita `agente_seguimiento/prompt.md` o `config.json`, agrega o ajusta una prueba en
   `tests/test_domingo_agente.py` y corre:
   ```powershell
   .venv\Scripts\python -m pytest -q
   .venv\Scripts\python agente\subir_agente.py --agente seguimiento
   ```
   El segundo comando debe terminar con todas las secciones en ✅.
2. Para cambiar lógica: escribe primero la prueba en `tests/` (hay 330; deben seguir en verde). Las horas siempre con
   zona de Ciudad de México (`lib.seguridad.ZONA_CDMX`); una hora sin zona es un error.
3. Cada prueba por voz y cada decisión se anota en `PROGRESO.md` con fecha (AAAA-MM-DD), ID de conversación,
   duración, créditos, extracción y decisión del bot.
4. Commit en español y `git push` a `master` después de cada cambio. Nunca subas `.env`, `resultados/`, `.venv/` ni
   `config/numeros_permitidos.txt` (ya están en `.gitignore`; no lo cambies).
5. Para actualizar el servidor: `sudo bash /home/sofia/bot-citas-daltile/despliegue/instalar.sh` (no toca `.env` ni
   datos). Guía completa: `docs/guia-servidor-domingo.md`.

## Estructura rápida
- `domingo/reglas.py` lógica pura · `domingo/latido.py` reloj de cada 5 min · `domingo/viajes.py` Excel y variables ·
  `domingo/pagina.py` página web · `domingo/telefonia.py` API de llamadas · `domingo/avisos.py` correos ·
  `domingo/almacen.py` estado en JSON con candado · `config/domingo.json` horarios.
- `lib/formato_voz.py` texto hablado · `lib/seguridad.py` candados.
- `tests/` pruebas (`pytest`, sin red).
