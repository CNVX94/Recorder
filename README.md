# 🎙️ Recorder · Live Audio Transcriber & Daily Notes Assistant

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-faster--whisper-orange.svg)](https://github.com/SYSTRAN/faster-whisper)
[![Architecture](https://img.shields.io/badge/architecture-modular%20clean-green.svg)](docs/architecture.md)

**Recorder** es una herramienta de escritorio ligera y modular para Windows que transcribe en tiempo real tanto la salida de audio de tu equipo (reuniones en Teams, Meet, Zoom, llamadas o vídeos) mediante **WASAPI Loopback**, como tu propio micrófono. Genera automáticamente un archivo `.md` con marcas de tiempo, capturas de pantalla automáticas en tus monitores ante palabras clave y cuenta con un sistema interactivo de **calibración anti-alucinaciones y léxico personal**.

---

## ✨ Características Principales

* 🔊 **Captura de Salida + Micrófono (WASAPI Loopback):** Captura el audio de tus reuniones sin necesidad de cables virtuales (Virtual Audio Cable). Muestra medidores de nivel de volumen en vivo (`🔊 █░   🎤 █░`).
* ⚡ **Transcripción Rápida con IA (faster-whisper):** Ejecución eficiente en CPU mediante cuantización `int8` (modelos `tiny`, `base`, `small`, `medium`, `large-v3-turbo`), en GPU NVIDIA con CUDA, o en GPU AMD con whisper.cpp y Vulkan ([docs/gpu-amd-vulkan.md](docs/gpu-amd-vulkan.md)).
* 📸 **Capturas de Pantalla Automáticas:** Al escuchar palabras clave configuradas (*"bloqueo"*, *"pendiente"*, *"captura"*, etc.), toma una captura de todas las pantallas, de un monitor o **solo de la ventana de una aplicación** (p. ej. Teams, aunque esté tapada por otras ventanas) y la incrusta directamente en el archivo Markdown.
* 🎯 **Fine-Tuning Anti-Alucinaciones & Léxico Personal:**
  * **Filtro de Silencios / Ruido:** Descarte automático de fórmulas típicas de YouTube (*"suscríbete"*, *"amara.org"*, etc.).
  * **Anti-Bucles:** Detector de repeticiones continuas mediante análisis de compresión zlib (`compression_ratio`).
  * **Diccionario Fonético:** Sustituciones automáticas para jerga técnica o siglas de tu equipo (`cuba` ➔ `QA`, `ayayas` ➔ `IIS`).
  * **🧪 Sandbox en Vivo:** Prueba tus reglas interactivamente en la interfaz antes de guardarlas.
* 🧹 **Reagrupar notas (📑):** Genera copias ordenadas por hora y agrupadas por tramos de reloj (5, 15, 30 o 60 min), con las líneas del mismo turno unidas en párrafos que conservan su `[HH:MM]`, sin ecos del vocabulario y, por defecto, en texto puro (sin imágenes ni indicadores de captura; se pueden conservar desmarcando la casilla; descartar las líneas cortas es opcional, porque se lleva respuestas como «Sí, va.»). **No resume**: el texto es el de la transcripción, y la cabecera de cada copia lo dice. **Nunca modifica la nota original**: cada copia es un archivo nuevo (`…_reagrupada-1h.md`) que registra de qué original salió.
* 📝 **Salida Markdown Atómica:** Genera un archivo diario (ej: `daily_2026-09-08_14-30.md`) con soporte para pausar (`⏸`), reanudar (`▶`) y trasladar la carpeta de notas en caliente.
* 🎧 **Resistente a auriculares y suspensión:** Si una fuente de audio se cae (auriculares desconectados, equipo que despierta), se reabre sola con reintentos mientras la otra sigue; el medidor lo muestra (`🔊 ⛔ reintento 3`). Mantiene el equipo despierto solo mientras hay trabajo (`☕`) y, al cerrar con fragmentos pendientes, avisa de cuántos minutos faltan y deja terminar. Ver [Auriculares, suspensión y cierre](#-auriculares-suspensión-y-cierre).

---

## 🚀 Instalación y Requisitos

📘 [Guía de instalación rápida](docs/instalacion.md): instalador de un clic (`install.bat`) que deja todo listo, sin pasos manuales.

📦 Sin Python: [docs/empaquetado.md](docs/empaquetado.md) explica cómo construir `Recorder.exe`, `daily.exe` y el instalador de Windows (`packaging\build.ps1`), qué llevan dentro y cómo publicar una versión.

1. **Requisitos:**
   * Windows 10 o Windows 11.
   * Python 3.10 o superior.

2. **Instalar dependencias:**
   ```powershell
   pip install faster-whisper pyaudiowpatch pillow numpy
   ```

3. **Configurar el atajo rápido `daily` en PowerShell:**
   Para abrir la aplicación escribiendo simplemente `daily` desde cualquier terminal, agrega esta función a tu perfil de PowerShell (`notepad $PROFILE`):
   ```powershell
   function daily { python "$HOME\Documents\GitHub\Recorder\recorder.py" $args }
   ```

4. **Crear tu configuracion a partir de la plantilla:**
   ```powershell
   Copy-Item config.example.json config.json
   ```

---

## ⚙️ Configuracion

Toda la configuracion vive en `config.json`, en la raiz del proyecto. **Ese archivo esta en `.gitignore` y nunca se sube**, porque guarda tu vocabulario, tus rutas y tus dispositivos. Lo que si se publica es `config.example.json`, una plantilla generica que puedes copiar. Con Recorder **instalado** como ejecutable (`Recorder.exe` / `daily.exe`) el archivo esta en `%APPDATA%\Recorder\config.json` y se crea solo en el primer arranque; la variable de entorno `RECORDER_CONFIG` apunta a otro `config.json` en los dos casos (ver [docs/architecture.md](docs/architecture.md), §2.8).

Una vez copiada, editala desde la propia aplicacion con los botones ⚙️ Opciones y 🎯 Calibrar. No hace falta tocar el JSON a mano.

La plantilla omite a proposito `notes_dir` y `caps_dir`. Al faltar esos campos, la aplicacion usa tu carpeta `Documentos\Dailies`. Anadelos solo si quieres otra ubicacion.

### Configuración según tu equipo

Recorder detecta el equipo en medio segundo (CPU y sus núcleos P/E, AVX2, RAM, batería, GPUs con su VRAM real) y propone la calidad, el motor y los hilos que le convienen, con el motivo: una NVIDIA de 6 GB o más va a **Extra**; una GPU AMD/Intel con whisper.cpp, a `large-v3-turbo` en la GPU; sin GPU, **Alta**, **Media** o **Baja** según la CPU (una gama menos con batería). El instalador y el primer arranque la aplican solos; después está en ⚙ Opciones (**Usar recomendado**), y al arrancar se avisa si tu configuración es más pesada que la recomendada o si hay una GPU dedicada sin `whispercpp_dir`. Para verla en la consola: `python recorder.py --recomendar` (con `--aplicar` la guarda). Detalle, umbrales y medidas: [docs/recomendacion-hardware.md](docs/recomendacion-hardware.md).

| Campo | Que hace |
| :--- | :--- |
| `vocab` | Contexto que se le pasa a Whisper antes de oir. Aqui van los terminos y nombres de tu equipo. Es lo que mas mejora la transcripcion. Escribelo como frase o lista **sin rotulos** (`Terminos:`, `Nombres del equipo:`): Whisper los repite en los silencios ([docs/anti-hallucination-tuning.md](docs/anti-hallucination-tuning.md), seccion D). |
| `keywords` | Palabras que disparan una captura de pantalla. Evita muletillas: *este* se ignora siempre (disparo 60 de 212 capturas en una daily); *aqui* y *ahi* disparan mucho. |
| `captures` | Capturas automaticas por palabra clave: `off`, `light` (JPEG a media resolucion), `normal` (por defecto: JPEG 85 sin submuestreo de color, texto nitido) o `high` (PNG sin perdida, la captura de siempre). Salen de un buffer con una imagen cada 5 s desde el primer audio de la reunion, asi que la captura es la del momento en que se dijo la palabra aunque la transcripcion vaya atrasada; nada queda en el buffer mas de 15 min ni al cerrar ([docs/captura-diferida.md](docs/captura-diferida.md)). Se elige en ⚙ Opciones o en `daily config`; un valor que no sea uno de esos cuatro cae a `normal`. **Ojo si vienes de una version anterior:** las capturas automaticas pasan de PNG a JPEG salvo con `high`. |
| `echo_filter` | Filtro del eco del vocabulario (`true` por defecto): quita los rotulos del `vocab` pegados a una frase y descarta los renglones que solo recitan el vocabulario; nunca toca nada si `vocab` esta vacio. Se apaga en 🎯 Calibrar o `daily calibrar` si se sospecha que se lleva frases reales. |
| `fixes` | Sustituciones palabra por palabra tras transcribir, para lo que Whisper confunda siempre igual. |
| `ignore` | Frases fantasma que Whisper inventa en los silencios. La lista de fabrica cubre las mas comunes en espanol. |
| `model` | Modelo de Whisper. `small` va en tiempo real en un portatil sin GPU; `medium` es mas preciso pero se retrasa. |
| `cpu_threads` | Hilos de CPU para la inferencia. `0` deja el valor de faster-whisper (4), que desaprovecha una CPU con mas nucleos. El instalador y el primer arranque ponen el recomendado para tu CPU (en una híbrida cuentan los núcleos P); se cambia en ⚙ Opciones. Como medir el mejor valor en tu equipo: [docs/rendimiento.md](docs/rendimiento.md). |
| `device`, `compute_type` | Dónde corre el modelo. `cpu`/`int8` sin GPU; `gpu`/`float16` usa CUDA si hay NVIDIA y si no whisper.cpp con Vulkan (AMD); `cuda` y `vulkan` fuerzan uno. Lo fija el preset elegido en ⚙ Opciones o **Usar recomendado**. |
| `whispercpp_dir`, `whispercpp_flash_attn`, `whispercpp_device` | Carpeta de whisper.cpp compilado con Vulkan (`tools\instalar_whispercpp.ps1` la escribe sola), si usa *flash attention* y qué GPU usa (`-1` = la dedicada con más VRAM, nunca la integrada; un número la fuerza). Se eligen en ⚙ Opciones. Para GPU AMD/Intel: [docs/gpu-amd-vulkan.md](docs/gpu-amd-vulkan.md). |
| `screen` | Monitor del que se captura. `0` son todas las pantallas juntas. |
| `window` | Título de la ventana de aplicación que se captura en lugar de la pantalla (vacío = usar `screen`). Se elige desde ⚙ Opciones. |
| `no_speech_threshold`, `logprob_threshold`, `compression_ratio_threshold` | Umbrales anti-alucinaciones. Se ajustan desde 🎯 Calibrar, que ademas trae un sandbox para probarlos. |

### Capturar solo una ventana (p. ej. Teams)

En ⚙ Opciones, el selector **Qué capturar 📸** lista, además de las pantallas, las ventanas abiertas (`Ventana: Reunión semanal | Microsoft Teams`). El botón 🔄 vuelve a leer la lista. Al elegir una ventana:

* Se captura **solo esa ventana, aunque esté tapada por otras o en otro monitor**, sin traerla al frente ni robar el foco (`PrintWindow` con `PW_RENDERFULLCONTENT`). Puedes seguir trabajando en el resto de monitores.
* Se guarda su título en `window`. Como Teams cambia el título con cada chat o reunión, al capturar vale cualquier ventana abierta de la **misma aplicación** (el último tramo del título: `Microsoft Teams`); si hay varias, la que esté más arriba.
* Si la ventana **no está abierta o está minimizada**, se captura lo que diga `screen` (todas las pantallas o el último monitor elegido). Nunca falla ni interrumpe la transcripción.
* Algunas ventanas no se dejan dibujar así y salen en negro. En ese caso se recorta lo que haya visible en su rectángulo de pantalla (si otra ventana la tapa, saldrá esa).

---

## 💻 Modos de Uso

### 1. Iniciar la Aplicación

* **Desde la terminal (`daily`):** graba ahí mismo, sin abrir la ventana. Las frases van saliendo con su hora (🎤 las del micrófono; debajo, `📸 captura: …` si dispararon una captura), igual que los avisos de la sesión (las fuentes de audio resueltas al arrancar, una fuente caída o muda, el atraso de la transcripción) y se quedan en el historial de la terminal; al pie, tres líneas con el estado, los medidores `🔊 🎤` (con `⛔` si una fuente cayó y `🔇` si lleva 10 min muda) y las teclas: `p` pausar/continuar, `c` captura, `r` reconectar audio, `a` abrir la nota, `q` salir (Ctrl+C también). Si al salir quedan fragmentos por transcribir, pregunta en el mismo pie: `e` esperar a que terminen, `s` salir perdiéndolos, `c` cancelar. En silencio no gasta CPU: solo se redibuja lo que cambia.
  ```powershell
  daily                 # grabar en la terminal
  daily menu            # menú numerado: grabar, opciones, calibrar, reagrupar nota, recomendación, ventana
  daily config          # ⚙ Opciones por secciones (también la calidad de las capturas por palabra clave); guarda al confirmar
  daily config --ver    # la configuración actual (--editor abre config.json; --recomendado aplica la del equipo)
  daily calibrar        # 🎯 Calibrar: vocabulario, frases a ignorar, correcciones, umbrales y sandbox
  daily calibrar --probar "frase"   # ¿pasaría los filtros? (sale con 0 si se acepta, 1 si se descarta o es eco del vocab)
  daily sintesis        # elige una nota y genera su copia reagrupada (no resume); el original no se toca
  daily sintesis nota.md --cada 15 --si   # lo mismo sin preguntas; por defecto texto puro y sin ecos, como la ventana
                        # (--sin-unir, --con-horas, --con-imagenes, --sin-cortas, --con-ecos invierten las casillas)
  daily recomendar      # equipo detectado y configuración recomendada (--aplicar la guarda)
  daily ventana         # la ventana de siempre (igual que daily --gui)
  daily --ascii         # símbolos ASCII (en la consola clásica, conhost, se detecta solo)
  daily -h              # todos los subcomandos
  ```
  Con la salida redirigida (`daily > log.txt`) no hay pie ni colores: una línea por frase, y los cambios de estado también como líneas.
* **La ventana:** `daily --gui` o `daily ventana`. Es también lo que se abre cuando no hay consola (`pythonw`, un ejecutable de ventana).
* **O directamente con Python:**
  ```powershell
  python recorder.py    # igual que daily
  # O bien como módulo:
  python -m recorder
  ```

### 2. Controles de la Ventana

* **📸 Captura:** Toma una captura manual instantánea del objetivo configurado (pantallas, monitor o ventana) y la anota en el Markdown.
* **⚙ Opciones:** Permite elegir la carpeta de notas, la carpeta de capturas, los dispositivos de audio WASAPI (altavoces/micrófono), qué capturar (pantallas, un monitor o una ventana), la calidad de las capturas automáticas por palabra clave (o apagarlas), la calidad de transcripción (con la **recomendada para este equipo** y su motivo), los hilos de CPU y, para una GPU AMD/Intel, la carpeta de whisper.cpp, la GPU y *flash attention*. Si cambias la carpeta de notas en plena reunión, la nota se mueve y sus enlaces a capturas se reescriben para seguir funcionando.
* **📑 Reagrupar:** Genera una copia ordenada y agrupada de una nota, sin tocar el original ([docs/sintesis-de-notas.md](docs/sintesis-de-notas.md)).
* **🎯 Calibrar:** Abre el panel de fine-tuning para ajustar el prompt de contexto (sin rótulos: el sandbox marca como eco lo que solo repite el vocabulario), la lista negra de alucinaciones, el diccionario fonético y probar frases en el sandbox.
* **⏸ Pausar / ▶ Continuar:** Suspende la toma de notas durante pausas de la reunión sin cerrar el archivo diario.
* **Clic en los medidores `🔊 🎤`:** Reabre las dos fuentes de audio al momento con los dispositivos configurados (plan B si un flujo se queda mudo sin dar error).
* **Cerrar la ventana:** Si quedan fragmentos por transcribir, pregunta cuántos minutos de audio faltan y deja elegir entre esperar a que terminen o salir perdiéndolos.

---

## 🎧 Auriculares, suspensión y cierre

Con `large-v3-turbo` en un portátil sin GPU la transcripción va al ritmo justo del tiempo real, y en una reunión larga la cola de fragmentos pendientes puede crecer hasta decenas de minutos de audio en memoria. Tres mecanismos protegen ese trabajo.

### Si se cae una fuente de audio (auriculares desconectados, dispositivo que desaparece)

Cada fuente (🔊 salida y 🎤 micrófono) vive en su propio hilo y **se recupera sola**: al morir el flujo, lo que había grabado a medias se encola igual, y la fuente se reintenta con espera creciente (1, 2, 4, 8, 16 y luego cada 30 s) hasta que el dispositivo vuelve. La otra fuente sigue trabajando mientras tanto, y la cola pendiente no se toca nunca por un problema de dispositivo.

En la cabecera se ve de un vistazo: el medidor pasa de `🔊 ████░░░░` a `🔊 ⛔ reintento 3` mientras está caída, y vuelve a las barras en cuanto lee audio otra vez. Además queda una línea con hora en la ventana y en la nota (`> ⚠ audio de salida caído…` / `> ✔ audio de salida recuperado`), para saber por qué hay un hueco.

Una fuente también puede estar **sin audio sin estar caída**: el flujo lee, pero nada llega a formar un fragmento (está silenciada, el micrófono elegido no es el que usa Teams, o es un jack sin micrófono conectado). Si una fuente lleva 10 minutos sin audio mientras la otra sí suena, el medidor muestra `🎤 ░░░░░░░░ 🔇` (en la ventana y en el pie de la terminal) y la nota y el visor lo dicen de forma neutra (`> ⚠ sin audio de micrófono 🎤 desde hace 10 min (¿silenciado?; la salida 🔊 sí suena)…`), una vez por episodio, y otra al volver a haber audio. El plazo cuenta desde el arranque o desde la última vuelta de una pausa; desactivar el micrófono en Opciones retira el aviso sin más. Al arrancar, la nota y el visor apuntan además qué dispositivo resolvió cada fuente (`> Fuentes: 🔊 … · 🎤 …`).

Límites que conviene conocer:

* PortAudio lee la lista de dispositivos **al arrancar**. Desconectar y volver a conectar el mismo dispositivo se recupera solo; pero un dispositivo que **no existía al abrir Recorder**, o cambiar el predeterminado de Windows a **otro** distinto, exige reiniciar Recorder (o elegirlo a mano en ⚙ Opciones si ya estaba en la lista).
* Si tras despertar de una suspensión un flujo se queda mudo **sin dar error** (no es lo habitual, pero puede pasar), el reintento automático no salta porque no hay fallo que lo dispare. Haz **clic en los medidores** `🔊 🎤`: reabre las dos fuentes al momento.

### Suspensión por inactividad y cierre de la tapa

Mientras hay trabajo (se está oyendo algo, o quedan fragmentos por transcribir), Recorder pide a Windows que **no suspenda el equipo por inactividad** (`SetThreadExecutionState`) y lo indica con `☕` en la cabecera. No es permanente: se suelta cuando la cola está vacía y llevan 15 minutos sin ningún fragmento de audio (contados desde el arranque o desde audio real; continuar tras una pausa no reinicia el plazo), o en pausa (⏸) sin cola. (Cuenta fragmentos y no nivel: el ruido de un jack sin micrófono pasa el umbral en instantes sueltos y antes retenía el equipo sin fin.) Así un Recorder olvidado abierto no deja el portátil encendido toda la noche. La pantalla sí puede apagarse; solo se retiene el sistema.

**Cerrar la tapa no lo puede impedir ninguna aplicación**: es una directiva de energía de Windows. Si quieres cerrar la tapa y que Recorder siga transcribiendo, configura que al cerrarla no pase nada:

* Interfaz: *Panel de control → Opciones de energía → Elegir el comportamiento del cierre de la tapa → "No hacer nada"* (con batería y enchufado).
* O en PowerShell **como administrador** (`0` = no hacer nada; `ac` = enchufado, `dc` = batería):
  ```powershell
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
  powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
  powercfg /setactive SCHEME_CURRENT
  ```
  Para comprobar que Recorder está reteniendo el equipo, `powercfg /requests` (también como administrador) lista `python.exe` bajo `SYSTEM`.

Si el equipo se suspende o hiberna igualmente (tapa, botón, o inactividad con la app en pausa), al despertar las fuentes se reabren solas por el mismo mecanismo de reintento, y la cola pendiente sigue donde estaba: vive en memoria y una suspensión no la pierde. Lo que sí la pierde es que el proceso muera (apagado, cierre de sesión, fallo de Python). No se vuelca a disco a propósito: serían cientos de MB de audio escritos mientras la CPU ya va justa transcribiendo, para cubrir un caso raro.

### Cerrar la ventana con fragmentos pendientes

Al cerrar con cola pendiente, Recorder dice cuántos fragmentos y cuántos minutos de audio quedan, y da a elegir:

* **Sí**: deja de capturar, sigue transcribiendo lo pendiente (cabecera `⏳ Terminando 212 fragmentos (~48 min de audio)…`) y la ventana se cierra sola al acabar. El equipo se mantiene despierto mientras tanto.
* **No**: sale ahora y pierde esos fragmentos.

Con la cola vacía cierra directamente, como siempre.

### Cuando la transcripción va atrasada

Si al transcribir un fragmento ya han pasado más de 2 minutos desde que se dijo, la nota lo marca (`> ⏳ transcripción atrasada 5 min desde 10:42:13`) y vuelve a marcarlo cada vez que el atraso se duplica, y una vez al ponerse al día (`> ✔ transcripción al día desde …`). Las capturas no se ven afectadas mientras el buffer tenga el fotograma; si no lo tiene, la captura se toma en el momento y se anota como `tardía, +N min`. Un fragmento o una captura que tarda más de un minuto también queda anotado, para saber dónde se atasca.

---

## 🏛️ Arquitectura del Proyecto

El proyecto está diseñado bajo una arquitectura limpia por capas y un pipeline productor-consumidor concurrente:

```
Recorder/
├── config.example.json             # Plantilla recomendada (esta si se sube)
├── config.json                     # Tu configuracion personal (ignorada por git)
├── recorder.py                     # Entrypoint principal (terminal o ventana) y ejecutor de selftest
│
├── recorder/                       # Paquete principal
│   ├── session.py                  # La sesión de grabación sin interfaz, la misma para ventana y terminal
│   ├── rutas.py                    # Dónde está cada cosa desde el código o instalado (config, docs, logs)
│   ├── registro.py                 # Registro de fallos: excepciones sin atrapar a %LOCALAPPDATA%\Recorder\logs
│   ├── config/                     # Esquemas tipados (AppConfig) y persistencia
│   ├── audio/                      # Captura WASAPI loopback, RMS, decibeles y 16 kHz
│   ├── engine/                     # Trabajador de inferencia faster-whisper
│   ├── filters/                    # Pipeline anti-alucinaciones, zlib, normalizador y léxico
│   ├── actions/                    # Capturas de pantalla DPI-aware y notas Markdown
│   ├── digest/                     # Reagrupar notas: ordena, agrupa y limpia sin tocar el original (no resume)
│   ├── cli/                        # Modo terminal (daily): grabación en vivo, menú y subcomandos
│   └── ui/                         # Interfaz gráfica Catppuccin y diálogos modales
│
├── docs/                           # Documentación técnica
│   ├── architecture.md             # Especificación detallada de arquitectura
│   ├── anti-hallucination-tuning.md# Guía completa de fine-tuning y alucinaciones
│   ├── plan-fase-2.md              # Plan de la Fase 2 (modularizacion) - completada
│   ├── plan-fase-3.md              # Plan de la Fase 3 (identificar participantes)
│   └── sintesis-de-notas.md        # Como se agrupan y limpian las notas
│
└── tests/                          # Suite de pruebas unitarias
    ├── test_audio_processing.py    # Pruebas de DSP y señales
    ├── test_audio_recovery.py      # Reapertura de fuentes caídas, cierre con cola y equipo despierto
    ├── test_config.py              # Pruebas de configuración
    ├── test_hardware.py            # Detección de CPU, RAM, energía y GPUs con datos sintéticos
    ├── test_recommendation.py      # Configuración recomendada por gama y elección de GPU Vulkan
    └── test_filters_and_lexicon.py # Pruebas de filtros y sustituciones
```

Para más detalles, consulta la documentación en la carpeta [docs/](docs/):
* 📖 [docs/architecture.md](docs/architecture.md): Diagramas de flujo y detalle de cada subsistema.
* 🎯 [docs/anti-hallucination-tuning.md](docs/anti-hallucination-tuning.md): Cómo se producen las alucinaciones en Whisper y cómo calibrarlas.
* 🖥️ [docs/recomendacion-hardware.md](docs/recomendacion-hardware.md): Qué detecta Recorder de tu equipo, cómo elige la configuración recomendada y qué GPU usa whisper.cpp.
* 🎚️ [docs/presets-calidad.md](docs/presets-calidad.md): Los presets Baja, Media, Alta y Extra, y qué pasa si se pide GPU y no la hay.
* ⚡ [docs/rendimiento.md](docs/rendimiento.md): Qué hace lenta la transcripción en CPU, qué palancas hay y cómo medirlas en tu equipo (`tools/medir_rendimiento.py`).
* 🎮 [docs/gpu-amd-vulkan.md](docs/gpu-amd-vulkan.md): Transcribir en una GPU AMD (Radeon) con whisper.cpp y Vulkan: instalación, medidas y límites.
* 🗺️ [docs/plan-fase-3.md](docs/plan-fase-3.md): Plan para identificar a cada participante por su voz.
* 🧹 [docs/sintesis-de-notas.md](docs/sintesis-de-notas.md): Como generar copias reagrupadas (ordenadas y limpias, no resumidas) de una nota sin tocar nunca el original.
* 🔍 [docs/auditoria-daily-2026-09-25.md](docs/auditoria-daily-2026-09-25.md): Auditoría de una daily real (capturas tardías o perdidas, eco del vocabulario, micrófono mudo) y lo que se cambió.
* 📸 [docs/captura-diferida.md](docs/captura-diferida.md): El buffer circular de capturas: por qué la imagen es la del momento en que se dijo la palabra.

---

## 🧪 Pruebas y Validación

El proyecto incluye dos niveles de verificación:

1. **Selftest Rápido (integrado en `recorder.py`):**
   ```powershell
   daily --selftest
   # o
   python recorder.py --selftest
   ```

2. **Suite Completa de Pruebas Unitarias:**
   ```powershell
   python -m unittest discover -s tests -t .
   ```

3. **Qué detecta en tu equipo y qué recomienda** (no cambia nada; con `--aplicar` lo guarda en `config.json`):
   ```powershell
   python recorder.py --recomendar
   ```
