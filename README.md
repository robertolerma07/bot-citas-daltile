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

## Candados de seguridad (`lib/seguridad.py`)
Todos los scripts que llamen:
- solo llaman a números de `config/numeros_permitidos.txt`, y si encuentran otro se detienen antes de llamar;
- piden escribir `SI` después de mostrar cuántas llamadas harán y a quién;
- solo corren entre 9:00 y 20:00 hora de Ciudad de México, salvo con `--forzar`;
- nunca imprimen una key completa, solo sus últimos 4 caracteres.

## Bitácora
Avance, decisiones y pendientes en `PROGRESO.md`.
