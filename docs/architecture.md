# Arquitectura del Sistema - Recorder (Fase 2)

Este documento describe la arquitectura modular de **Recorder**, diseñada para la captura de flujos de audio en tiempo real, transcripción automática mediante Inteligencia Artificial (Whisper), filtrado avanzado anti-alucinaciones y generación de notas con capturas de pantalla automáticas.

---

## 1. Visión General

El sistema sigue una arquitectura por capas desacoplada (**Clean Architecture**) combinada con un **Pipeline Productor-Consumidor Concurrente**.

```mermaid
flowchart TD
    subgraph AudioLayer ["1. Ingesta de Audio (audio/)"]
        WASAPI_Out["WASAPI Loopback (Audio Sistema / Teams)"] --> CaptureOut["Capture Thread (Out)"]
        WASAPI_Mic["WASAPI Mic (Voz Usuario)"] --> CaptureMic["Capture Thread (Mic)"]
        CaptureOut --> Segmenter["Segmentación VAD (RMS / Silencios)"]
        CaptureMic --> Segmenter
        Segmenter --> AudioQueue[("Queue[AudioChunk]")]
    end

    subgraph EngineLayer ["2. Inferencia IA (engine/)"]
        AudioQueue --> TranscribeWorker["TranscriberWorker Thread"]
        TranscribeWorker --> WhisperModel["faster-whisper (int8 / CPU)"]
        WhisperModel --> RawSegments[("Transcription Segments")]
    end

    subgraph FiltersLayer ["3. Pipeline Anti-Alucinaciones (filters/)"]
        RawSegments --> QualityFilter["1. Filtro Heurístico (no_speech & logprob)"]
        QualityFilter --> RepetitionFilter["2. Detector de Bucles (compression_ratio zlib)"]
        RepetitionFilter --> BlacklistFilter["3. Lista Negra (Frases Fantasma / YouTube)"]
        BlacklistFilter --> LexiconFilter["4. Diccionario de Reemplazos (Fixes)"]
        LexiconFilter --> KeywordFilter["5. Detector de Palabras Clave (Keywords)"]
    end

    subgraph ActionsLayer ["4. Persistencia y Automatización (actions/)"]
        KeywordFilter --> ScreenshotService["Capturas DPI-Aware (screenshot.py)"]
        KeywordFilter --> NotesSession["Notas Diarias Markdown (notes.py)"]
    end

    subgraph PresentationLayer ["5. Interfaz de Usuario (ui/)"]
        NotesSession --> UIQueue[("Queue[UIEvent]")]
        UIQueue --> MainWindow["Ventana Principal (Catppuccin UI)"]
        MainWindow --> SettingsDialog["⚙ Opciones Generales"]
        MainWindow --> TuningDialog["🎯 Calibración Anti-Alucinaciones & Sandbox"]
        TuningDialog -.->|Actualiza en caliente| FiltersLayer
    end
```

---

## 2. Descripción de Componentes

### 2.1. Ingesta y Audio (`recorder/audio/`)
* **`devices.py`**: Interfaz con `pyaudiowpatch` para consultar la API WASAPI de Windows. Resuelve dispositivos físicos de entrada (micrófono) y dispositivos virtuales de loopback (altavoces/auriculares para escuchar a otros participantes).
* **`processing.py`**: Funciones puras de procesamiento digital de señales:
  * `rms(pcm)`: Cálculo de valor cuadrático medio para niveles de volumen.
  * `bars(rms)`: Conversión a escala logarítmica (-60 dB a 0 dB) representada en bloques `█░`.
  * `to_16k(pcm, rate, channels)`: Remuestreo y mezcla a mono en formato `float32` a 16.000 Hz.
* **`capture.py`**: Gestiona los hilos de lectura continuos. Segmenta el audio detectando silencios entre frases (`PAUSE_SEC = 0.6s`) o al alcanzar un máximo de tiempo (`MAX_SEC = 20s`). Cada fuente vive en su propio hilo (`capture_thread`) que abre el flujo, lee hasta que muere y lo **reabre con espera creciente** (`retry_delay`: 1, 2, 4… hasta 30 s), resolviendo el dispositivo de nuevo en cada intento; al morir el flujo, lo grabado a medias se encola igual. El gestor (`AudioCaptureManager`) expone `attempts` (0 = viva, n = reintento n) y avisa por `source_callback` cuando una fuente cae o vuelve; `meter_label` y `pending_summary` son las políticas puras que la interfaz pinta. Cada `start()` lleva su propio `Event` de parada, de modo que `restart()` no resucita hilos del arranque anterior. PortAudio enumera dispositivos solo al inicializar: se reabre el mismo dispositivo, no se sigue un cambio del predeterminado a otro distinto.

