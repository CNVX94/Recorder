# Captura diferida: ¿vídeo o buffer circular?

> **Estado (25-SEP-2026): implementado el plan de abajo, pasos 1 a 8.** La auditoría de una daily
> real mostró el fallo en su peor forma: 212 capturas llegaron 11-31 s tarde y, tras un atasco,
> 54 min tarde (`docs/auditoria-daily-2026-09-25.md`). Qué quedó y dónde se apartó del plan:
>
> * **Paso 1.** `capture.py` encola `(t0, fuente, audio, t_ini)`; `TextPipeline.process()` devuelve
>   además el desfase de la primera palabra clave, interpolado por carácter dentro de su segmento
>   (`hit_offset`), y el worker calcula `t_hit = t_ini + desfase`. `t_ini` es la hora de llegada
>   del primer frame menos lo que dura un frame (~21 ms a 48 kHz).
> * **Paso 2.** `grab_image(pantalla, ventana)` en `screenshot.py`; `take_screenshot` la usa.
> * **Pasos 3-4.** `actions/capture_buffer.py`: un fotograma cada 5 s en `caps_dir/.buffer/<hora>`
>   mientras «hay reunión». Se cuenta como reunión el arranque o **el último fragmento de audio**
>   encolado hace menos de 15 min, no el último frame con nivel: el ruido de un jack sin
>   micrófono pasa el umbral en frames sueltos y el buffer no habría parado nunca (lo mismo
>   retenía el equipo despierto sin fin; se corrigió también). La purga no es `t0 - intervalo`
>   sino `t_ini - 40 s`: un fragmento posterior en la cola puede empezar hasta 20 s (`MAX_SEC`)
>   antes que el actual y pedir un fotograma a dos intervalos.
> * **Paso 5.** `take()` mueve el fotograma más cercano a `t_hit` (a menos de 2 intervalos) al
>   nombre final `AAAA-MM-DD_HH-MM-SS_clave.jpg` con la hora `t_hit`, sin recomprimir. Si no hay,
>   captura inmediata anotada `· tardía, +N min` cuando llega más de 5 s tarde. El enlace solo se
>   escribe si el archivo existe en disco.
> * **Paso 6.** El enfriamiento de 15 s compara `t_hit` (en valor absoluto: dos fuentes pueden
>   llegar desordenadas).
> * **Pasos 7-8.** `captures` en `config.json` (`off`, `light`, `normal` por defecto, `high`; otro
>   valor cae a `normal` al cargar) y un desplegable «Capturas por palabra clave» en ⚙ Opciones y en
>   `daily config` (sección Capturas; `--ver` lo muestra). La captura manual sigue siendo PNG
>   instantáneo, en su propio hilo, al margen del buffer.
> * **Paso 9.** Reunión de prueba: resultados en `docs/auditoria-daily-2026-09-25.md`, sección 4.
>
> Además, con el buffer, el hilo de transcripción ya no llama a `PrintWindow` salvo en el plan B,
> y `PrintWindow` solo se llama si la ventana atiende un mensaje en 1 s (`responsive()`): una
> ventana colgada no puede volver a parar la transcripción.
>
> **Dónde vive.** El buffer lo arranca, rearranca (si ⚙ Opciones cambia la carpeta o la calidad) y
> para `RecorderSession` (`recorder/session.py`), la sesión sin interfaz que comparten la ventana y
> `daily` en la terminal; «hay reunión» se decide con el último fragmento encolado por el gestor de
> audio (`AudioCaptureManager.last_chunk_at`). Así el comportamiento es el mismo en los dos
> frontales y se prueba sin pantalla (`tests/test_session.py`, `TestBufferDeCapturas`).
>
> **Ajustes tras la evaluación de la rama (14-OCT-2026):**
>
> * **Calidad.** Hasta la auditoría, cada captura por palabra clave era un PNG sin pérdida. El
>   primer buffer guardaba `normal` como JPEG 70 con submuestreo de color 4:2:0, peor que antes para
>   el texto pequeño. Ahora `normal` es **JPEG 85 sin submuestreo (4:4:4)**, `light` reduce a media
>   resolución con **LANCZOS** (sin filtro, Pillow usa el vecino más próximo y el texto se rompe) y
>   `high` sigue siendo **PNG, idéntico a la captura de siempre**. Quien venga de una versión anterior
>   y quiera exactamente lo de antes, elige `high`. Un valor de `captures` que no sea ninguno de los
>   cuatro vale como `normal` (nunca apaga el buffer en silencio); un `config.json` sin el campo, igual.
> * **Medido** (pantalla entera a 2560×1440 con un escritorio cargado, 12 fotogramas/min, sin
>   Whisper; una ventana de Teams sola ocupa mucho menos): `light` 125 KB/img, ~88 MB/h, ~2,3 % de un
>   núcleo (el LANCZOS cuesta); `normal` nuevo 673 KB/img, ~470 MB/h, ~1,7 % (82 ms por fotograma:
>   52 de captura y 30 de guardado); `normal` viejo (JPEG 70) 372 KB/img, ~260 MB/h, ~1,3 %; `high`
>   625 KB/img, ~440 MB/h, ~3,1 %. En otra pantalla (60 s, misma resolución, otro contenido) el
>   evaluador midió el viejo `normal` en 0,83 % de CPU, 340 KB/img y 225 MB/h; `light` 1,25 %, 114 KB
>   y 75 MB/h; `high` 2,19 %, 537 KB y 355 MB/h; ~11-12 fotogramas/min y +4,4 MB de RSS, estable. Las
>   cifras cambian con lo que haya en pantalla; las de la tabla de abajo son las del plan original.
> * **Retención y privacidad.** El buffer no guarda nada hasta el **primer fragmento de audio** (antes
>   capturaba 15 min desde el arranque aunque no hubiera reunión, y continuar tras una pausa tampoco
>   lo arranca), y su propio hilo borra en cada vuelta, haya reunión o no, lo más viejo que
>   `RETENTION_SEC` (15 min): la pantalla no se queda en disco por el hecho de que el transcriptor no
>   procese nada. El worker sigue purgando por delante de lo que transcribe. `stop()` vacía la carpeta.
>   Si la transcripción fuera más de 15 min atrasada, la captura cae al plan B (inmediata, `tardía`).
> * **Fallos.** El primer fallo del buffer (la unidad de la carpeta de capturas no está, la pantalla no
>   se deja leer) se escribe en la nota y sale en el visor de la ventana y de la terminal
>   (`⚠ el buffer de capturas falló (…)`); los siguientes solo cuentan en `errors`.

