# Recomendación de configuración según el equipo

Recorder tiene que servir en cualquier equipo, no solo en los dos en los que se midió. Hasta
ahora solo miraba si había GPU para el preset Extra (`detect_cuda_device_count` y
`whispercpp_ready`, que solo comprueba la carpeta escrita a mano); el instalador dejaba siempre
**Media con `cpu_threads` 0 (= 4 hilos)** en cualquier máquina, y Opciones no tenía campo para
`whispercpp_dir`: un usuario perdió la GPU sin enterarse porque `config.json` se quedó con ese
campo vacío. Este documento explica qué detecta Recorder ahora, cómo decide la gama, qué hace
con la decisión y qué queda sin verificar.

> **Convención de fuentes**, la de `hardware-y-modelos.md`: `[medido]` = medido en este proyecto
> o leído en el código instalado; `[terceros]`, `[autor]`, `[anecdótico]` según su origen;
> `[estimado]` = razonamiento propio sin medir. Octubre de 2026.

---

## 0. Resumen

* **Qué detecta** (`recorder/config/hardware.py`, sin dependencias nuevas): CPU (nombre,
  núcleos físicos y lógicos, núcleos P/E, AVX2, AVX-512, VNNI), RAM, sobremesa o portátil,
  batería, GPUs con su VRAM real y su tipo (dedicada o integrada), su número en whisper.cpp y
  las GPUs CUDA. **0,47 s** en el sobremesa i5-9500 + RX 6700 XT `[medido]`.
* **Cómo decide** (`recommend_config` en `recorder/config/schema.py`, función pura): NVIDIA con
  CUDA → Extra o turbo según la VRAM; GPU dedicada con whisper.cpp → turbo en Vulkan; si no,
  la gama de la CPU (Alta, Media, Baja), una menos con batería. Cada recomendación lleva un
  motivo legible y su confianza: **medida** si hay medición en ese modelo de CPU o GPU,
  **estimada** si no.
* **Dónde actúa**: el primer arranque la aplica sola; el instalador la escribe en el
  `config.json` que crea; ⚙ Opciones la muestra con un botón **Usar recomendado**; al arrancar
  se avisa si la configuración es más pesada que la recomendada o si hay una GPU dedicada sin
  `whispercpp_dir`; y `python recorder.py --recomendar` la imprime.

Salida real en el sobremesa medido, con whisper.cpp instalado `[medido]`:

```text
Equipo:      Intel Core i5-9500 · 6 núcleos · AVX2 · 16 GB de RAM · sobremesa · GPU: AMD Radeon RX 6700 XT (12 GB)
Recomendado: Personalizado (large-v3-turbo, haz 5, GPU con whisper.cpp y Vulkan, float16 + flash attention, 5 hilos) [medida]
Motivo:      AMD Radeon RX 6700 XT (12 GB) con whisper.cpp y Vulkan: large-v3-turbo en float16 con flash
             attention, 8,5x el tiempo real y 6,8 % de WER medidos en esta GPU. large-v3 (Extra) iba a 2,6x ...
```

---

## 1. Qué se detecta y cómo

