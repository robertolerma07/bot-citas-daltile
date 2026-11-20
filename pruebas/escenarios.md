# Escenarios de prueba — Sofía

Guía para quien simula al operador o al despacho. Los resultados esperados que se revisan en automático están en `pruebas/esperados.csv`.

## Cómo correr cada prueba (en navegador)
1. Carga la cita del escenario en el agente (no gasta créditos):
   ```
   .venv\Scripts\python agente\usar_cita_en_prueba.py --escenario 1
   ```
2. Abre el agente en ElevenLabs y llama con el botón del teléfono 📞. En la **ronda por texto**, escribe en la caja "Envía un mensaje" en lugar de hablar.
3. Sigue el guion del escenario. Usa tus propias palabras; no hace falta leerlo exacto.
4. Al terminar, revisa la prueba y anótala en la bitácora:
   ```
   .venv\Scripts\python pruebas\revisar_prueba.py --escenario 1 --ronda 1
   ```
   El script:
   - trae la conversación más reciente y confirma que sea de la cita del escenario;
   - detecta si fue por voz o por texto;
   - compara el resultado con lo esperado;
   - busca datos que no estén en la cita, frases prohibidas y si siguió hablando después de despedirse;
   - te pide quién probó, si dijo algún dato incorrecto, si cumplió lo específico del escenario, la naturalidad (1 a 5) y comentarios.
5. **Una prueba a la vez:** el agente tiene cargada una sola cita; si dos personas prueban al mismo tiempo escenarios distintos, se cruzan.

## Qué cuenta como "pasa"
Un escenario pasa si se cumple todo esto:
- el **estatus** extraído es el esperado;
- **no dijo ningún dato** distinto a los de la cita (fechas, horas, direcciones, nombres, compromisos);
- se cumple lo específico del escenario (columna "Además debe…");
- en los escenarios 1, 2 y 4, duró **menos de 90 segundos**.

La Fase 3 termina cuando los 8 escenarios pasan **dos rondas seguidas**. En una ronda, un escenario cuenta como pasado solo si **todos** sus intentos de esa ronda pasaron; repetirlo hasta que salga bien no cuenta.

Propuesta para ahorrar créditos: **ronda 1 por texto** (valida la lógica: estatus, datos y flujo) y **ronda 2 por voz** (valida además la naturalidad y la duración).

## Los 8 escenarios

### 1. Confirma sin problema — Despacho (folio 458217, Juan Pérez)
- **Quien simula dice:** "Sí, soy Juan." → escucha los datos → "Sí, ahí estaremos."
- **Esperado:** estatus **Confirmada**, con quién habló contiene «Juan».
- **Además debe:** dar los datos en orden (folio; destino y dirección; fecha y hora; contacto en destino) y cerrar con el teléfono de tráfico.

### 2. No puede: unidad descompuesta — Despacho (458217, Juan Pérez)
- **Quien simula dice:** "Sí, soy Juan." → escucha → "No vamos a llegar, se nos descompuso la unidad." → cuando pregunte la hora: "Como a las tres de la tarde."
- **Esperado:** estatus **No puede**, motivo contiene «descompu» (descompuesta o descompuso), hora estimada contiene «tres».
- **Además debe:** NO ofrecer reprogramar ni decir que alguien le va a llamar.

### 3. Está manejando — Operador (458230, Miguel Ángel Torres)
- **Quien simula dice:** "Sí, soy Miguel." → cuando pregunte si maneja: "Sí, voy manejando."
- **Esperado:** estatus **Reintentar**.
- **Además debe:** despedirse en una frase y colgar **sin dar ningún dato** (ni folio ni teléfono de tráfico).

### 4. Contesta otra persona — Operador (458244, para Ernesto Villalobos)
- **Quien simula dice:** "No, soy Pedro Sánchez, su compañero." → acepta el mensaje: "Sí, yo le digo." → cuando pregunte si puede confirmar: "No sé, él le confirma."
- **Esperado:** estatus **Reintentar**, con quién habló: Pedro Sánchez.
- **Además debe:** dejar el mensaje con los datos y pedir que se los haga llegar a Ernesto.

### 5. Pide repetir la dirección — Operador (458230, Miguel Ángel Torres)
- **Quien simula dice:** "Sí, soy Miguel." → "No, no voy manejando." → después de los datos: "¿Me repite la dirección, por favor?" → "Sí, ahí llegamos."
- **Esperado:** estatus **Confirmada**.
- **Además debe:** repetir la dirección despacio y por partes, **con los mismos datos** (calle, número, colonia y ciudad sin cambios).

### 6. Ruido de fondo — Operador (458244, Ernesto Villalobos)
- **Preparación:** pon de fondo, con buen volumen, un video de ruido de tractocamión o de patio de maniobras.
- **Quien simula dice:** "Sí, soy Ernesto." → "No, estoy en el patio." → "Sí, sí llego."
- **Esperado:** estatus **Confirmada**.
- **Además debe:** entender, o pedir que repita y, si no entiende, pedir que marque 1. En el navegador no se pueden marcar teclas: la tecla 1 se prueba por teléfono en la Fase 4.

### 7. Interrumpe a mitad de los datos — Despacho (458217, Juan Pérez)
- **Quien simula dice:** "Sí, soy Juan." → mientras dice la dirección, interrumpe: "Perdón, ¿a qué hora era la cita?" → deja que conteste y siga → "Sí, confirmado."
- **Esperado:** estatus **Confirmada**.
- **Además debe:** callarse al ser interrumpida, contestar con la hora correcta y retomar los datos donde se quedó.

### 8. No contesta — cualquiera (458217)
- **En navegador:** inicia la llamada y **no digas nada**. Sofía debe colgar sola después de unos 20 segundos de silencio.
- **Por teléfono (Fase 4):** deja sonar sin contestar.
- **Esperado:** estatus **Sin respuesta**.
- **Además debe:** no dar ningún dato de la cita.
