# 🎙️ Recorder · Live Audio Transcriber & Daily Notes Assistant

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-faster--whisper-orange.svg)](https://github.com/SYSTRAN/faster-whisper)
[![Architecture](https://img.shields.io/badge/architecture-modular%20clean-green.svg)](docs/architecture.md)

**Recorder** es una herramienta de escritorio ligera y modular para Windows que transcribe en tiempo real tanto la salida de audio de tu equipo (reuniones en Teams, Meet, Zoom, llamadas o vídeos) mediante **WASAPI Loopback**, como tu propio micrófono. Genera automáticamente un archivo `.md` con marcas de tiempo, capturas de pantalla automáticas en tus monitores ante palabras clave y cuenta con un sistema interactivo de **calibración anti-alucinaciones y léxico personal**.

---

## ✨ Características Principales

* 🔊 **Captura de Salida + Micrófono (WASAPI Loopback):** Captura el audio de tus reuniones sin necesidad de cables virtuales (Virtual Audio Cable). Muestra medidores de nivel de volumen en vivo (`🔊 █░   🎤 █░`).
* ⚡ **Transcripción Rápida con IA (faster-whisper):** Ejecución eficiente en CPU mediante cuantización `int8` (modelos `tiny`, `base`, `small`, `medium`, `large-v3-turbo`).
* 📸 **Capturas de Pantalla Automáticas:** Al escuchar palabras clave configuradas (*"bloqueo"*, *"pendiente"*, *"captura"*, etc.), toma una captura de todas las pantallas, de un monitor o **solo de la ventana de una aplicación** (p. ej. Teams, aunque esté tapada por otras ventanas) y la incrusta directamente en el archivo Markdown.
* 🎯 **Fine-Tuning Anti-Alucinaciones & Léxico Personal:**
  * **Filtro de Silencios / Ruido:** Descarte automático de fórmulas típicas de YouTube (*"suscríbete"*, *"amara.org"*, etc.).
  * **Anti-Bucles:** Detector de repeticiones continuas mediante análisis de compresión zlib (`compression_ratio`).
  * **Diccionario Fonético:** Sustituciones automáticas para jerga técnica o siglas de tu equipo (`cuba` ➔ `QA`, `ayayas` ➔ `IIS`).
  * **🧪 Sandbox en Vivo:** Prueba tus reglas interactivamente en la interfaz antes de guardarlas.
* 🧹 **Síntesis de Notas:** Genera versiones agrupadas por tramos de reloj (5, 15, 30 o 60 min), con las líneas del mismo turno unidas en párrafos y el relleno corto descartado. **Nunca modifica la nota original**: cada síntesis es un archivo nuevo que registra de qué original salió.
* 📝 **Salida Markdown Atómica:** Genera un archivo diario (ej: `daily_2026-09-08_14-30.md`) con soporte para pausar (`⏸`), reanudar (`▶`) y trasladar la carpeta de notas en caliente.
* 🎧 **Resistente a auriculares y suspensión:** Si una fuente de audio se cae (auriculares desconectados, equipo que despierta), se reabre sola con reintentos mientras la otra sigue; el medidor lo muestra (`🔊 ⛔ reintento 3`). Mantiene el equipo despierto solo mientras hay trabajo (`☕`) y, al cerrar con fragmentos pendientes, avisa de cuántos minutos faltan y deja terminar. Ver [Auriculares, suspensión y cierre](#-auriculares-suspensión-y-cierre).

---

## 🚀 Instalación y Requisitos

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

Toda la configuracion vive en `config.json`, en la raiz del proyecto. **Ese archivo esta en `.gitignore` y nunca se sube**, porque guarda tu vocabulario, tus rutas y tus dispositivos. Lo que si se publica es `config.example.json`, una plantilla generica que puedes copiar.

Una vez copiada, editala desde la propia aplicacion con los botones ⚙️ Opciones y 🎯 Calibrar. No hace falta tocar el JSON a mano.

La plantilla omite a proposito `notes_dir` y `caps_dir`. Al faltar esos campos, la aplicacion usa tu carpeta `Documentos\Dailies`. Anadelos solo si quieres otra ubicacion.

| Campo | Que hace |
| :--- | :--- |
| `vocab` | Contexto que se le pasa a Whisper antes de oir. Aqui van los terminos y nombres de tu equipo. Es lo que mas mejora la transcripcion. |
| `keywords` | Palabras que disparan una captura de pantalla. Evita muletillas como *aqui* o *este*, se dicen constantemente. |
| `fixes` | Sustituciones palabra por palabra tras transcribir, para lo que Whisper confunda siempre igual. |
| `ignore` | Frases fantasma que Whisper inventa en los silencios. La lista de fabrica cubre las mas comunes en espanol. |
| `model` | Modelo de Whisper. `small` va en tiempo real en un portatil sin GPU; `medium` es mas preciso pero se retrasa. |
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

* **Con el comando rápido:**
  ```powershell
  daily
  ```
* **O directamente con Python:**
  ```powershell
  python recorder.py
  # O bien como módulo:
  python -m recorder
  ```

### 2. Controles de la Interfaz

* **📸 Captura:** Toma una captura manual instantánea del objetivo configurado (pantallas, monitor o ventana) y la anota en el Markdown.
* **⚙ Opciones:** Permite elegir la carpeta de notas, la carpeta de capturas, los dispositivos de audio WASAPI (altavoces/micrófono), qué capturar (pantallas, un monitor o una ventana) y el modelo de Whisper.
* **🎯 Calibrar:** Abre el panel de fine-tuning para ajustar el prompt de contexto, la lista negra de alucinaciones, el diccionario fonético y probar frases en el sandbox.
* **⏸ Pausar / ▶ Continuar:** Suspende la toma de notas durante pausas de la reunión sin cerrar el archivo diario.
* **Clic en los medidores `🔊 🎤`:** Reabre las dos fuentes de audio al momento con los dispositivos configurados (plan B si un flujo se queda mudo sin dar error).
* **Cerrar la ventana:** Si quedan fragmentos por transcribir, pregunta cuántos minutos de audio faltan y deja elegir entre esperar a que terminen o salir perdiéndolos.

---

## 🎧 Auriculares, suspensión y cierre

Con `large-v3-turbo` en un portátil sin GPU la transcripción va al ritmo justo del tiempo real, y en una reunión larga la cola de fragmentos pendientes puede crecer hasta decenas de minutos de audio en memoria. Tres mecanismos protegen ese trabajo.

### Si se cae una fuente de audio (auriculares desconectados, dispositivo que desaparece)

Cada fuente (🔊 salida y 🎤 micrófono) vive en su propio hilo y **se recupera sola**: al morir el flujo, lo que había grabado a medias se encola igual, y la fuente se reintenta con espera creciente (1, 2, 4, 8, 16 y luego cada 30 s) hasta que el dispositivo vuelve. La otra fuente sigue trabajando mientras tanto, y la cola pendiente no se toca nunca por un problema de dispositivo.

En la cabecera se ve de un vistazo: el medidor pasa de `🔊 ████░░░░` a `🔊 ⛔ reintento 3` mientras está caída, y vuelve a las barras en cuanto lee audio otra vez. Además queda una línea con hora en la ventana y en la nota (`> ⚠ audio de salida caído…` / `> ✔ audio de salida recuperado`), para saber por qué hay un hueco.

Límites que conviene conocer:

* PortAudio lee la lista de dispositivos **al arrancar**. Desconectar y volver a conectar el mismo dispositivo se recupera solo; pero un dispositivo que **no existía al abrir Recorder**, o cambiar el predeterminado de Windows a **otro** distinto, exige reiniciar Recorder (o elegirlo a mano en ⚙ Opciones si ya estaba en la lista).
* Si tras despertar de una suspensión un flujo se queda mudo **sin dar error** (no es lo habitual, pero puede pasar), el reintento automático no salta porque no hay fallo que lo dispare. Haz **clic en los medidores** `🔊 🎤`: reabre las dos fuentes al momento.

### Suspensión por inactividad y cierre de la tapa

Mientras hay trabajo (se está oyendo algo, o quedan fragmentos por transcribir), Recorder pide a Windows que **no suspenda el equipo por inactividad** (`SetThreadExecutionState`) y lo indica con `☕` en la cabecera. No es permanente: se suelta cuando la cola está vacía y llevan 15 minutos sin oírse nada, o en pausa (⏸) sin cola. Así un Recorder olvidado abierto no deja el portátil encendido toda la noche. La pantalla sí puede apagarse; solo se retiene el sistema.

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

---

## 🏛️ Arquitectura del Proyecto

El proyecto está diseñado bajo una arquitectura limpia por capas y un pipeline productor-consumidor concurrente:

```
Recorder/
├── config.example.json             # Plantilla recomendada (esta si se sube)
├── config.json                     # Tu configuracion personal (ignorada por git)
├── recorder.py                     # Entrypoint principal y ejecutor de selftest
│
├── recorder/                       # Paquete principal
│   ├── config/                     # Esquemas tipados (AppConfig) y persistencia
│   ├── audio/                      # Captura WASAPI loopback, RMS, decibeles y 16 kHz
│   ├── engine/                     # Trabajador de inferencia faster-whisper
│   ├── filters/                    # Pipeline anti-alucinaciones, zlib, normalizador y léxico
│   ├── actions/                    # Capturas de pantalla DPI-aware y notas Markdown
│   ├── digest/                     # Sintesis de notas: agrupa y limpia sin tocar el original
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
    └── test_filters_and_lexicon.py # Pruebas de filtros y sustituciones
```

Para más detalles, consulta la documentación en la carpeta [docs/](docs/):
* 📖 [docs/architecture.md](docs/architecture.md): Diagramas de flujo y detalle de cada subsistema.
* 🎯 [docs/anti-hallucination-tuning.md](docs/anti-hallucination-tuning.md): Cómo se producen las alucinaciones en Whisper y cómo calibrarlas.
* 🗺️ [docs/plan-fase-3.md](docs/plan-fase-3.md): Plan para identificar a cada participante por su voz.
* 🧹 [docs/sintesis-de-notas.md](docs/sintesis-de-notas.md): Como generar versiones agrupadas y limpias de una nota sin tocar nunca el original.

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
   python -m unittest discover -s tests
   ```