| Dato | De dónde sale | Notas |
| :--- | :--- | :--- |
| Nombre de la CPU | Registro: `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0`, `ProcessorNameString` | Se acorta para mostrarlo («Intel Core i5-9500»). |
| Núcleos físicos, lógicos y P/E | `GetLogicalProcessorInformationEx(RelationProcessorCore)`: un registro por núcleo físico con su `EfficiencyClass` y su máscara de procesadores lógicos | P = los de la clase más alta; si todas son iguales la CPU no es híbrida y todos cuentan como P. El i7-1255U sale 2P (con HT) + 8E, 10 físicos, 12 lógicos `[medido, rendimiento.md §1]`. |
| AVX2 / AVX-512 | `IsProcessorFeaturePresent(40)` / `(41)`, con `numpy.__cpu_features__` de respaldo | Un Windows 10 antiguo no conoce las constantes 40/41 y responde FALSE; numpy mira CPUID directamente. |
| VNNI | `numpy.__cpu_features__["AVX512VNNI"]` | numpy **no** informa AVX-VNNI (la versión de 256 bits de Alder Lake): el i7-1255U sale sin VNNI aunque lo tiene. Solo informativo; no entra en la decisión. |
| RAM total y libre | `GlobalMemoryStatusEx` | |
| Sobremesa o portátil, batería | `GetSystemPowerStatus` (bandera de batería, enchufado) y `PowerDeterminePlatformRoleEx` | El rol de plataforma manda (un sobremesa con SAI puede «tener batería»); si Windows no lo sabe, se deduce de la batería. |
| GPUs y VRAM | **DXGI**: `CreateDXGIFactory1` → `EnumAdapters1` → `GetDesc1` (`DedicatedVideoMemory`, `SharedSystemMemory`, LUID, bandera `SOFTWARE`) | Memoria de 64 bits, fiable. Ver «duplicados» abajo. |
| Tipo de GPU y su número en whisper.cpp | **Vulkan** (`vulkan-1.dll`): `vkEnumeratePhysicalDevices`, `deviceType` (DISCRETE/INTEGRATED), heaps `DEVICE_LOCAL`, UUID/LUID, `driverID`, `storageBuffer16BitAccess` | En un **proceso aparte** (ver «robustez»). DXGI y Vulkan se emparejan por LUID, que es el mismo en las dos APIs. |
| GPUs CUDA | `ctranslate2.get_cuda_device_count()` (~300 ms) | Solo si hay una NVIDIA o no se sabe qué GPU hay. |

**Lo que no se usa, y por qué** `[medido]`:

* `Win32_VideoController.AdapterRAM` es un `uint32`: se queda en 4 GB. Para la RX 6700 XT de
  12 GB devuelve 4293918720.
* WMI y `vulkaninfo.exe` tardan segundos; todo lo anterior junto, medio segundo.
* Importar `faster_whisper` cuesta ~3 s; `ctranslate2` solo, ~300 ms.

**Duplicados de DXGI** `[medido]`: en el sobremesa, DXGI listó la misma RX 6700 XT **cuatro
veces** (con LUIDs distintos) por los adaptadores de pantalla indirectos de Meta, SudoMaker y
Amyuni, más el «Microsoft Basic Render Driver». `dedupe_dxgi_adapters` quita los adaptadores
de software y deja una GPU por (VendorId, DeviceId, SubSysId). Vulkan solo ve la RX una vez, con
el LUID de la primera copia.

**Robustez.** `detect_hardware()` no lanza nunca: cada bloque va en su `try/except`, deja un
valor neutro (0, "", None = «no se sabe», nunca «no hay») y apunta el motivo en
`detection_errors`. Vulkan se consulta ejecutando `hardware.py --vulkan` en otro proceso
(`python -I`, solo biblioteca estándar; 0,35 s `[medido]`): crear una instancia de Vulkan carga
el driver de vídeo y las capas de terceros (superposiciones de Steam, OBS...), y un fallo ahí no
debe tumbar la ventana. Es la misma razón por la que whisper.cpp corre como `whisper-server`
aparte.

**Caché e hilos.** `cached_hardware()` detecta una vez por proceso. La ventana principal lo
lanza en un hilo al arrancar; Opciones y el transcriptor reutilizan el resultado (si lo piden
antes de que termine, esperan a esa misma detección en vez de repetirla). El estado de la
batería es el del arranque.

---

## 2. Gamas

En este orden; la primera que encaja decide (`recommend_config`).