**Veredicto: buffer circular de capturas JPEG/PNG, no vídeo.** Un códec de vídeo solo compensa a decenas de fotogramas por segundo; a un fotograma cada pocos segundos el coste real es la captura de pantalla, no la codificación, y el buffer ya tiene ese coste medido, respeta la captura de ventana tapada y no añade ningún binario externo.

## El fallo, con precisión

* La hora en que se **dijo** la palabra se puede reconstruir, pero **no con `t0`**. `capture.py` fija `t0 = time.time()` en el primer frame **con voz**, mientras que el buffer de audio empieza antes: acumula desde el primer frame tras cortar el fragmento anterior, incluidos los silenciosos. Whisper devuelve `seg.start` relativo al **inicio del audio**, así que `t0 + seg.start` da un instante **más tardío** que el real, tanto como dure el silencio inicial. La base correcta es la hora del primer frame del buffer, `t_ini`.
* Verificado en `faster-whisper` 1.2.1: con `vad_filter=True` la librería llama a `restore_speech_timestamps`, que devuelve `seg.start` referido al audio original y no al audio ya recortado. Esa parte es fiable.
* Se pierde en dos sitios: `pipeline.process_segments()` devuelve `(texto, hits)` y descarta `seg.start`; y `take_screenshot()` captura y sella con `datetime.now()` al **terminar** de transcribir. Un fragmento dura hasta 20 s, así que ni siquiera `t0` a secas basta: la palabra puede estar 15 s dentro.
* La cola crece: con carga real la transcripción va a 0,33x (`docs/rendimiento.md`), tres segundos de cola por cada segundo de reunión. Cualquier solución tiene que **retener imágenes durante horas**, no minutos. Eso pesa contra grabar la pantalla entera en continuo.

