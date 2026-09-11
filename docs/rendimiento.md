# Rendimiento de la transcripción en CPU

Recorder transcribe con `faster-whisper` (CTranslate2) en CPU, sin GPU. Con `large-v3-turbo` la transcripción va al ritmo justo del tiempo real, y en una reunión larga la cola de fragmentos pendientes crece hasta cientos de fragmentos que tardan casi una hora en terminar después de la reunión. Este documento recoge **qué se midió, en qué condiciones, qué es fiable y qué no**, y qué palancas quedan por medir con el equipo en reposo.

Lo importante primero:

* **La medición de hoy se hizo con el equipo cargado**: Recorder estaba transcribiendo una reunión real (4 hilos al 100 %) y Teams y el navegador estaban abiertos. Otros procesos consumían entre el **56 % y el 70 %** de la CPU durante las pasadas. Los números absolutos de esta sesión **no** sirven como referencia de velocidad; se cortó la medición tras dos filas para no seguir robándole CPU a la transcripción real.
* Lo que **sí** está verificado (en el código de `faster-whisper` y en los logs de CTranslate2, no depende del ruido): la aplicación usaba **4 hilos de CPU en una máquina de 10 núcleos**; cada llamada a `transcribe()` paga **una pasada completa del codificador de 30 s aunque el fragmento dure 10 s**; `int8` e `int8_float32` son **lo mismo** en esta CPU; y el GEMM empaquetado de MKL ya está activo.
* Se ha implementado el mínimo sin riesgo: `cpu_threads` ahora se lee de `config.json` (por defecto `0`, que es exactamente lo de antes). Elegir el valor bueno requiere medir en reposo con `tools/medir_rendimiento.py` (unos 15 minutos).

---

## 1. Condiciones de medición

| | |
| :--- | :--- |
| Equipo | Portátil con Intel Core i7-1255U: 10 núcleos físicos / 12 hilos, **2 núcleos de rendimiento (P, procesadores lógicos 0-3, con HT) + 8 de eficiencia (E, procesadores 4-11)**, medido con `GetLogicalProcessorInformationEx`. Sin GPU. Plan de energía del fabricante, no se tocó. |
| Software | Windows 11, Python 3.14, `faster-whisper` 1.2.1, `ctranslate2` 4.8.2. |
| Backend CTranslate2 (`CT2_VERBOSE=2`) | `Selected ISA: AVX2` (sin AVX-512), `Use Intel MKL: true`, `GEMM_S8 backend: MKL (packed: true)`. Al pedir `compute_type="int8"` el log dice `Selected compute type: int8_float32`. |
| Muestra de audio | 241 s (4 min) de una *daily* ficticia en español con vocabulario técnico genérico (API Gateway, Kubernetes, PostgreSQL, webhook, TLS…), 546 palabras en 22 turnos, sintetizada con la voz de Windows es-MX a 16 kHz mono, con 0,8 s de silencio entre turnos. Es audio limpio: los errores de una reunión real serán mayores, pero la muestra es idéntica para todas las filas y el guion permite calcular el WER. |
| Segmentación | La misma política que `capture.py`: corte en una pausa de 0,6 s tras 8 s, forzado a 20 s. Sobre la muestra produce **23 fragmentos de 10,5 s de media** (mín 2,9 s, máx 16,6 s). |
| Llamada | La misma que `whisper_worker._process()`: `language="es"`, `vad_filter=True`, `condition_on_previous_text=False`, `repetition_penalty=1.1`, `initial_prompt` con un vocabulario genérico de 133 tokens (el de un usuario típico ronda los 90). |
| Protocolo | Un proceso por configuración. Se transcribe el primer fragmento y se descarta (carga y calentamiento); después una o dos pasadas cronometradas sobre todos los fragmentos. Velocidad = segundos de audio / segundos de reloj. Se registra la CPU que consumen **otros** procesos durante cada pasada (`GetSystemTimes` menos el tiempo de proceso propio). |
| Calidad | WER (tasa de error por palabra) frente al guion, con texto normalizado (minúsculas, sin tildes ni puntuación). Los números dichos en letras y transcritos en cifras ("doscientos" → "200") cuentan como error; es el mismo sesgo para todas las filas. |
| **Carga ajena** | **Durante toda la sesión estaba en marcha otra instancia de Recorder transcribiendo una reunión real (modelo `large-v3-turbo`, 4 hilos al 100 %), más Teams, el navegador y Visual Studio.** |