| # | Condición | Recomendación | Confianza |
| :-: | :--- | :--- | :--- |
| 1 | NVIDIA con CUDA y **≥ 6 GB** | **Extra**: large-v3, haz 5, `gpu`, float16 | estimada: 8x-15x y 4,5 GB de VRAM `[terceros, hardware-y-modelos.md §2]` |
| 2 | NVIDIA con CUDA y < 6 GB (o VRAM desconocida) | large-v3-turbo, haz 5, `cuda`, float16 | estimada: turbo float16 ocupa ~2,5 GB `[terceros]` |
| 3 | GPU **dedicada** y whisper.cpp con `ggml-large-v3-turbo.bin` | large-v3-turbo, haz 5, `vulkan`, float16, **flash attention** | **medida** en una RX 6700 XT (8,49x, WER 6,8 %); estimada en otras GPUs |
| 3b | Ídem, pero solo está descargado `ggml-large-v3.bin` | Extra con flash attention, sugiriendo descargar turbo | como la 3 |
| 4 | CPU **alta**: AVX2, ≥ 7,5 GB de RAM y (no híbrida con **≥ 8 físicos**, o híbrida con **≥ 6 P**) | **Alta**: large-v3-turbo, haz 5, CPU | estimada (un i7-1255U, más débil, iba a ~1,0x `[medido]`) |
| 5 | CPU **media**: AVX2, ≥ 7,5 GB y 4-7 físicos (o híbrida con < 6 P) | **Media**: small, haz 5, CPU | medida en el i7-1255U (3,0x); estimada en otras |
| 6 | CPU **baja**: < 4 físicos, sin AVX2 o < 7,5 GB | **Baja**: small, haz 1, CPU | medida en el i7-1255U (5,4x); estimada en otras |
| — | **Con batería** | Una gama de CPU menos (Alta → Media → Baja) | estimada |

Cuando cae a CPU teniendo GPU, el motivo dice por qué y qué hacer:

* **NVIDIA sin CUDA** (DXGI la ve, `ctranslate2` no): driver, o faltan las bibliotecas de CUDA
  12 y cuDNN 9 que usa faster-whisper. También se puede usar con whisper.cpp y Vulkan.
* **GPU dedicada AMD/Intel sin whisper.cpp**: «ejecuta `tools\instalar_whispercpp.ps1` y vuelve
  a pulsar Usar recomendado».
* **Solo GPU integrada**: no se usa por defecto (sección 3).

### 2.1. Umbrales `[estimado]`

| Umbral | Valor | Por qué |
| :--- | :--- | :--- |
| VRAM para Extra | 5 632 MB | «6 GB» con margen: large-v3 float16 con haz 5 llegó a 4 521 MB en una 2080 Ti `[terceros]`. |
| RAM mínima | 7 680 MB | Un equipo «de 8 GB» reporta algo menos (firmware, memoria de la iGPU). |
| CPU alta | ≥ 8 físicos (no híbrida) o ≥ 6 P (híbrida) | Ver abajo. |
| CPU media | ≥ 4 físicos | Por debajo, ni `small` con haz 5 va holgado con una videollamada. |

**En una CPU híbrida mandan los núcleos P, no los físicos.** El i7-1255U tiene 10 físicos, pero
8 son E, que rinden un 35-45 % de un P en AVX2 `[estimado, hardware-y-modelos.md §1.2]`. Con
turbo iba a ~1,0x en reposo y a 0,33x con Teams `[medido]`, y en reuniones reales la cola
llegaba a cientos de fragmentos (`rendimiento.md`). Contar sus 10 núcleos lo pondría en Alta y
reproduciría ese problema; contando sus 2 P queda en **Media**. «≥ 8 físicos o ≥ 6 P» se
interpreta así: los 8 físicos para una CPU no híbrida, los 6 P para una híbrida (una híbrida con
6 P tiene siempre más de 8 físicos, así que la otra lectura dejaría la condición de los P sin
efecto).

### 2.2. ¿large-v3 o turbo en una GPU con Vulkan?

La re-medición del 13 de octubre en la RX 6700 XT dio **large-v3 2,57x (WER 7,7 %) y turbo
8,49x (WER 6,8 %)** `[medido, gpu-amd-vulkan.md §3]`. large-v3 supera el 2,0x del peor caso de
dos fuentes (`rendimiento.md` §4), así que Extra es viable, pero la recomendación es **turbo**:

* En la muestra, large-v3 no transcribe mejor (7,7 % frente a 6,8 %); su ventaja publicada en
  español es pequeña (4,4 % frente a ~5,2 % en Common Voice `[terceros]`).