## Comparativa

Leyenda: **M** medido en este equipo (monitor 2560x1440, una captura cada 5 s), **E** estimado con razonamiento, **?** sin verificar.

| Opción | CPU continua | Disco por hora de reunión | Dependencias | Calidad | Ventana tapada (`PrintWindow`) | Privacidad | Complejidad |
| :--- | :--- | ---: | :--- | :--- | :--- | :--- | :--- |
| Hoy: capturar al transcribir | 0 % entre capturas | ~0,3 MB por captura (PNG) | ninguna | PNG | Sí | Solo el instante de cada palabra | — (está roto por el desfase) |
| **Buffer circular JPEG media resolución** | **3,8 % de un núcleo (M)** | **54 MB (M)**, y se purga al transcribir | ninguna (Pillow) | Baja: texto pequeño se pierde | **Sí**, mismo código | 1 imagen/5 s solo mientras hay audio; borrado al vaciar la cola y al cerrar | Baja: ~100 líneas |
| **Buffer circular JPEG calidad 70** | **3,2 % (M)** | **180 MB (M)**, purgado | ninguna | Buena para diapositivas | **Sí** | Igual | Baja |
| **Buffer circular PNG** | **4,9 % (M)** | **316 MB (M)**, purgado | ninguna | Máxima, sin pérdida | **Sí** | Igual | Baja |
| Vídeo `ffmpeg gdigrab` + x264 software | 1080p a 30 fps: **57-70 % de un núcleo y pierde 4-7 % de fotogramas aun con pantalla estática** [1]. A 1-5 fps en 1440p, solo captura y conversión: ~1-3 % / ~5-15 % (E) | ~50-150 MB (E; referencias de 60 y 100 MB/h [2]) | `ffmpeg.exe` (~100 MB) | H.264 4:2:0: texto algo más blando que JPEG q70 (E) | **No**: graba lo visible en pantalla | Todo lo que pase por la pantalla, toda la reunión, en un archivo | Media-alta: proceso hijo, MP4 fragmentado, sincronía |
| Vídeo `ffmpeg gdigrab` + `h264_qsv` (Quick Sync) | Referencia 1080p60: ~20 % frente a 80-90 % con x264 [3]. **La conversión de color y las copias CPU-GPU siguen en CPU** [4]. En este equipo a 1440p y 2 fps: **~3-8 % de un núcleo** (E), es decir, lo mismo que el buffer | ~50-150 MB (E) | `ffmpeg.exe` de gyan.dev o BtbN, que ya traen QSV; el runtime viene con el driver Intel [5] | Igual | **No** | Igual | Igual, más un modo de fallo: QSV falla sin sesión de usuario activa [5] |
| Vídeo Windows Graphics Capture (`windows-capture` de PyPI) | El más barato en teoría (E) | ~50-150 MB (E) | `windows-capture` 2.0.1, wheel `abi3` para Python 3.9 o superior, **debería** cargar en 3.14 (sin probar). **No expone codificador de vídeo en Python**, solo en su versión Rust [6]: haría falta además OpenCV o PyAV | Igual | **Tapada sí, minimizada no** [7], igual que `PrintWindow`. Quitar el borde amarillo exige `IsBorderRequired`, disponible desde la compilación 20348 [8] | Igual | Alta: dependencia nativa nueva más un codificador aparte, API asíncrona, sincronía |

