# 🎙️ Recorder · Live Audio Transcriber & Daily Notes Assistant

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-faster--whisper-orange.svg)](https://github.com/SYSTRAN/faster-whisper)
[![Architecture](https://img.shields.io/badge/architecture-modular%20clean-green.svg)](docs/architecture.md)

**Recorder** es una herramienta de escritorio ligera y modular para Windows que transcribe en tiempo real tanto la salida de audio de tu equipo (reuniones en Teams, Meet, Zoom, llamadas o vídeos) mediante **WASAPI Loopback**, como tu propio micrófono. Genera automáticamente un archivo `.md` con marcas de tiempo, capturas de pantalla automáticas en tus monitores ante palabras clave y cuenta con un sistema interactivo de **calibración anti-alucinaciones y léxico personal**.

---

## ✨ Características Principales

* 🔊 **Captura de Salida + Micrófono (WASAPI Loopback):** Captura el audio de tus reuniones sin necesidad de cables virtuales (Virtual Audio Cable). Muestra medidores de nivel de volumen en vivo (`🔊 █░   🎤 █░`).
* ⚡ **Transcripción Rápida con IA (faster-whisper):** Ejecución eficiente en CPU mediante cuantización `int8` (modelos `tiny`, `base`, `small`, `medium`, `large-v3-turbo`).
* 📸 **Capturas de Pantalla Automáticas:** Al escuchar palabras clave configuradas (*"bloqueo"*, *"pendiente"*, *"captura"*, etc.), toma una captura del monitor seleccionado y la incrusta directamente en el archivo Markdown.
* 🎯 **Fine-Tuning Anti-Alucinaciones & Léxico Personal:**
  * **Filtro de Silencios / Ruido:** Descarte automático de fórmulas típicas de YouTube (*"suscríbete"*, *"amara.org"*, etc.).
  * **Anti-Bucles:** Detector de repeticiones continuas mediante análisis de compresión zlib (`compression_ratio`).
  * **Diccionario Fonético:** Sustituciones automáticas para jerga técnica o siglas de tu equipo (`cuba` ➔ `QA`, `ayayas` ➔ `IIS`).
  * **🧪 Sandbox en Vivo:** Prueba tus reglas interactivamente en la interfaz antes de guardarlas.
* 📝 **Salida Markdown Atómica:** Genera un archivo diario (ej: `daily_2026-09-08_14-30.md`) con soporte para pausar (`⏸`), reanudar (`▶`) y trasladar la carpeta de notas en caliente.

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
   function daily { python "C:\Users\desarrollo 6\Documents\GitHub\Recorder\recorder.py" $args }
   ```

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

* **📸 Captura:** Toma una captura de pantalla manual instantánea del monitor configurado y la anota en el Markdown.
* **⚙ Opciones:** Permite elegir la carpeta de notas, la carpeta de capturas, los dispositivos de audio WASAPI (altavoces/micrófono), el monitor y el modelo de Whisper.
* **🎯 Calibrar:** Abre el panel de fine-tuning para ajustar el prompt de contexto, la lista negra de alucinaciones, el diccionario fonético y probar frases en el sandbox.
* **⏸ Pausar / ▶ Continuar:** Suspende la toma de notas durante pausas de la reunión sin cerrar el archivo diario.

---

## 🏛️ Arquitectura del Proyecto

El proyecto está diseñado bajo una arquitectura limpia por capas y un pipeline productor-consumidor concurrente:

```
Recorder/
├── config.json                     # Configuración persistente del usuario
├── recorder.py                     # Entrypoint principal y ejecutor de selftest
│
├── recorder/                       # Paquete principal
│   ├── config/                     # Esquemas tipados (AppConfig) y persistencia
│   ├── audio/                      # Captura WASAPI loopback, RMS, decibeles y 16 kHz
│   ├── engine/                     # Trabajador de inferencia faster-whisper
│   ├── filters/                    # Pipeline anti-alucinaciones, zlib, normalizador y léxico
│   ├── actions/                    # Capturas de pantalla DPI-aware y notas Markdown
│   └── ui/                         # Interfaz gráfica Catppuccin y diálogos modales
│
├── docs/                           # Documentación técnica
│   ├── architecture.md             # Especificación detallada de arquitectura
│   ├── anti-hallucination-tuning.md# Guía completa de fine-tuning y alucinaciones
│   ├── plan-fase-2.md              # Plan de la Fase 2 (modularizacion) - completada
│   └── plan-fase-3.md              # Plan de la Fase 3 (identificar participantes)
│
└── tests/                          # Suite de pruebas unitarias
    ├── test_audio_processing.py    # Pruebas de DSP y señales
    ├── test_config.py              # Pruebas de configuración
    └── test_filters_and_lexicon.py # Pruebas de filtros y sustituciones
```

Para más detalles, consulta la documentación en la carpeta [docs/](docs/):
* 📖 [docs/architecture.md](docs/architecture.md): Diagramas de flujo y detalle de cada subsistema.
* 🎯 [docs/anti-hallucination-tuning.md](docs/anti-hallucination-tuning.md): Cómo se producen las alucinaciones en Whisper y cómo calibrarlas.
* 🗺️ [docs/plan-fase-3.md](docs/plan-fase-3.md): Plan para identificar a cada participante por su voz.

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