* La velocidad de la GPU depende de qué más la use. El mismo 13 de octubre, durante este
  trabajo y con una sesión de RustDesk activa (códec de vídeo de la GPU al **58,5 %**), turbo fue
  a **3,28x** con el mismo WER de 6,8 % (`medir_rendimiento.py --motor whispercpp --dev 0`, una
  pasada) y `whisper-bench` dio 2 224-2 716 ms de codificador frente a 816 ms sin la sesión
  `[medido]`. Es la misma pérdida que el 14 de septiembre (turbo 3,18x, large-v3 1,74x). Con esa
  carga large-v3 caería a ~1,0x `[estimado, misma proporción]`, por debajo del 2x de dos fuentes;
  turbo sigue por encima.

Extra sigue disponible en Opciones. Se recomienda large-v3 en Vulkan solo si turbo no está
descargado (fila 3b). Con una GPU más rápida medida, se añade a `MEASURED_VULKAN_GPUS` y se
revisa esta regla.

### 2.3. Hilos de CPU

`recommended_cpu_threads` `[estimado; afinar con tools\medir_rendimiento.py]`:

* **No híbrida**: `max(4, físicos − 1)`, dejando un núcleo a la videollamada.
* **Híbrida con ≥ 4 P**: los núcleos P (en un bucle OpenMP el hilo más lento marca el paso;
  llama.cpp fue 2,4x más rápido solo con los P en un i7-12700H `[terceros]`).
* **Híbrida con < 4 P**: `físicos − 1`, porque solo con los P se quedaría por debajo de los 4
  hilos de la biblioteca (Intel oneMKL dice que con muchos menos P que E conviene usar todos
  `[autor]`).
* **Nunca más que núcleos físicos**; 0 (valor de la biblioteca) si no se sabe cuántos hay.

| CPU | Hilos |
| :--- | ---: |
| i5-9500 (6, sin HT) | 5 |
| i7-1255U (2P+8E) | 9 |
| i7-12700H (6P+8E) | 6 |
| Ryzen 7 5800U (8) | 7 |
| 2 núcleos | 2 |

---

## 3. Qué GPU usa whisper.cpp (`whispercpp_device`)

**Lo que hace whisper.cpp v1.9.4 sin indicaciones** `[medido en el código]`: sin
`GGML_VK_VISIBLE_DEVICES`, ggml-vulkan registra las GPUs **dedicadas e integradas** en el orden en
que Vulkan las enumera (`ggml-vulkan.cpp`, ~7560-7691), y whisper.cpp toma el dispositivo
`gpu_device` (0) contando GPU e IGPU por igual (`src/whisper.cpp`, ~1298-1320). En un portátil
con iGPU y dGPU **gana la que Vulkan enumere primero**, que puede ser la integrada.
`whisper-server` acepta `-dev N`, y su registro imprime
`ggml_vulkan: N = <nombre> (<driver>) | uma: 0/1 | ...` y `using VulkanN backend`.

**Lo que hace Recorder:**

* Campo `whispercpp_device` (`-1` = automático). En automático elige **la dedicada con más
  VRAM** y la pasa con `-dev N`; **nunca una integrada**. Si solo hay integrada, Vulkan cuenta
  como no disponible y se usa el preset de CPU, explicándolo en la cabecera.
* Un número ≥ 0 fuerza esa GPU, integrada incluida; con una integrada el modelo se limita a
  **large-v3-turbo** (nunca large-v3).
* El número se calcula reproduciendo en Python el orden de ggml (`ggml_vulkan_order`): GPUs
  dedicadas e integradas con `storageBuffer16BitAccess`, y si dos son la misma GPU (mismo UUID o
  LUID, p. ej. el driver propio y Dozen) se queda la del driver preferido.
* **Comprobación en el registro**: tras arrancar, se lee qué GPU tomó el servidor
  (`parse_vulkan_log`). En automático, si fue una integrada (Vulkan no se pudo consultar antes, o
  el orden no coincidió), se cierra el servidor y se usa la CPU, avisando.