Lo decisivo:

1. **A 0,2 fps el códec no es el cuello.** Las tres filas de vídeo pagan la misma captura por fotograma que el buffer; Quick Sync solo ahorra la parte que a esa frecuencia ya es pequeña. Para que el vídeo aporte algo habría que grabar a muchos fps, que es justo lo que no cabe en esta CPU.
2. **Disco.** A la frecuencia útil (un fotograma cada 2-5 s) el vídeo estático ocuparía menos que el buffer JPEG completo, pero el buffer se purga conforme se transcribe y solo crece mientras hay audio; el vídeo de la reunión entera queda en disco hasta que la cola termina, horas después.
3. **Ventana tapada.** `gdigrab` la pierde; recuperarla obliga a WGC, la opción más compleja. El buffer reutiliza `grab_window()` tal cual.
4. **Privacidad.** Ya ocurrió que una captura recogió una cadena de conexión con contraseña. Una grabación continua guarda todos los fotogramas de toda la pantalla durante toda la reunión (y lo que se abra después mientras vacía la cola). El buffer guarda un fotograma cada pocos segundos, solo mientras hay audio, del objetivo configurado (idealmente la ventana de Teams), y lo borra en cuanto deja de hacer falta.
5. **Sincronía.** Con el buffer, la imagen lleva su propia hora `time.time()` y se elige la más cercana a `t0 + seg.start`: error máximo medio intervalo (2,5 s a 5 s) más el de Whisper. Con vídeo hay que mapear hora de reloj a `pts` del archivo, y cualquier fotograma perdido o pausa desplaza el mapa.

## Plan recomendado

1. **Recuperar el instante de la palabra.** Obligatorio para cualquier opción, en tres partes:
   * `capture.py` encola también `t_ini`, la hora del **primer frame del buffer**, no solo `t0`. Sin esto el instante sale desplazado por el silencio inicial.
   * `process_segments()` devuelve el segmento que contiene la palabra clave, con `start`, `end` y el texto.
   * Un segmento de Whisper es una frase y puede durar más de diez segundos, así que `seg.start` solo no basta con capturas cada cinco. **Por defecto, interpolar sin coste:** `t_hit = t_ini + seg.start + (posición del carácter / longitud del texto) × (seg.end − seg.start)`. El ritmo de habla dentro de una frase es aproximadamente uniforme y el error queda en uno o dos segundos. **Opcional, solo en calidad alta:** `word_timestamps=True` da la hora de cada palabra con resolución de 20 ms, a cambio de un ~10-15 % más de cómputo en una transcripción que ya va justa [9].
   * Ese `t_hit` sella la captura en el nombre de archivo y en la nota.
