# Bot de voz "Sofía" — avisos de citas de entrega (prueba de concepto)

Prueba interna de Daltile México. Un agente de voz de **ElevenLabs** llama por **Twilio** para avisar una cita de entrega y capturar la confirmación. **Solo se llama a celulares del equipo** que estén en la lista blanca. Todos los datos de citas son ficticios.

## Requisitos
- Windows con Python 3.12 o más reciente y Git.
- Cuenta de ElevenLabs (plan Starter recomendado) y cuenta de Twilio.

## Instalación (una sola vez)
Abre una terminal en esta carpeta y corre:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Configuración
1. Copia `.env.example` como `.env` y pega tus keys. **El `.env` nunca se sube a git.**
2. Copia `config/numeros_permitidos.ejemplo.txt` como `config/numeros_permitidos.txt` y pon un celular por línea (`+52` y 10 dígitos). Este archivo tampoco se sube a git, porque trae celulares reales.

## Scripts
| Script | Qué hace | ¿Gasta dinero? |
|---|---|---|
| `verificar_conexion.py` | Confirma que las keys de ElevenLabs y Twilio funcionan y si se puede llamar a México | No (solo lectura) |
| `validar_citas.py` | Revisa la tabla de citas (formatos, vacíos, duplicados, lista blanca, fechas pasadas) | No |
| `herramientas/generar_datos_ejemplo.py` | Regenera los archivos de ejemplo de `datos/` | No |
| `agente/elegir_voces.py` | Lista voces mexicanas que sirven para agentes y escribe `agente/voces_mexicanas.md` | No |
| `agente/usar_cita_en_prueba.py --escenario N` | Carga en el agente la cita del escenario N para probar en navegador | No |
| `pruebas/revisar_prueba.py --escenario N --ronda R` | Revisa la última prueba contra lo esperado y la anota en `pruebas/bitacora.csv` | No |
| `agente/subir_agente.py` | Crea o actualiza el agente desde `prompt.md` y `config.json`, y comprueba cómo quedó (`--revisar` solo comprueba; `--agente seguimiento` es el del domingo) | No (no hace llamadas) |
| `herramientas/registrar_numero.py` | Registra el número de Twilio en ElevenLabs y guarda `ELEVENLABS_PHONE_NUMBER_ID` en `.env` | No |
| `herramientas/generar_viajes_ejemplo.py` | Regenera `datos/viajes_prueba.xlsx` y `datos/viajes_con_errores.xlsx` | No |
| `python -m domingo.servir` | Página web del domingo (subir, aprobar, detener); en el servidor corre como servicio | No |
| `python -m domingo.latido` | Latido cada 5 minutos: llama, reintenta y manda correos según la hora de CDMX | **Sí** (llama, pero solo con la lista aprobada y los candados) |
| `despliegue/instalar.sh` | Instala o actualiza todo en el servidor Ubuntu (se corre con `sudo`) | No (solo la renta del servidor) |

Ejemplos:
```
.venv\Scripts\python verificar_conexion.py
.venv\Scripts\python validar_citas.py --lista datos\numeros_demo.txt --mostrar-voz
.venv\Scripts\python -m pytest -q
```

## Tabla de citas (`datos/citas_prueba.csv`)
- Ábrela en Excel. Al guardar, elige **"CSV UTF-8 (delimitado por comas)"**.
- Pon las columnas `telefono` y `tel_trafico` como **Texto** para que Excel no borre el `+`.
- Teléfonos: `+52` y 10 dígitos. Fecha: `AAAA-MM-DD`. Hora: `HH:MM` en formato de 24 horas (`08:30`, `16:45`).
- `tipo_contacto`: `Operador` o `Despacho`.
- Escribe las direcciones sin abreviaturas ("Avenida", "colonia"), para que el bot las lea bien.
- Las columnas de resultado (`estatus`, `motivo`, etc.) se dejan vacías; las llenan los scripts.
- Antes de llamar, los teléfonos de las citas deben estar en `config/numeros_permitidos.txt`.

## El agente (`agente/`)
- `prompt.md`: lo que dice y hace Sofía. `config.json`: voz, idioma, modelo, tiempos, tecla 1, privacidad y datos que se extraen de cada llamada.
- Después de cambiar cualquiera de los dos, corre `.venv\Scripts\python agente\subir_agente.py` y haz commit, para que cada cambio quede versionado.
- Para cambiar la voz, toma el `voice_id` y el `public_owner_id` de `agente/voces_mexicanas.md` y ponlos en `config.json`. El script agrega la voz a "Mis voces" si hace falta.

## Candados de seguridad (`lib/seguridad.py`)
Todos los scripts que llamen:
- solo llaman a números de `config/numeros_permitidos.txt`, y si encuentran otro se detienen antes de llamar;
- piden escribir `SI` después de mostrar cuántas llamadas harán y a quién;
- solo corren entre 9:00 y 20:00 hora de Ciudad de México, salvo con `--forzar`;
- nunca imprimen una key completa, solo sus últimos 4 caracteres.

## Seguimiento de domingo (`domingo/`)
Cada domingo el equipo sube la lista de viajes en una página web, Roberto la aprueba antes de las 12:00 y el bot llama
a los operadores a partir de las 13:00 (reintentos a las 19:00 y 19:30). Cada persona de monitoreo recibe por correo solo
sus casos, Roberto recibe correos de control y el lunes a las 7:00 llega el resumen en Excel.
- La página (`python -m domingo.servir`) exige `PAGINA_PASSWORD` y `PAGINA_SECRETO` en el `.env`.
- El latido (`python -m domingo.latido`) lo corre `cron` cada 5 minutos en el servidor. Los dos deben correr con el mismo usuario de Linux.
- `config/domingo.json` trae `"ensayo": true`: mientras sea así solo se llama a los celulares de `config/numeros_permitidos.txt`.
- Montaje del servidor paso a paso: `docs/guia-servidor-domingo.md`. Archivos de despliegue en `despliegue/`.
- Diseño: `docs/superpowers/specs/2026-11-24-seguimiento-domingo-design.md`.

## Bitácora
Avance, decisiones y pendientes en `PROGRESO.md`.