* **Sin GPU, whisper.cpp no falla: sigue en su CPU**, más lento que faster-whisper y sin avisar.
  Si el registro dice `no GPU found` sin ninguna `using VulkanN backend` (`runs_on_cpu`), se
  trata como «Vulkan no arranca»: preset de CPU con aviso. Probado con `-dev 5` en el sobremesa:
  se detecta en 2,3 s `[medido]`.

**Por qué la iGPU nunca va por defecto:** su «VRAM» es RAM del sistema, con el mismo ancho de
banda que ya usa la CPU (~51 GB/s en DDR4 de doble canal) `[estimado]`, y comparte con la CPU, y
con Teams, el presupuesto de potencia: lo que gana la GPU lo puede perder la CPU. No hay cifras
publicadas de Whisper en Iris Xe; whisper.cpp 1.8.3 logró 3-4x sobre CPU en una Radeon 680M y en
la Arc de un Core Ultra `[autor del PR]`, pero una UHD 730 fue más lenta que la CPU `[terceros]`
(`hardware-y-modelos.md` §2.5). Es una opción explícita, después de medir:

```powershell
python tools\medir_rendimiento.py --motor whispercpp --modelo large-v3-turbo --hilos 4 --flash-attn --dev 0
```

---

## 4. Dónde se aplica

| Momento | Qué pasa |
| :--- | :--- |
| **Primer arranque** (no hay `config.json`) | `ConfigManager.first_run` lo indica. La ventana espera a la detección (~0,5-2 s) antes de cargar el modelo, aplica la recomendación (modelo, haz, dispositivo, precisión, hilos y, con whisper.cpp, flash attention), guarda `config.json` y escribe en el visor una línea con el equipo, lo aplicado y el motivo. Rutas, vocabulario y filtros no se tocan. |
| **Instalador** (`install.ps1`) | Tras copiar `config.example.json`, ejecuta `recorder.py --recomendar --aplicar`. Si `config.json` ya existía, solo muestra la recomendación (`--recomendar`) y no lo toca. |
| **⚙ Opciones** | «Recomendado para este equipo: … — motivo [confianza]» y el botón **Usar recomendado** (pone el preset, o Personalizado con sus valores, los hilos y flash attention; se guarda al pulsar Guardar). Además: **Hilos de CPU** (con el recomendado al lado), **whisper.cpp** (carpeta con 📁 y si hay servidor y modelos), **GPU de whisper.cpp** (Automática o una de la lista) y **Flash attention**. |
| **Cada arranque** | Avisos en el visor (`startup_notices`): ⚠ GPU dedicada que solo sirve con whisper.cpp y `whispercpp_dir` vacío; ⚠ configuración más pesada que la recomendada (`config_heavier_than`: mismo dispositivo y modelo o haz mayor, o large-v3 en CPU); 💡 la configuración está en CPU y la recomendada usa la GPU. |
| **`tools\instalar_whispercpp.ps1`** | Al terminar, ejecuta `whisper-bench` y muestra las líneas de dispositivo (`ggml_vulkan: N = …`, `using VulkanN backend`), avisando si la que toma es integrada; y escribe `whispercpp_dir` en `config.json` si existe, cambiando solo esa clave como texto. |
| **Consola** | `python recorder.py --recomendar` imprime el equipo, la recomendación y el motivo; con `--aplicar` la guarda en `config.json` (se niega si el archivo no se pudo leer). |

**Ejemplos** (perfiles de `tests/test_recommendation.py`):

| Equipo | Recomendación |
| :--- | :--- |
| i5-9500 + RX 6700 XT con whisper.cpp | turbo en Vulkan, float16, flash attention, 5 hilos `[medida]` |
| i5-9500 + RX 6700 XT sin whisper.cpp | Media, 5 hilos, «ejecuta tools\instalar_whispercpp.ps1» |
| i7-1255U (2P+8E, Iris Xe) enchufado / con batería | Media, 9 hilos `[medida]` / Baja |
| i7-12700H (6P+8E) | Alta, 6 hilos |
| 8 núcleos no híbridos enchufado / con batería | Alta / Media |
| RTX 3060 12 GB con CUDA | Extra |
| GTX 1650 4 GB con CUDA | turbo en CUDA, float16 |
| RTX 3060 sin CUDA | gama de la CPU, explicando lo de CUDA |
| Celeron de 2 núcleos sin AVX2 | Baja, 2 hilos |