2. **Separar captura de guardado.** Extraer de `take_screenshot()` una `grab_image(screen_idx, window) -> Image` con la lógica actual (ventana tapada, plan B de pantalla). La usan el buffer y la captura manual.
3. **Hilo del buffer.** Un `threading.Thread` con `Event.wait(intervalo)`: si no hay pausa y se oyó audio hace menos de 15 min (misma política que `power.should_stay_awake`), guarda `grab_image()` en `caps_dir/.buffer/<t>.jpg|png` con `t = time.time()`. Fuera de la reunión no captura nada. API: `nearest(t)`, `purge_before(t)`, `clear()`.
4. **Purga ligada a la cola.** Al empezar cada fragmento el worker llama a `purge_before(t0 - intervalo)`: retención = desfase real, disco acotado por duración de reunión × ritmo (1 h → 54 / 180 / 316 MB según calidad). `clear()` al arrancar y al cerrar.
5. **Sustituir la captura en el worker.** En lugar de `take_screenshot`, `buffer.nearest(t_hit)` y `Path.replace()` al nombre final con la hora `t_hit` y la etiqueta: sin recomprimir. Si no hay imagen (buffer apagado, arranque reciente), plan B: captura inmediata como hoy, anotada como "captura tardía".
6. **Cooldown en tiempo de reunión.** `CAP_COOLDOWN_SEC` pasa a compararse con `t_hit` en vez de con `time.time()`: al vaciar la cola en ráfaga, dos palabras separadas 5 min en la reunión se procesan con segundos de diferencia y hoy se pisarían.
7. **Calidad ajustable y desactivar.** Un campo `captures: str = "normal"` en `AppConfig` y un desplegable en Opciones: `off` (sin hilo, sin capturas automáticas; la manual sigue), `light` (JPEG media resolución, 54 MB/h), `normal` (JPEG q70 completo, 180 MB/h), `high` (PNG, 316 MB/h). Opcional: `capture_interval_sec: int = 5`.
8. **Alta calidad bajo demanda.** Dos vías, ninguna nueva: el nivel `high` del buffer para toda la sesión, y el botón de captura manual, que sigue siendo instantánea y PNG porque ahí sí coincide "ahora" con lo que se ve.
9. **Verificar en una reunión de 10 min** con palabra clave dicha en momentos conocidos: sello de la captura frente a hora real, CPU del hilo del buffer conviviendo con Whisper y tamaño máximo de `.buffer`.

Complementario, no sustituto: reducir el desfase (`cpu_threads`, modelo) según `docs/rendimiento.md` acorta la retención, pero no elimina la necesidad del buffer.

## Sin verificar

* **Nada del vídeo se midió en este equipo.** `ffmpeg` no está instalado y la app estaba transcribiendo una reunión real. Las cifras de vídeo son de terceros o estimadas.
* El ~10-15 % de coste de `word_timestamps` sale de blogs sin metodología publicada.
* Precisión real de `word_timestamps` en español: el dato disponible es de inglés sintético, con F1 de 74,7 en una ventana de 200 ms, es decir, uno de cada cuatro límites de palabra se desvía más de 200 ms [9]. Para capturas cada cinco segundos es de sobra.
* Que la interpolación por posición de carácter quede en uno o dos segundos es una estimación: hay que comprobarla en la reunión de prueba del paso 9.
* Los 3,2-4,9 % de CPU del buffer se midieron aislados, no conviviendo con Whisper a 4-8 hilos.

## Fuentes

1. Medición gdigrab/ddagrab con libx264 y nvenc, Windows 11: <https://qiita.com/aijidokalab/items/2adbc4711d7ab66e8f40>
2. Grabaciones de pantalla estática: <https://lou-kratz.medium.com/compressing-recorded-lectures-with-crf-and-ffmpeg-891a320a44bd> y <https://obsproject.com/forum/threads/is-there-way-to-record-very-small-file-sizes.173303/>
3. Quick Sync frente a x264 en OBS: <https://obsproject.com/forum/threads/high-cpu-usage-on-x264-but-not-quicksync-i-use-a-seperate-streaming-pc.143138/>
4. White paper de Intel sobre QSV y ffmpeg: <https://www.intel.com/content/dam/www/public/us/en/documents/white-papers/cloud-computing-quicksync-video-ffmpeg-white-paper.pdf>
5. Builds de ffmpeg con libvpl: <https://www.gyan.dev/ffmpeg/builds/>; runtime en el driver y fallo sin sesión: <https://github.com/intel/cartwheel-ffmpeg/issues/334>
6. `windows-capture` sin codificador en Python: <https://github.com/NiiightmareXD/windows-capture/issues/152>
7. Windows Graphics Capture con ventanas tapadas y minimizadas: <https://obs-versions.com/blog/obs-window-capture-guide>
8. `IsBorderRequired`: <https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscapturesession.isborderrequired>
9. Marcas de tiempo por palabra, mecanismo y precisión: <https://github.com/openai/whisper/pull/869> y <https://arxiv.org/abs/2408.16589>