---

## 2. Mediciones

### 2.1. Medidas de hoy (equipo cargado)

| # | Modelo | Configuración | Audio | Velocidad | WER | CPU de otros procesos | Fiabilidad |
| :-: | :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| 1 | `small`, int8 | beam 1, sin prompt, **cpu_threads 8** | 241 s, 23 fragmentos | **1,97x** (1 pasada) | 12,1 % | 56 % | Velocidad: **baja** como valor absoluto (contención). WER: fiable (la salida es determinista). |
| 2 | `large-v3-turbo`, int8 | beam 5, prompt 133 tokens, **cpu_threads 0 (= 4)**, la configuración actual | 90 s, 9 fragmentos de 10,0 s | **0,33x** (pasadas: 0,31x y 0,36x) | no calculado (muestra recortada) | 65-70 % | Velocidad: **baja** como absoluto. Sí es representativa de lo que rinde la configuración actual mientras hay otra transcripción y Teams en marcha. |

Lectura honesta de estas dos filas:

* La fila 2 dice que, **con la CPU compartida con otra transcripción de 4 hilos y una llamada de Teams, la configuración actual va a un tercio del tiempo real**: la cola crece tres segundos por cada segundo de reunión. No es una medida limpia de la palanca, pero sí del escenario real "Recorder + Teams en el mismo portátil".
* Las dos filas **no son comparables entre sí** (modelos distintos, beam distinto, carga ajena distinta). No se puede deducir de ellas la ganancia de `cpu_threads`.
* El **WER del 12,1 %** de `small` beam 1 sin prompt se descompone así al comparar los textos: unas 10 de las 66 palabras erróneas son números en cifras (no son errores reales); el resto son anglicismos técnicos destrozados (*Apigatewai*, *Stying*, *Riddis*, *Prometries*, *Rojvak* por *rollback*, *CUA* por QA, *IS* por IIS) y algún nombre de tecnología. Es exactamente el tipo de error que el `vocab` y los `fixes` corrigen; sin ellos, `small` no vale para una reunión técnica.

### 2.2. Punto de partida (medidas previas, equipo en reposo, muestra de 35 s)

Estas cifras las aportó el usuario como punto de partida; hoy **no se han podido verificar** por la carga ajena. Se dejan porque son la única referencia en reposo disponible y son coherentes con lo que se sabe de estos modelos.

| Modelo | Configuración | Velocidad |
| :--- | :--- | ---: |
| small | beam 1, sin prompt | 5,4x |
| small | beam 5 + initial_prompt | 3,0x |
| medium | beam 5 + initial_prompt | 1,2x |
| large-v3-turbo | beam 1, sin prompt | 1,3x |
| large-v3-turbo | beam 5 + initial_prompt | 1,0x |

### 2.3. Hechos verificados que no dependen del ruido

Estos puntos salen de leer el código instalado y los logs del motor, no de cronometrar, así que son fiables aunque el equipo estuviera cargado.

