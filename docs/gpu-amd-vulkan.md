# Transcribir en una GPU AMD con whisper.cpp y Vulkan

`faster-whisper` (CTranslate2) solo usa GPUs NVIDIA con CUDA. En Windows, una Radeon RDNA2
como la RX 6700 XT no tiene camino con ese motor, así que Recorder tiene un segundo motor:
**whisper.cpp compilado con Vulkan**, corriendo como proceso aparte (`whisper-server.exe`) al
que se le habla por HTTP en `127.0.0.1`. Este documento explica por qué, cómo se instala, qué se
midió y qué queda sin verificar.

> **Convención de fuentes**, la misma que `hardware-y-modelos.md`: `[medido]` = medido en este
> equipo o leído en el código instalado; `[terceros]`, `[anecdótico]` según su origen;
> `[estimado]` = razonamiento propio. Septiembre de 2026.

---

## 1. Por qué whisper.cpp con Vulkan

| Vía | Estado en septiembre de 2026 | Veredicto |
| :--- | :--- | :--- |
| CTranslate2 con ROCm en Windows (desde la v4.7) | El paquete de Windows se compila para gfx1030/110x/115x/120x, **no para gfx1031** (RX 6700/6750 XT); el HIP SDK de AMD marca la RX 6700 XT como no soportada en Windows `[terceros: repositorio y documentación oficial]` | No sirve |
| PyTorch con ROCm en Windows | La 6700 XT solo en las compilaciones de desarrollo de AMD (TheRock), «no estables para producción» | No sirve |
| DirectML / Windows ML | DirectML en mantenimiento; el proveedor MIGraphX exige una versión exacta del driver | No sirve |
| `pywhispercpp` (binding) | Hay que compilarlo, no expone `no_speech_prob`, fallo abierto con `initial_prompt` | No conviene |
| **`whisper-server` con Vulkan** | Devuelve `avg_logprob` y `no_speech_prob` por segmento, VAD Silero, prompt, haz e idioma `[medido en server.cpp v1.9.4]`. Un fallo del driver mata ese proceso, no la ventana ni la cola | **Elegido** |

whisper.cpp **no publica binarios Vulkan para Windows** (se pidió y se cerró como «not planned»),
por eso se compila desde la etiqueta oficial.

---

## 2. Instalación

Requisitos (una vez): Git, Visual Studio 2022/2026 con C++, `winget install Kitware.CMake` y
`winget install KhronosGroup.VulkanSDK`. Después:

```powershell
.\tools\instalar_whispercpp.ps1 -Destino E:\whispercpp
```

Clona whisper.cpp `v1.9.4`, compila `whisper-server` y `whisper-bench` con `GGML_VULKAN=ON`, copia
los binarios a `E:\whispercpp\bin` y descarga `ggml-large-v3.bin` (2 952 MB),
`ggml-large-v3-turbo.bin` (1 549 MB) y el VAD `ggml-silero-v6.2.0.bin` (0,8 MB) a
`E:\whispercpp\models`. Se puede repetir sin volver a descargar. **No uses una carpeta de
OneDrive**: sincronizaría GB de modelos. En `config.json`:

```json
"whispercpp_dir": "E:\\whispercpp",
"whispercpp_flash_attn": true,
"model": "large-v3-turbo",
"beam_size": 5,
"device": "gpu",
"compute_type": "float16"
```

`device: "gpu"` usa CUDA si hay una NVIDIA y, si no, whisper.cpp con Vulkan. `"vulkan"` lo fuerza.
Con `compute_type` `q8_0` o `q5_0` se usan los modelos cuantizados (`ggml-<modelo>-q8_0.bin`), si
se descargan aparte.

---

## 3. Qué se midió `[medido]`

**Equipo:** AMD Radeon RX 6700 XT 12 GB (driver 32.0.21045.5002, Vulkan «AMD proprietary
driver», sin *coopmat*), Intel i5-9500 (6 núcleos sin HT, AVX2), 16 GB, Windows 11. whisper.cpp
v1.9.4 (`927cfce`), Vulkan SDK 1.4.357.0, MSVC 14.51. **Durante las mediciones estaban abiertos
RustDesk (usando el codificador de vídeo de la GPU), Sunshine y el servicio de Oculus**; la CPU de
otros procesos fue del 18-26 %.

**Muestra y protocolo:** los de `rendimiento.md` (241 s de *daily* sintética en español, 23
fragmentos de 10,5 s de media, haz 5, vocabulario de `config.json`, primer fragmento de
calentamiento), con `python tools\medir_rendimiento.py --motor whispercpp --hilos 5`.

| Modelo | *Flash attention* | 14-sep-2026 (GPU compartida) | 13-oct-2026 | WER |
| :--- | :-: | ---: | ---: | ---: |
| large-v3-turbo | no | 1,49x | — | 7,1 % |
| **large-v3-turbo** | **sí** | 3,18x | **8,49x** | **6,8 %** |
| large-v3 (preset Extra) | sí | 1,74x | **2,57x** | 7,7 % |

**Las cifras del 14 de septiembre están lastradas por otra carga en la GPU.** El 13 de octubre,
con el mismo driver, la misma compilación y los mismos programas abiertos (RustDesk, Sunshine,
Oculus y Teams, sin llamada en curso), turbo fue 2,7x más rápido y large-v3 1,5x; el WER es
idéntico. La causa más probable es que en septiembre hubiera una sesión remota activa: RustDesk
estaba usando el codificador de vídeo de la GPU al 57 % `[medido]`, aunque no se aisló. **Si la
GPU se comparte con streaming o escritorio remoto, cuenta con perder hasta dos tercios.**