---

## 5. Qué se cambió en el código

* `recorder/config/hardware.py` (nuevo): `GpuInfo`, `HardwareProfile`, `detect_hardware`,
  `cached_hardware`, y las piezas puras `parse_core_topology`, `dedupe_dxgi_adapters`,
  `ggml_vulkan_order`, `merge_gpus`, `classify_power`, `describe_hardware`.
* `recorder/config/schema.py`: `whispercpp_device` en `AppConfig`; `Recommendation`,
  `recommend_config`, `recommended_cpu_threads`, `cpu_tier`, `apply_recommendation`,
  `config_heavier_than`, `startup_notices`, `describe_recommendation`; `VulkanChoice`,
  `choose_vulkan_device`, `vulkan_model_for`; `resolve_runtime` acepta la GPU elegida
  (sigue devolviendo los mismos cinco valores).
* `recorder/config/manager.py`: `first_run`.
* `recorder/engine/whispercpp.py`: `-dev N` en `server_command`, `parse_vulkan_log`,
  `vulkan_readiness`, `installed_models`; el modelo guarda la GPU que dice el registro.
* `recorder/engine/whisper_worker.py`: elige la GPU antes de arrancar el servidor y rechaza una
  integrada tomada en automático.
* `recorder/ui/main_window.py` y `recorder/ui/dialogs/settings_dialog.py`: lo de la sección 4.
* `recorder.py --recomendar [--aplicar]`, `install.ps1`, `tools/instalar_whispercpp.ps1`,
  `tools/medir_rendimiento.py --dev N`, `config.example.json` (`whispercpp_device`).
* Pruebas: `tests/test_hardware.py` (topología 2P+8E sintética, DXGI con duplicados, orden de
  ggml, energía, `detect_hardware` con ctypes roto, registro del servidor, `-dev`,
  `first_run`) y `tests/test_recommendation.py` (cada gama, hilos, comparaciones, avisos,
  elección de GPU y el worker). En `tests/test_whispercpp.py` la prueba del worker con Vulkan
  fija ahora la lista de GPUs vacía, para no depender de las del equipo que la ejecuta.

---

## 6. Qué quedó sin verificar

* **Solo se ejecutó en un equipo**, el sobremesa i5-9500 + RX 6700 XT. No se probó en vivo en
  un portátil con iGPU y dGPU, con una NVIDIA, con una Intel Arc ni con una APU de AMD; esos
  casos están cubiertos con datos sintéticos y por la comprobación del registro del servidor.
* **La topología híbrida** se probó con un búfer sintético 2P+8E; los números del i7-1255U son
  los de `rendimiento.md`, no de una ejecución de esta detección en ese portátil.
* **Los umbrales son estimados**, y las gamas Alta en CPUs más potentes que el i7-1255U no se
  midieron. `tools\medir_rendimiento.py` convierte cualquiera en dato en 15 minutos.
* **Flash attention** se recomienda para cualquier GPU dedicada con whisper.cpp; solo se midió
  limpia en la RX 6700 XT, y hay reportes de repeticiones en una RX 6600 `[anecdótico]`.
* **El orden de ggml** se reproduce con la lógica de v1.9.4; si una versión futura de whisper.cpp
  lo cambia, la comprobación del registro sigue protegiendo frente a una iGPU, pero el `-dev`
  automático podría apuntar a otra dedicada.
* **APU de AMD con mucha memoria UMA** asignada en la BIOS: si Vulkan no responde, DXGI la ve
  con varios GB «dedicados» y la tomaría por dedicada.
* **Dos GPUs idénticas**: DXGI las junta en una (misma clave); la lista de Vulkan sí las separa.
* **VNNI**: numpy no informa AVX-VNNI; el campo solo refleja AVX512-VNNI.
* **La batería** se lee al arrancar: enchufar o desenchufar después no cambia la recomendación
  hasta reiniciar.