1. **La aplicación usaba 4 hilos en una CPU de 10 núcleos.** `WhisperModel` se creaba sin `cpu_threads`; la firma de `faster-whisper` 1.2.1 dice `cpu_threads: int = 0` y su docstring: *"Number of threads to use when running on CPU (4 by default)"*; ese valor pasa tal cual a `intra_threads` de CTranslate2 (`transcribe.py`, línea 694). La documentación de CTranslate2 recomienda que `inter_threads * intra_threads` no supere el número de núcleos físicos (10 aquí).
2. **Cada llamada paga el codificador entero de 30 s.** `generate_segments()` recorta o rellena cada ventana a `nb_max_frames` (`pad_or_trim(segment)`, línea 1180), y `nb_max_frames = chunk_length * 100` con `chunk_length = 30` en el `FeatureExtractor`. Un fragmento de 10 s se rellena con 20 s de silencio antes de entrar al codificador. Con la segmentación actual (media de 10-10,5 s por fragmento), **dos tercios del trabajo del codificador se gastan en relleno**. En `large-v3-turbo` el codificador es la parte grande (32 capas frente a 4 del decodificador), así que este coste fijo pesa más que en `small`.
3. **`int8` y `int8_float32` son lo mismo en esta CPU.** CTranslate2 resuelve `int8` como `int8_float32` (log: `Selected compute type: int8_float32`). Cambiar entre ambos no puede dar nada.
4. **El GEMM empaquetado de MKL ya está activo** (`packed: true` en el log). `CT2_PACKED_GEMM` no aporta nada; solo sirve para desactivarlo.
5. **Sin AVX-512.** La CPU anuncia AVX2 y CTranslate2 selecciona AVX2. `CT2_FORCE_CPU_ISA` no puede mejorar nada (solo empeorar forzando `AVX` o `GENERIC`).
6. **El `initial_prompt` se codifica en cada llamada.** Con `condition_on_previous_text=False` y fragmentos de menos de 30 s, el prompt (unos 90 tokens con un vocabulario típico) se procesa una vez por fragmento como prefijo del decodificador. Es una pasada del decodificador de 4 capas sobre ~90 tokens frente a una del codificador de 32 capas sobre 1500 posiciones: **el coste debería ser pequeño**, pero no se ha medido.
7. **Reintentos por temperatura.** `transcribe()` usa por defecto `temperature=[0, 0.2, 0.4, 0.6, 0.8, 1.0]`: si un fragmento no supera `compression_ratio_threshold` o `log_prob_threshold`, se **vuelve a decodificar** con la siguiente temperatura, hasta seis veces. En la muestra limpia ocurrió **0 veces**; en audio real con ruido o silencio puede multiplicar el coste de los fragmentos malos, que además el pipeline de Recorder acaba descartando.
8. **VAD no reduce el coste del codificador.** `vad_filter=True` recorta silencios antes de la ventana, pero la ventana se rellena a 30 s igual; solo ahorra cuando un fragmento supera los 30 s de voz.

---

## 3. Palancas, una por una

La escala de confianza: **alta** = verificado en código/logs o medido limpio; **media** = razonamiento sólido sin medida en reposo; **baja** = hipótesis.

### 3.1. `cpu_threads` (implementada la opción; el valor bueno queda por medir)

* **Qué es**: hilos OpenMP de CTranslate2 por llamada. Hoy: 4. Núcleos físicos: 10.
* **Medido**: no en reposo. La única fila con `large-v3-turbo` (0,33x) se hizo con 4 hilos y otros procesos ocupando dos tercios de la CPU; no hay fila con 8 hilos en las mismas condiciones.
* **Expectativa** (confianza media): pasar de 4 a 8-10 hilos debería acelerar el codificador, que es puro GEMM y escala bien. **No** se espera que 12 gane a 10: en esta CPU híbrida los hilos extra caen en los núcleos E, más lentos, y en un bucle OpenMP el más lento marca el paso. Es posible que el óptimo esté en 8 y no en 10 por el mismo motivo. Solo la medición lo dirá.
* **Coste de calidad**: **ninguno**; el resultado es idéntico con cualquier número de hilos.
* **Contrapartida**: durante la reunión, más hilos compiten más con Teams. Si la llamada empieza a entrecortarse, bajar a 6.
* **Cómo medirlo** (equipo en reposo, Recorder y Teams cerrados, unos 15 min):

  ```powershell
  python tools\medir_rendimiento.py
  ```

  Imprime una tabla con 0 (= 4), 4, 6, 8, 10 y 12 hilos, la velocidad de cada uno sobre la misma muestra y el WER. El script se niega a medir si otros procesos ya consumen más del 15 % de la CPU. Poner el ganador en `config.json` (`"cpu_threads": 8`, por ejemplo) y reiniciar Recorder.

### 3.2. Longitud del fragmento y fusión de la cola pendiente (no implementada; la mejor palanca estructural)