### 2.2. Motor de Inferencia (`recorder/engine/`)
* **`whisper_worker.py`**: Hilo consumidor que procesa los fragmentos de audio (`AudioChunk`) mediante la biblioteca `faster-whisper`.
* Soporta la actualización en caliente del pipeline de filtrado sin necesidad de recargar el modelo de IA de la memoria.

### 2.3. Pipeline Anti-Alucinaciones (`recorder/filters/`)
* **`normalizer.py`**: Normalización Unicode NFKD (descompone caracteres con tildes y convierte a minúsculas).
* **`quality.py`**: Valida métricas internas de inferencia de Whisper (`no_speech_prob`, `avg_logprob`) y calcula el ratio de compresión zlib para evitar bucles repetitivos.
* **`blacklist.py`**: Descarta transcripciones completas si coinciden con patrones típicos de alucinación en silencios.
* **`lexicon.py`**: Aplica un diccionario fonético personal basado en límites de palabra (`\b`) para corregir términos técnicos o nombres propios mal reconocidos.
* **`keywords.py`**: Detecta palabras clave de acción configuradas para disparar capturas.
* **`pipeline.py`**: Encapsula todo el flujo en una clase reutilizable `TextPipeline` y proporciona un método `test_sample()` para pruebas interactivas en la UI.

### 2.4. Automatización y Salida (`recorder/actions/`)
* **`screenshot.py`**: Obtiene coordenadas precisas de cada monitor respetando el escalado DPI de Windows (`ctypes.windll.shcore.SetProcessDpiAwareness(2)`) y captura la pantalla seleccionada con Pillow, o una ventana de aplicación concreta con `PrintWindow` (`PW_RENDERFULLCONTENT`), que la dibuja aunque esté tapada sin traerla al frente. La política de qué ventana abierta corresponde a la guardada en config (`pick_window`: título exacto o misma aplicación) es una función pura; si no hay ninguna o está minimizada, cae a la pantalla configurada, y si `PrintWindow` devuelve negro, recorta lo visible en su rectángulo.
* **`notes.py`**: Mantiene abierta la sesión diaria en un archivo `.md`. Coordina el acceso concurrente mediante un cerrojo (`threading.Lock`) y permite trasladar la carpeta de notas en caliente.
* **`power.py`**: Retiene el equipo despierto (`SetThreadExecutionState` con `ES_SYSTEM_REQUIRED`) mientras hay trabajo. La política `should_stay_awake` es pura: cola pendiente o fragmento en curso, o audio oído hace menos de 15 min sin estar en pausa. No puede impedir el cierre de la tapa (directiva de energía de Windows; ver README).

### 2.5. Presentación Gráfica (`recorder/ui/`)
* Construida en Tkinter con diseño oscuro Catppuccin Mocha.
* **`main_window.py`**: Visor en tiempo real, sondeo de eventos cada 200 ms y medidores de nivel `🔊 █░   🎤 █░` (o `🔊 ⛔ reintento n` si la fuente está caída; clic sobre ellos reabre las fuentes). En cada sondeo decide si retener el equipo despierto (`☕`). Al cerrar con cola pendiente pregunta si esperar: si sí, para la captura, muestra `⏳ Terminando…` y se cierra sola al vaciar la cola.
* **`dialogs/settings_dialog.py`**: Configuración de dispositivos, carpetas y objetivo de captura (pantallas, monitor o ventana de aplicación, con botón 🔄 para releer las ventanas abiertas).
* **`dialogs/tuning_dialog.py`**: Ventana dedicada para calibración de alucinaciones, umbrales y probador en vivo (sandbox).

---

## 3. Modelo de Concurrencia y Flujo de Datos

1. **Hilos de Captura (2)**: Leen audio de baja latencia mediante WASAPI, calculan RMS en cada frame y depositan `AudioChunk` en una cola `chunk_queue`. Cada hilo abre y reabre su propio flujo (las aperturas se serializan con un cerrojo: PortAudio no soporta abrirlas desde dos hilos a la vez) y solo termina cuando se le pide; una fuente caída nunca mata al hilo ni afecta a la otra. Al cerrar la aplicación **no** se llama a `pa.terminate()`: cerraría los streams desde el hilo principal mientras el del loopback sigue bloqueado en `read()`, lo que revienta el proceso (`0xC0000005`); el proceso termina justo después y Windows recoge los recursos.
2. **Hilo de Inferencia (1)**: Espera en `chunk_queue.get()`, realiza la inferencia con Whisper, ejecuta el pipeline de filtros y guarda en el archivo Markdown.
3. **Hilo Principal (GUI)**: Ejecuta el bucle de eventos de Tkinter y sondea la cola `ui_queue` periódicamente, garantizando que la interfaz nunca se congele.
