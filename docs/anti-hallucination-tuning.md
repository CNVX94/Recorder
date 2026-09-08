# Guía de Calibración Anti-Alucinaciones y Léxico Personal

En modelos de transcripción por IA basados en arquitecturas Transformer Encoder-Decoder (como Whisper), las **alucinaciones** son transcripciones inventadas generadas cuando el audio no contiene suficiente información acústica o cuando el decodificador entra en un patrón degenerativo.

Esta guía explica los tipos de alucinaciones más comunes, cómo las combate **Recorder** y cómo utilizar el panel de **Calibración (Fine-Tuning)** para adaptarlo a tu entorno personal o de trabajo.

---

## 1. Tipos de Alucinaciones en Whisper

### A. Alucinaciones por Silencio o Ruido de Fondo
* **Síntoma**: En momentos de silencio, estática o pausas largas, el modelo genera frases como *"¡Suscríbete al canal!", "Gracias por ver el vídeo", "Subtítulos por la comunidad...", "amara.org", "Nos vemos en el próximo episodio"*.
* **Causa**: Whisper fue entrenado con miles de horas de audio de YouTube y subtítulos web. Ante ausencia de voz, el decodificador asigna probabilidades altas a fórmulas de cierre habituales en vídeos.
* **Solución en Recorder**:
  1. **Voice Activity Detection (VAD)** activado en pre-procesamiento para no enviar silencios puros al modelo.
  2. **Umbral `no_speech_prob`**: Si la probabilidad de que no haya voz en el fragmento supera el umbral (por defecto `0.6`), el segmento se descarta.
  3. **Lista Negra (`ignore`)**: Búsqueda insensible a mayúsculas y tildes de frases prohibidas conocidas.

---

### B. Bucles de Repetición Infinita
* **Síntoma**: El modelo empieza a repetir una palabra, sílaba o frase sin detenerse (*"de de de de de de de de"* o *"bueno bueno bueno bueno"*).
* **Causa**: Naturaleza autorregresiva de los modelos de lenguaje: al predecir la palabra siguiente basándose en las anteriores, una repetición refuerza la probabilidad de repetirse a sí misma.
* **Solución en Recorder**:
  1. **`condition_on_previous_text = False`**: Cada fragmento de audio se transcribe de forma independiente, evitando que un error contamine los siguientes minutos de reunión.
  2. **Filtro de Ratio de Compresión zlib (`compression_ratio_threshold = 2.4`)**: Las secuencias repetitivas tienen un nivel de redundancia muy alto. Al comprimir el texto con el algoritmo zlib, si el tamaño comprimido es anormalmente pequeño respecto al original, el segmento se marca como bucle y se elimina.
  3. **`repetition_penalty = 1.1`**: Penaliza tokens repetidos en el decodificador de `faster-whisper`.

---

### C. Confusiones Fonéticas y Jerga Técnica
* **Síntoma**: Palabras en español cotidiano reemplazan términos de desarrollo o nombres propios (por ejemplo, transcribir *"cuba"* en lugar de *"QA"*, o *"ayayas"* en lugar de *"IIS"*).
* **Causa**: El vocabulario base de Whisper desconoce siglas internas de la empresa o nombres de servidores.
* **Solución en Recorder**:
  1. **Prompt de Contexto (`vocab`)**: Se envía al inicio de cada inferencia para sesgar los priors probabilísticos de Whisper hacia tu vocabulario técnico.
  2. **Diccionario Fonético Personal (`fixes`)**: Reglas de reemplazo post-inferencia con delimitadores de palabra completa (`\b`) para que solo sustituya la palabra aislada y no afecte a palabras mayores (ej: corrige *"cuba"* por *"QA"*, pero no toca *"incubadora"*).

---

## 2. Cómo Usar el Menú de Calibración (`🎯 Calibrar`)

Desde la ventana principal de la aplicación, haz clic en **🎯 Calibrar**:

```
+-----------------------------------------------------------------------+
| 🎯 Calibración Anti-Alucinaciones y Léxico Personal                  |
+-----------------------------------------------------------------------+
| 1. Vocabulario de contexto (Initial Prompt):                          |
| [ Daily de desarrollo de software. Términos: API Core, QA, IIS...   ] |
|                                                                       |
| 2. Frases prohibidas / Lista negra:          [+ Añadir comunes]       |
| [ suscríbete, gracias por ver, amara.org, hasta la próxima...       ] |
|                                                                       |
| 3. Correcciones de léxico personal (mal=bien; ...):                   |
| [ cuba=QA; ayayas=IIS; yenkins=Jenkins; reyis=Redis                 ] |
|                                                                       |
| 4. Umbrales Heurísticos:                                              |
|    Filtro silencio (no_speech_prob > X):        [---O-------] 0.60    |
|    Confianza mínima (avg_logprob < X):          [-----O-----] -1.0    |
|    Anti-bucles repetición (ratio compresión):   [-------O---] 2.40    |
|                                                                       |
| 🧪 Sandbox de Prueba en Vivo:                                         |
| [ Revisa cuba porque Ana no responde. ]                               |
|                        [🎲 Frase de ejemplo] [⚡ Probar Reglas]         |
| ✅ ACEPTADA: "Revisa QA porque Ana no responde."                     |
|                                                                       |
|                                      [Cancelar] [💾 Guardar Calibración]
+-----------------------------------------------------------------------+
```

### Pasos recomendados para ajustar a tu uso personal:

1. **Añadir nombres y términos en el Contexto (Campo 1):**
   * Agrega los nombres de pila de tus compañeros de daily y los nombres de proyectos/repositorios clave.
2. **Importar frases de alucinación comunes (Campo 2):**
   * Haz clic en **`+ Añadir comunes`** si notas que aparecen frases de cierre de vídeos de YouTube.
3. **Corregir palabras persistentes (Campo 3):**
   * Cada vez que veas que una palabra se transcribe sistemáticamente mal, añade el par `palabra_mal=Palabra_Bien;` separado por punto y coma.
4. **Validar en el Sandbox antes de guardar:**
   * Escribe la frase en la caja de prueba y presiona **`⚡ Probar Reglas`**. Podrás ver si la regla funciona exactamente como esperas antes de guardarla.
5. **Guardar:**
   * Al hacer clic en **`💾 Guardar Calibración`**, los cambios se guardan en `config.json` y se aplican en caliente a las transcripciones en curso sin necesidad de reiniciar la app.

---

## 🎲 Frases de ejemplo automaticas

El boton **🎲 Frase de ejemplo** arma una frase de prueba usando tu propio glosario, en lugar de obligarte a inventar ejemplos a mano. Toma los terminos del campo de vocabulario, las palabras mal oidas del diccionario de correcciones, las frases de la lista negra y tus palabras clave, y los combina en una frase con forma de daily.

Cada pulsacion ejercita al azar uno de los cuatro caminos del pipeline:

| Camino | Que comprueba | Resultado esperado |
| :--- | :--- | :--- |
| `limpia` | Que una frase normal no se descarte por error. | ACEPTADA sin cambios. |
| `clave` | Que tus palabras clave disparen la captura. | ACEPTADA con captura. |
| `correccion` | Que el diccionario sustituya el termino mal oido. | ACEPTADA y corregida. |
| `alucinacion` | Que la lista negra atrape la frase fantasma. | DESCARTADA. |

Solo se ofrecen los caminos que tengas configurados. Si aun no has escrito correcciones, no saldran frases de ese tipo. Las frases se generan con lo que hay **escrito en ese momento** en el dialogo, no con lo ultimo guardado, asi que puedes probar un cambio antes de confirmarlo.