* **Qué es**: el codificador cuesta lo mismo para 8 s que para 30 s (hecho 2). Fragmentos más largos amortizan ese coste fijo.
* **Medido**: no. La segmentación actual produce fragmentos de 10-10,5 s de media sobre la muestra, lo que sí es una medida.
* **Expectativa** (confianza media-alta por el hecho 2): si el codificador domina, pasar de fragmentos de ~10 s a ~28 s reduce las pasadas del codificador a poco más de un tercio; la ganancia total será menor porque el decodificador sigue costando lo mismo por palabra. Una estimación prudente para `large-v3-turbo` es entre 1,5x y 2x sobre el estado actual; hay que medirla (`--fusion 30` en la herramienta compara la misma muestra con fragmentos fusionados hasta 30 s).
* **Dos formas de aprovecharlo**:
  1. **Subir `min_sec`/`max_sec` en `capture.py`** (por ejemplo 20/30). Sencillo, pero **retrasa el texto en vivo**: la primera palabra de un fragmento tarda hasta 30 s en aparecer en pantalla en vez de hasta 20.
  2. **Fusionar fragmentos consecutivos de la misma fuente en el worker solo cuando hay cola** (concatenar los pendientes hasta ~28 s antes de llamar a `transcribe()`). En vivo, sin cola, no cambia nada; al drenar 200 fragmentos, el codificador se ejecuta un tercio de las veces. El coste es de granularidad: cada línea de la nota cubriría hasta 30 s de audio con una sola marca de tiempo en lugar de 10-20 s. La calidad de transcripción no baja; Whisper está entrenado con ventanas de 30 s y suele ir mejor con más contexto.
* **Recomendación**: medir primero con `--fusion 30`; si la ganancia es la esperada, implementar la opción 2 con un tope configurable.

### 3.3. `beam_size` 5 → 1 (solo recomendación; cuesta calidad)

* **Medido hoy**: no con `large-v3-turbo`. Las medidas previas del usuario dan 1,3x (beam 1, sin prompt) frente a 1,0x (beam 5 + prompt), pero mezclan dos cambios.
* **Expectativa** (confianza media): beam 1 reduce el trabajo del decodificador unas 5 veces; como en `turbo` el decodificador es pequeño, la ganancia total es moderada (del orden del 20-30 %, no 5x).
* **Coste de calidad**: real. Con beam 1 el decodificador toma la primera opción en cada paso y se equivoca más en nombres y términos raros, justo lo que importa en una *daily*. Hay que verlo en el WER: `python tools\medir_rendimiento.py --hilos 8 --beam 1` frente a `--beam 5`, y comparar los textos guardados. **Decisión del usuario**; no se ha aplicado.
* Un punto intermedio (`beam_size: 2` o `3`) puede recuperar casi toda la velocidad con menos pérdida; también es medible con `--beam 2`.

### 3.4. `compute_type` (descartada)

* `int8` = `int8_float32` en esta CPU (hecho 3): **nada que ganar**.
* `int16` y `float32`: no medidos. Con MKL y AVX2 el camino rápido es el int8 (`GEMM_S8`); `float32` mueve cuatro veces más memoria y `int16` no tiene ventaja sobre int8 en esta ISA. Expectativa (confianza media): más lentos que int8, sin mejora apreciable de calidad para transcripción. No merece la pena medirlos antes que las palancas anteriores.

### 3.5. `num_workers` (no medida; útil solo en un caso)

* **Qué es**: réplicas del modelo que atienden llamadas a `transcribe()` desde varios hilos de Python a la vez (`inter_threads` en CTranslate2). Recorder tiene un solo hilo consumidor, así que **hoy no haría nada** aunque se pusiera a 2.
* **Cuándo ayudaría** (confianza media): si la medición de hilos muestra que 8-10 hilos en una sola llamada escalan mal (por ejemplo 10 hilos apenas mejor que 6), dos réplicas de 4-5 hilos procesando dos fragmentos a la vez pueden aprovechar mejor los núcleos. Requiere dos hilos consumidores en el worker. La documentación de CTranslate2 lo recomienda para "grandes volúmenes" precisamente por esto, con la regla `inter * intra ≤ núcleos físicos`.
* **Coste**: más memoria (`large-v3-turbo` int8 ronda 0,8-1 GB por réplica) y el orden de las líneas en la nota deja de ser el de llegada salvo que se reordene.
* **Recomendación**: medir después de fijar `cpu_threads`. Si 10 hilos dan claramente más que 6, no hace falta.