Con 2,57x, `large-v3` supera el 2,0x que exige el peor caso de dos fuentes hablando a la vez
(`rendimiento.md` §4), así que el preset Extra es viable en este equipo; turbo va 3,3 veces más
rápido sin peor WER en esta muestra y deja más margen si la GPU se comparte.

Prueba de punta a punta con el `TranscriberWorker` real (turbo, 14-sep): carga del modelo 2,9 s;
66 s de audio en 19,9 s (3,3x); 0 fragmentos perdidos; el servidor se cierra al parar.

Sin bucles de repetición en ninguna transcripción (el fallo reportado con *flash attention* en
una RX 6600 `[anecdótico]`): 530-532 palabras frente a 546 del guion y ratio de compresión 1,97.

### 3.1. Dónde se va el tiempo

Con `GGML_VK_PERF_LOGGER=1` en `whisper-bench` (turbo, una ventana de 30 s):

* **Sin *flash attention*, 7,0 s de codificador.** Las dos multiplicaciones de la atención (f16,
  por lotes de 20 cabezas, 1500×1500) van a **~110 GFLOPS/s**, frente a ~1 600 de las
  multiplicaciones normales del mismo grafo; con `SOFT_MAX` se llevan **4,7 de los 7,0 s**. Es el
  camino lento del driver propietario de AMD para ese tipo de operación.
* **Con *flash attention*, 2,7 s.** La atención pasa a `FLASH_ATTN_EXT` (0,55 s en 32 capas) y
  el resto se reparte entre `ADD` (0,71 s), multiplicaciones normales (1,0 s) y `GELU` (0,2 s).
* **large-v3 decodifica muy lento**: 54-58 ms por token frente a 2,4-2,9 ms de turbo (32 capas de
  decodificador frente a 4), así que su codificador idéntico no compensa.

Una referencia de terceros con una RX 6750 GRE (misma familia gfx1031, Windows, marzo de 2025) daba
429-477 ms de codificador `[terceros]`, 5 veces menos que los 2,7 s de arriba. El 13 de octubre,
`whisper-bench` (turbo, *flash attention*) dio **816 ms** en este mismo equipo `[medido]`: la
mayor parte de la diferencia era la carga ajena sobre la GPU de septiembre, no el driver ni
whisper.cpp. El perfil de arriba sigue valiendo para ver *qué* pesa, no *cuánto*.

---

## 4. Cómo se comporta Recorder

* **Elección del motor** (`resolve_runtime` en `config/schema.py`): `gpu` → CUDA si
  `ctranslate2` ve una NVIDIA; si no, Vulkan si `whispercpp_dir` tiene `bin\whisper-server.exe` y
  el modelo pedido; si no, el preset Alta completo en CPU, con aviso en la cabecera.
* **Arranque** (`engine/whispercpp.py`): puerto libre en `127.0.0.1`; espera a `/health`
  (el servidor carga el modelo antes de escuchar); registro en `<whispercpp_dir>\logs\whisper-server.log`.
  El proceso va en un *Job Object* de Windows: si Recorder muere de golpe, Windows lo cierra y no
  queda ocupando VRAM.
* **Si Vulkan no arranca** (driver, VRAM): preset Alta en CPU, avisando.
* **Si el servidor muere a mitad de reunión**: se reinicia y se reintenta el mismo fragmento. Si no
  vuelve a arrancar, el resto de la reunión sigue en CPU, empezando por ese fragmento. Nada se pierde.
* **Filtros**: los mismos. El servidor no devuelve `compression_ratio`; `filters/quality.py` lo
  calcula del texto. `repetition_penalty` no existe en whisper.cpp y se ignora.
* **Petición**: WAV de 16 bits en memoria (sin ffmpeg), `verbose_json`, sin detección de idioma
  ni marcas por token (trabajo que Recorder no usa), `vad` solo si está el modelo Silero.
* **Flash attention**: `whispercpp_flash_attn` es `false` por defecto por los reportes de
  repeticiones y cierres de `amdvlk64.dll` en otras Radeon `[anecdótico]`. En esta RX 6700 XT se
  midió limpia y es 2,1x más rápida, así que el `config.json` de este equipo la activa.

---

## 5. Qué quedó sin verificar

* **Comparación con la CPU de este equipo.** No se midió `faster-whisper` turbo en el i5-9500
  (el modelo CT2 ya está en caché: `python tools\medir_rendimiento.py --hilos 4,5,6`). La
  estimación es 1-2x `[estimado]`; la GPU además deja la CPU libre para Teams.
* **Qué cargaba la GPU el 14 de septiembre.** Una sesión de RustDesk activa es la hipótesis; para
  confirmarla, medir turbo con y sin una sesión remota abierta.
* **Con Teams en llamada.** Teams decodifica vídeo en la misma GPU; no se midió la reunión real en
  GPU. Hasta el 13 de octubre todas las reuniones se transcribieron en CPU porque `config.json`
  había perdido `whispercpp_dir`.
* **Audio real.** La muestra es voz sintetizada limpia; el WER en una reunión será mayor.
* **Umbrales anti-alucinación.** `no_speech_prob` y `avg_logprob` de whisper.cpp se calculan de
  forma parecida pero no idéntica a `faster-whisper`; conviene revisar con 🎯 Calibrar tras unas
  reuniones.
* **Modelos cuantizados** (`q8_0`, `q5_0`): no medidos; podrían acelerar el decodificador de
  large-v3, que es su cuello de botella.