### 3.6. `initial_prompt` (no medida; mantenerlo)

* El vocabulario se procesa como prefijo del decodificador en cada fragmento (hecho 6). Con ~90 tokens el coste esperado es de unos pocos por ciento (confianza media). A cambio es, con diferencia, lo que más corrige los anglicismos que `small` destroza en la fila 1.
* **Recomendación**: mantenerlo. Si se quiere comprobar el coste: `--sin-vocab` frente a la ejecución normal, misma cantidad de hilos. Recortar el vocabulario a lo que de verdad se confunde (siglas, nombres) reduce tokens sin perder la parte útil.

### 3.7. Prioridad del proceso en Windows (no medida; solo importa con el equipo cargado)

* Con el equipo en reposo no puede cambiar nada: no hay con quién competir.
* Con Teams y el navegador abiertos (la situación real durante la reunión, y la de la fila 2) sí: subir Recorder a `ABOVE_NORMAL_PRIORITY_CLASS` le daría preferencia frente a Teams. Eso **quita CPU a la llamada** (vídeo y audio de Teams) y puede entrecortarla, que es peor que una cola que crece. Una prioridad *inferior* (`BELOW_NORMAL`) hace lo contrario: Recorder se retrasa durante la reunión y drena después.
* **Recomendación**: no tocarla por defecto. Si se prueba, `ABOVE_NORMAL` y nunca `HIGH`/`REALTIME`. Se puede medir con dos ejecuciones de la herramienta con carga sintética, pero solo tiene sentido después de las palancas anteriores.

### 3.8. Otras palancas encontradas en la documentación

| Palanca | Qué hace | Coste | Confianza / recomendación |
| :--- | :--- | :--- | :--- |
| `temperature=0` en `transcribe()` | Desactiva los reintentos por temperatura (hecho 7): un fragmento malo se decodifica una vez en lugar de hasta seis. | Los reintentos a veces rescatan bucles de repetición; sin ellos, el pipeline descarta ese fragmento por `compression_ratio`. | Media. Solo se nota en audio con ruido o silencios; en la muestra limpia hubo 0 reintentos. Medir en una grabación real antes de decidir. |
| `without_timestamps=True` | El decodificador no genera tokens de tiempo: menos pasos por fragmento. | Cada fragmento vuelve como **un solo segmento**, y los filtros anti-alucinación de Recorder trabajan por segmento: un trozo malo tiraría el fragmento entero, o pasaría entero. | Baja-media. Ganancia pequeña (unos pocos tokens de ~50 por fragmento); cambia el comportamiento de los filtros. No recomendada. |
| `BatchedInferencePipeline` (`batch_size` 8) | Codifica varias ventanas en un mismo lote. En GPU es la gran palanca. | En CPU el lote solo ayuda si el GEMM de una sola ventana no llena los núcleos; con 8-10 hilos probablemente ya los llena. | Baja. Medir solo si la fusión de fragmentos (3.2) no basta. |
| Afinidad a núcleos P (`SetProcessAffinityMask 0xF`) con 4 hilos | Evita que hilos caigan en núcleos E lentos. | Deja 8 núcleos sin usar. | Baja. Es una hipótesis para explicar un posible mal escalado a 12 hilos; solo si la tabla de hilos sale rara. |
| `OMP_NUM_THREADS` | Equivale a `cpu_threads` si este es 0. | — | Redundante con la opción de configuración. |
| Plan de energía | Un plan "equilibrado" del fabricante puede limitar la frecuencia bajo carga sostenida. | Batería y temperatura. | Baja. Comprobar el deslizador de energía de Windows ("Mejor rendimiento") mientras se drena una cola, con el portátil enchufado. |
| Modelo `medium` | 1,2x en reposo según las medidas previas. | Peor que `turbo` en calidad y velocidad. | Alta: descartado. `large-v3-turbo` es mejor en ambas cosas. |

---

## 4. Recomendación

Qué poner en `config.json` **hoy**, sin haber medido en reposo (no pierde calidad y no puede empeorar la velocidad):

```json
"model": "large-v3-turbo",
"beam_size": 5,
"cpu_threads": 8
```

`8` es un punto de partida: por debajo de los 10 núcleos físicos y deja margen a Teams. **Es una hipótesis razonable, no un valor medido.** Para convertirlo en dato:

1. Con Recorder y Teams cerrados: `python tools\medir_rendimiento.py` (unos 15 min). Dejar en `cpu_threads` el valor con más velocidad.
2. Después: `python tools\medir_rendimiento.py --hilos <ganador> --fusion 30`. Si sube claramente (la expectativa es 1,5x-2x), pedir que se implemente la fusión de fragmentos pendientes en el worker (3.2).
3. Solo si con lo anterior la cola sigue creciendo: `--beam 2` y `--beam 1`, mirando el WER y los textos guardados antes de sacrificar calidad.

**Cuánto ganaría**: no se puede prometer un número con las medidas de hoy. La cadena esperada, cada eslabón por medir, es: hilos (4 → 8-10) más fusión de fragmentos (10 s → 28 s de audio por pasada del codificador). Si ambos rinden como cabe esperar, `large-v3-turbo` con beam 5 y vocabulario pasaría de ~1,0x en reposo a **entre 2x y 3x**; ese rango es una estimación, no una medida.

### ¿Aguanta dos fuentes de audio a la vez?

La condición para que la cola no crezca con salida y micrófono capturando **simultáneamente** es una velocidad sostenida de al menos **2,0x** sobre una fuente (el peor caso; en una reunión normal las dos fuentes rara vez producen fragmentos a la vez, y el total ronda 1,1-1,3x del reloj, aunque eso no se ha medido).

* **Con la configuración actual: no.** Ni en reposo (1,0x según las medidas previas) ni, desde luego, con Teams abierto (0,33x medido hoy con carga ajena).
* **Con `large-v3-turbo` ajustado (hilos + fusión): no se puede afirmar todavía.** La estimación de 2x-3x lo pondría en el límite o por encima, pero es una estimación; hay que medirla. Y durante la propia reunión, con Teams consumiendo CPU, será menor que en reposo: lo realista con `turbo` es "no perder demasiado durante la reunión y drenar rápido después", no "ir en vivo con dos fuentes".
* **Con `small`: sí, con alta probabilidad, a costa de calidad.** 3,0x en reposo con beam 5 + vocabulario (medida previa) y 1,97x hoy con beam 1 sin prompt **con el equipo cargado al 56 %**. El precio es el WER del 12 % de la fila 1 en audio limpio, que `vocab` y `fixes` reducen pero no anulan.

---

## 5. Qué se cambió en el código

* `recorder/config/schema.py`: nuevo campo `cpu_threads: int = 0` (0 = valor de la biblioteca, es decir, el comportamiento anterior). `config.example.json` y el README lo documentan.
* `recorder/engine/whisper_worker.py`: `WhisperModel(..., cpu_threads=self.config.cpu_threads)`.
* `tests/test_cpu_threads.py`: el valor de `config.json` llega a `WhisperModel`, el defecto es 0 y las configuraciones antiguas sin el campo siguen cargando. Las 93 pruebas anteriores más estas 3 pasan; `python recorder.py --selftest` también.
* `tools/medir_rendimiento.py`: la herramienta de medición descrita arriba. Lee `config.json` (modelo, beam y vocabulario reales del usuario, que no se publican), genera la muestra de audio con la voz de Windows la primera vez, segmenta como `capture.py`, transcribe como `whisper_worker.py` y devuelve velocidad, WER y CPU ajena por fila.

No se ha cambiado ningún valor por defecto de comportamiento: hasta que no haya una medición en reposo, Recorder hace exactamente lo mismo que antes.

---

## 6. Pendiente de medir (en orden de valor esperado)

1. Barrido de `cpu_threads` 4/6/8/10/12 con `large-v3-turbo`, beam 5, vocabulario, equipo en reposo.
2. Fusión de fragmentos a 30 s con el mejor número de hilos.
3. `beam_size` 5/2/1 con WER y comparación de textos.
4. `num_workers` 2 × (hilos/2) si el barrido de hilos escala mal.
5. `temperature=0` sobre una grabación real con ruido (contar reintentos).
6. Prioridad `ABOVE_NORMAL` con carga sintética, midiendo también si Teams se resiente.
