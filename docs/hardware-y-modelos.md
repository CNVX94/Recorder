# Hardware y modelos: qué hacer con un portátil que se queda corto

Documento de decisión. Responde a cinco preguntas: si el freno es de hardware o de optimización, qué
hardware mínimo hace falta para `large-v3`, qué modelo usar en cada tipo de reunión, qué modelos
locales alucinan menos, y si compensa delegar la transcripción a otra máquina. Termina con una
recomendación ordenada y con precios.

> **Convención de fuentes.** `[medido]` = medido en este equipo o leído en el código instalado.
> `[estimado]` = cálculo o razonamiento propio, sin medir. `[autor]` = lo afirma el autor del modelo
> o el fabricante. `[terceros]` = medido o publicado por alguien externo con método. `[anecdótico]`
> = issues, foros o blogs sin método. Las referencias `[F#]` están al final. Investigación de
> septiembre de 2026; **los precios y los modelos cambian**.
>
> La transcripción en la nube y los contenedores comerciales (Speechmatics, Azure) están cubiertos
> en `stt-nube-y-privacidad.md`; aquí solo se citan cuando compiten con una compra de hardware.

---

## 0. La conclusión primero

1. **Para `large-v3-turbo`, el freno es de optimización, todavía no de hardware.** Con los datos de
   `rendimiento.md` y el código instalado, fusionar fragmentos hasta ~28 s y ajustar los hilos
   debería llevar `turbo` con haz 5 de **1,0x a entre 2x y 4x en reposo** (lo más probable, 2,5x-3x)
   `[estimado]`, y a **~1,2x-2,6x con Teams abierto**. Eso cubre una reunión normal con dos fuentes;
   el peor caso (las dos fuentes hablando sin parar, que exige 2,0x) solo si la medición sale por
   arriba. Cuesta 0 MXN y un par de horas.
2. **Para `large-v3` completo, el freno sí es de hardware.** Hoy iría a 0,3x-0,4x en esta CPU
   `[terceros por analogía + estimado]` y entre 0,6x y 1,6x afinado. No hay camino sin GPU: **este
   portátil no tiene NPU** (solo el GNA 3.0, que OpenVINO discontinuó) `[medido]`, y la Iris Xe da
   como mucho 1,3x-2x con un cambio de motor frágil en Windows `[terceros por analogía]`.
3. **La GPU externa está descartada:** el ProBook 440 G9 tiene un USB-C de 10 Gbps sin Thunderbolt
   ni USB4, y sin túnel PCIe no hay eGPU `[medido + ficha HP]`.
4. **Cualquier GPU NVIDIA de 6 GB o más corre `large-v3` muy por encima del tiempo real** (una
   RTX 2080 Ti medida: 15x en float16 con haz 5; 4,5 GB de VRAM) `[terceros]`. La más barata que
   resuelve el problema es una **RTX 3060 de 12 GB a 7 679 MXN** `[terceros]` en cualquier PC de
   sobremesa de la red local, con un servidor compatible con la API de OpenAI y Recorder delegando.
5. **En español, la ventaja de calidad de `large-v3` sobre `turbo` es real pero pequeña** (4,4 %
   frente a ~5,2 % de WER en Common Voice) `[terceros]`; la ventaja grande de la GPU es de velocidad
   y de sacar la carga del portátil durante la llamada.
6. **Recomendación:** primero optimizar (gratis), después delegar a un sobremesa con GPU si existe
   uno en la red (7 679 MXN; ~16 500 MXN si hay que comprar también el PC), y cambiar de portátil solo
   si de todas formas tocaba (desde 26 659 MXN).

---

## 1. ¿Freno de hardware o de optimización?

### 1.1. Inventario del equipo `[medido]`

| | |
| :--- | :--- |
| Modelo | HP ProBook 440 14 inch G9. BIOS 01.18.01 (2026). |
| CPU | Intel Core i7-1255U: 2 núcleos P con HT + 8 núcleos E, 12 hilos, AVX2 con VNNI, sin AVX-512. |
| RAM | 32 GB (2 × 16 GB DDR4-3200 SODIMM). Sobra para cualquier modelo en CPU. |
| GPU integrada | Intel Iris Xe Graphics, 96 EU, driver 32.0.101.7085. |
| NPU | **No hay.** Solo aparece «Intel GNA Scoring Accelerator» (GNA 3.0). La ficha de Intel del i7-1255U lista GNA 3.0 y no «AI Boost»; la NPU es de Core Ultra en adelante [F3] `[autor]`. |
| Thunderbolt / USB4 | **No hay controlador** Thunderbolt ni USB4 en el sistema; solo «Intel USB 3.10/3.20 eXtensible Host Controller». La ficha de HP dice «1 SuperSpeed USB Type-C 10Gbps signaling rate (USB Power Delivery, DisplayPort 1.4)»; Notebookcheck y LaptopMedia lo listan como «sin Thunderbolt» y el soporte de HP responde que por eso no admite eGPU [F2]. Las QuickSpecs en PDF no se pudieron descargar (certificado); no se encontró ningún SKU del 440 G9 con TB4 (aparece en el 440 **G10**). |
| Software | Python 3.14, `faster-whisper` 1.2.1, `ctranslate2` 4.8.2, `torch` 2.11 (CPU), `onnxruntime` 1.28. |

### 1.2. Un modelo de coste por llamada

`rendimiento.md` deja dos hechos que bastan para estimar el margen:

* Cada `transcribe()` rellena el fragmento a 30 s antes del codificador. **Confirmado en el código
  instalado: `pad_or_trim` se llama siempre con su valor por defecto de 3000 frames en el bucle de
  ventanas; el parámetro `chunk_length` solo acorta la ventana, no el relleno** `[medido]`. La
  petición de un `audio_ctx` como el de whisper.cpp se cerró como «not planned» (issue #171) [F11].
  whisper.cpp sí lo tiene (`-ac`): 3x en clips de 5,7 s con `base.en`, pero el propio hilo avisa de
  bucles y repeticiones y los ajustes que lo corrigen solo existen para tiny/base/small [F11]
  `[terceros]`. Para fragmentos de 10 s la única palanca segura es fusionarlos.
* Transcribir 30 s cuesta **1,10x** lo que cuesta transcribir 5 s `[medido]`.

Si el coste de una llamada es `T(s) = E + D·s` (`E` fijo por llamada: codificador de 30 s más el
`initial_prompt`; `D` coste del decodificador por segundo de voz), de `T(30) = 1,10 · T(5)` sale
`D ≈ 0,004 · E`: para un fragmento de 10,5 s el decodificador es **menos del 5 % del coste**. Es
un dato de una sola medición y no consta con qué haz se hizo, así que se trabaja con dos escenarios:

| Escenario | Parte fija por llamada (fragmento de 10,5 s) | Fusión a 28 s: ganancia | Fuente |
| :--- | ---: | ---: | :--- |
| A: el decodificador es ~5 % | 95 % | **2,5x** | `[medido]` la relación 1,10x; `[estimado]` la extrapolación |
| B: el decodificador es ~30 % (haz 5, más tokens) | 70 % | **1,8x** | `[estimado]`, escenario prudente |

**Hilos, 4 → 8-10: entre nada y 2x, y hay que medirlo** `[estimado]`. Hoy 4 hilos caen casi seguro
en los 2 núcleos P con HT. Con 10 hilos entran los 8 núcleos E, cada uno a un 35-45 % de un núcleo
P en AVX2 y con el reloj bajando por el límite de potencia; en un bucle OpenMP con reparto estático
el hilo más lento marca el paso. La evidencia en CPU híbridas va en los dos sentidos: en un
i7-12700H (6P+8E), llama.cpp fue **2,4x más rápido usando solo los 6 núcleos P** que con todos [F12]
`[terceros]`; pero la guía de Intel oneMKL (el GEMM que usa CTranslate2) dice que cuando hay muchos
menos núcleos P que E «ejecutar en todos los núcleos puede rendir más» [F12] `[autor]`, que es este
caso (2P+8E). CTranslate2 no documenta nada sobre híbridos ni sobre `OMP_WAIT_POLICY` [F12]. Con
Teams abierto, `OMP_WAIT_POLICY=PASSIVE` o `KMP_BLOCKTIME=0` evitan que los hilos ociosos giren
compitiendo con la llamada; no está documentado por CT2, hay que probarlo.

**Combinado: `large-v3-turbo`, haz 5 y vocabulario pasaría de 1,0x a entre 2x y 4x en reposo, lo
más probable entre 2,5x y 3x** `[estimado]`. La parte de la fusión es la sólida (la relación 1,10x
dice que la parte fija pesa aún más de lo que `rendimiento.md` suponía); la de los hilos es la
incierta. `tools\medir_rendimiento.py` (`--hilos`, `--fusion 30`) convierte ambas en dato en 15
minutos con el equipo en reposo.

### 1.3. ¿Basta para dos fuentes de audio?

* **Durante la reunión**, la fila 2 de `rendimiento.md` (0,33x) se midió con *otra* instancia de
  Recorder de 4 hilos al 100 % más Teams, navegador y Visual Studio; descontando esa instancia,
  Teams y compañía se llevan **un 30-35 % de la CPU** `[medido, indirecto]`. Con el 65-70 % restante,
  `turbo` afinado quedaría en **1,2x-2,6x, lo más probable ~1,7x** `[estimado]`.
* La condición de `rendimiento.md` es 2,0x sostenido en el peor caso (las dos fuentes con voz a la
  vez) y 1,1x-1,3x en una reunión normal. **Reunión normal: sí, sin cola. Peor caso: solo si la
  medición sale por arriba**; si no, la cola crece despacio y se drena en minutos al terminar, no en
  una hora.
* **Coste oculto:** con Recorder a 8-10 hilos, Teams compite por la misma CPU. Si la llamada se
  entrecorta, bajar a 6 hilos o pasar a `small` en esa reunión. Es el argumento de fondo para sacar
  la transcripción del portátil (sección 5).

### 1.4. ¿Y `large-v3` en esta CPU?

`large-v3` comparte el codificador de 32 capas con `turbo` y multiplica por 8 el decodificador
(1550 M frente a 809 M de parámetros; el decodificador pasa de 32 a 4 capas [F5]). Las referencias
publicadas encajan: `large-v3` va a 0,33x en un Ryzen 7 5700G y a ~0,4x en un i9-12900K de
sobremesa [F13] `[terceros/anecdótico]`, así que **hoy en este portátil iría a 0,3x-0,4x**
`[estimado]`, y el 1,0x de `turbo` es lo normal, no un síntoma de configuración rota. Aplicando el
2x-4x de la optimización: **`large-v3` afinado quedaría entre 0,6x y 1,6x en reposo y por debajo de
1x con Teams** `[estimado]`. No vale para ir en vivo; en el mejor caso vale para transcribir
grabaciones después. `medium` ya está descartado (1,2x medido, peor que `turbo` en calidad y
velocidad).

**Respuesta a la pregunta 1:** hay margen de optimización de 2x a 4x sin gastar nada, y eso basta
para `turbo` con dos fuentes en una reunión normal. Para `large-v3` la única salida es una GPU.

---

## 2. Hardware mínimo para `large-v3`

### 2.1. Memoria de vídeo

| Modelo y precisión (haz 5, 13 min de audio) | VRAM máxima | Tiempo | GPU | Fuente |
| :--- | ---: | ---: | :--- | :--- |
| **large-v3 float16** | **4 521 MB** | 52,0 s (**15x**) | RTX 2080 Ti 11 GB | Issue #1030 [F10] `[terceros]` |
| large-v3 int8 | 2 953 MB | 52,6 s | RTX 2080 Ti | Ídem; **el WER subió de 2,9 a 4,6 %** en esa prueba |
| large-v3-turbo float16 / int8 | 2 537 / 1 545 MB | 19,2 / 19,6 s (**40x**) | RTX 2080 Ti | Ídem |
| large-v2 float16 / int8 | 4 525 / 2 926 MB | 63 / 59 s (12x-13x) | RTX 3070 Ti 8 GB | README de faster-whisper [F1] `[terceros]` |
| large-v2 float16, lote 8 (`BatchedInferencePipeline`) | 6 090 MB | 17 s (**46x**) | RTX 3070 Ti | Ídem |
| large-v2 int8, lote 8 | 4 500 MB | 16 s | RTX 3070 Ti | Ídem |
| large-v3 int8 (carga) | ~2,9 GB | — | — | Artículo de 2026 [F9] `[terceros]` |

`large-v3` y `large-v2` tienen los mismos 1550 M de parámetros [F5]. Lectura práctica: **6 GB bastan
para `large-v3` float16 sin lote; 8 GB para usar lote 8 en float16 (justo) o int8_float16 (holgado);
12-16 GB solo si además se quiere dejar sitio a otro modelo**. En GPU conviene **float16, no int8**:
la ganancia de velocidad es nula y en la única medición encontrada int8 costó 1,7 puntos de WER.

### 2.2. Velocidad esperable

| GPU | Medición publicada | Con `faster-whisper`, sin lote `[estimado]` | Fuente |
| :--- | :--- | :--- | :--- |
| RTX 2080 Ti | large-v3 fp16 haz 5: **15x**; turbo: 40x | — | [F10] `[terceros]` |
| RTX 3070 Ti 8 GB | large-v2 fp16: 12x; int8: 13x; lote 8: **46x** | — | [F1] `[terceros]` |
| RTX 3060 12 GB | ~35 s/min (**1,7x**) con `openai/whisper`; large-v3 por lotes en SaladCloud ≈ **20x** | 8x-10x | [F9, F14] `[terceros]` |
| RTX 4060 Ti 16 GB | ~18 s/min (**3,3x**) con `openai/whisper` | 8x-12x | [F9] `[terceros]` |
| RTX 4070 Super | 19 s/min (3,1x) con `openai/whisper` | 14x-18x | [F9] |
| RTX 3090 | RTF 0,19 (5,3x) | 10x-15x | [F13] `[anecdótico]` |
| RTX 4080 | large-v3 por lotes: **40x** | — | [F14] `[terceros]` |
| RTX 4090 | ~7 s/min (8,6x) con `openai/whisper` | >20x | [F9] |
| RTX 5060 8 GB / 5060 Ti 16 GB / 5070 12 GB | **Sin mediciones publicadas** con faster-whisper | 10x-14x / 12x-16x / 18x-22x | `[estimado]` por ancho de banda |
| Tesla T4 | `openai/whisper` large: 9x | 6x-8x | [F13] `[terceros]` |
| CPU i9 de sobremesa | ~150 s/min (0,4x) con `openai/whisper` | 1x-2x en int8 | [F9] |

La columna «estimado» aplica el factor del README (faster-whisper ~2,3x más rápido que
`openai/whisper` al mismo haz; ~8x con lote 8 [F1]) y escala por ancho de banda de memoria respecto a
la 2080 Ti. **Conclusión:** cualquier GPU NVIDIA de sobremesa de los últimos siete años pone
`large-v3` entre 5x y 15x sin lote, y muy por encima con lote. El escalón no lo marca la velocidad,
lo marca la VRAM y el uso futuro. Haz 1 frente a 5 en GPU apenas cambia el tiempo (10-25 %)
`[estimado]`: el decodificador es pequeño frente al codificador.

### 2.3. Tres escalones de gasto

Precios en México del 11 de septiembre de 2026, con IVA, en una tienda en línea con existencias
[F15, F16, F17] `[terceros]`; lo demás, `[estimado]`.

| Escalón | Qué | Precio | Qué da |
| :--- | :--- | ---: | :--- |
| **1. El más barato que resuelve** | RTX 3060 12 GB (o RTX 5060 8 GB, 7 369 MXN) en un PC de sobremesa **que ya exista** en la red local | **7 679 MXN** | `large-v3` fp16 a 8x-10x; con lote, decenas de veces el tiempo real. 12 GB dejan sitio para lote y un modelo más. Usada: 4 000-5 500 MXN `[estimado]`. |
| **1b. Si no hay sobremesa** | PC básico sin GPU (Ryzen 7 5700G, 16 GB: 8 819 MXN, comprobar fuente y ranura PCIe) + la GPU anterior; o PC armado con i7-12700F + RTX 5060 + 16 GB: **22 869 MXN** | **16 500-22 900 MXN** | Un pequeño servidor de transcripción en la red. |
| **2. Medio** | RTX 5060 Ti 16 GB | 12 519-14 169 MXN | Lo mismo con 16 GB: lote grande y sitio para un LLM local de 7-8 B para resumir (hoy la síntesis de notas es por reglas y no lo necesita). RTX 4060 Ti 16 GB (15 699) y RTX 4060 8 GB (7 119): agotadas, fin de serie. |
| **3. Holgado** | RTX 5070 12 GB (15 069-20 249 MXN) en sobremesa; o portátil nuevo con RTX 5060 de 8 GB | desde **26 659 MXN** (Lenovo LOQ 15AHP10) hasta ~48 000; con RTX 4060: 27 991 | Todo en una máquina; 8 GB bastan para `large-v3` fp16 con 3 GB de margen (lote 8 fp16 justo; usar int8_float16 con lote). Sigue compartiendo CPU, batería y ventilador con Teams. |
| Alternativa a 3 | Mac mini M4 16 GB / 512 GB: **19 499 MXN**; Mac mini M6 anunciado a 19 999 MXN (a la venta el 22-sep-2026) [F18] | 19 499-19 999 MXN | `large-v3` a **2,5x-4x** con Metal según benchmarks secundarios (`turbo` 10x-20x) [F19] `[terceros, sin método uniforme]`; más lento que una GPU de 7 679 MXN. |

### 2.4. GPU externa por Thunderbolt

* **No aplica a este portátil**: sin Thunderbolt ni USB4 no hay túnel PCIe (sección 1.1). La única
  vía sería un adaptador M.2 → OCuLink ocupando la ranura del SSD de arranque; no es recomendable.
* Por si se cambia de portátil y se quiere reutilizar la GPU: Razer Core X V2 (Thunderbolt 5,
  compatible TB4/USB4) **349,99 USD sin fuente de alimentación**; Sonnet Breakaway Box 750ex ~400
  USD con fuente; Minisforum DEG1 (OCuLink) 109-139 USD [F20] `[terceros]`. Pérdida por el enlace: en
  LLM se han medido **38,5 % menos tokens/s** por Thunderbolt 3 frente a PCIe x16 (con CPU distinta,
  no es limpio) [F21] `[terceros]`; para Whisper, que mueve ~1,5 MB de mel por ventana y carga el
  modelo una vez, no hay medición; la pérdida debería quedar **por debajo del 10-15 %** `[estimado]`.

### 2.5. ¿Hay camino sin GPU dedicada?

| Vía | Qué hay | Veredicto |
| :--- | :--- | :--- |
| **NPU** | No existe en el i7-1255U [F3]. | Descartada. |
| **GNA 3.0** | Coprocesador de ultra bajo consumo para redes pequeñas de audio (i8/i16, sin convoluciones 2D completas). **Discontinuado en OpenVINO 2024.0** («volver a 2023.3 LTS») [F4] `[autor]`. Ni `small` cabe en sus restricciones `[estimado]`. | Descartada. |
| **Iris Xe con whisper.cpp + OpenVINO** | Solo acelera el **codificador**; el decodificador sigue en CPU [F6]. En Iris Xe un usuario reporta «algo más rápido», con la GPU al 20-40 % [F6] `[anecdótico]`. En CPU, OpenVINO da un 16 % sobre whisper.cpp puro (`small`, i7-12700K) [F1]. El conversor no incluye `turbo` («not planned») [F6]. | Ayuda donde está el cuello de botella, pero exige cambiar de motor y no cubre `turbo`. |
| **Iris Xe con whisper.cpp + Vulkan** | whisper.cpp 1.8.3 logra **3-4x sobre CPU** en Radeon 680M y en la Arc de 128 EU de un Core Ultra 155H [F7] `[autor del PR]`. En una UHD 730 Gen12 de 24 EU (antes de 1.8.3) Vulkan fue **más lento que la CPU** y SYCL 2x más rápido [F6] `[terceros]`. | En esta Iris Xe (96 EU Gen12) cabe esperar **1,3x-2x sobre whisper.cpp en CPU** `[estimado]`, y menos frente a faster-whisper int8 con MKL. |
| **whisper.cpp + SYCL** | Verificado por los autores en i7-1165G7 (Iris Xe 96 EU); Windows «en curso»; hay un fallo abierto de segfault en iGPU Intel [F6] `[autor]`. | Frágil en Windows. |
| **OpenVINO GenAI `WhisperPipeline`** (todo en la iGPU) | Intel publica `large-v3` int8 y `turbo` int4 en formato OpenVINO [F8]. Única cifra en iGPU: whisper-base int8 en una Arc 140V (Lunar Lake, mucho más potente que esta Xe): **+30 % sobre la CPU** [F8] `[terceros]`. Hay un bug abierto del compilador de GPU con el decodificador int8 de large-v3 [F8]. Intel AI Playground exige Core Ultra o Arc discreta. | Sin cifras para Iris Xe; ganancia pequeña donde sí las hay. |
| **Contenedor de Speechmatics** | Corre en CPU con 1 vCPU y 2-5 GB (ver `stt-nube-y-privacidad.md`). | Única vía comercial sin GPU; velocidad real en este portátil sin medir; licencia con precio de ventas. |
| **Segunda máquina solo CPU** | Ryzen 9 7950X (AVX-512, lo que CT2 recomienda): sin cifras publicadas; `[estimado]` 4-6x sobre este portátil → `turbo` 4-6x, `large-v3` 1,5-2x. Un i7-13700K no tiene AVX-512 [F12]. | Una GPU usada de 2018 (2080 Ti: 15x) rinde más por menos dinero. |

**Veredicto:** la iGPU vale un benchmark de 30 minutos con `whisper-bench` (Vulkan y SYCL, modelo
`turbo`) cuando el equipo esté en reposo, pero no es el plan: la fusión de fragmentos da una
ganancia parecida sin cambiar de motor, y ninguna de estas vías lleva `large-v3` al tiempo real.

---

## 3. Qué modelo usar en cada caso

### 3.1. Tabla de modelos locales con soporte de español

WER en español: FLEURS según las tablas del paper de Whisper (tiny → large-v2) `[autor]` [F22];
Common Voice 13 y Multilingual LibriSpeech según un paper de 2025 que evaluó toda la escalera con la
misma normalización `[terceros]` [F23]; el resto, según se indica. Velocidades en esta CPU: las
`[medido]` vienen de `rendimiento.md`.

| Modelo | Español | WER es: FLEURS `[autor]` / CV13 / MLS `[terceros]` | Parámetros | Velocidad en esta CPU | Cuándo |
| :--- | :--- | ---: | ---: | :--- | :--- |
| Whisper tiny | Sí, débil | 15,9 / 27,7 / 17,3 | 39 M | ~15x-25x `[estimado]` | Nunca para reuniones. |
| Whisper base | Sí, débil | 9,9 / 18,4 / 11,5 | 74 M | ~10x-15x `[estimado]` | Solo para probar el pipeline. Un estudio con `base` midió ~8 puntos de diferencia entre acentos peninsulares y mexicano/caribeño [F24] `[terceros]`. |
| **Whisper small** | Sí | 5,6 / 9,7 / 6,6 | 244 M | **5,4x** haz 1; **3,0x** haz 5 + prompt; 12 % WER en audio técnico sintético `[medido]` | Daily corto en vivo con Teams; `vocab` y `fixes` obligatorios. |
| Whisper medium | Sí | 3,6 / 6,4 / 4,6 | 769 M | **1,2x** haz 5 + prompt | Descartado: `turbo` es mejor y más rápido. En español `medium` ≈ `large` según el paper. |
| Whisper large-v2 | Sí | 3,0 / 5,2 / 3,7 | 1 550 M | ~0,3x `[estimado]` | Referencia; `turbo` lo iguala. |
| **Whisper large-v3-turbo** | Sí | «como large-v2» [F25] `[autor]`; 6,9 % en CV17 según una ficha de ajuste fino [F26] `[terceros]`; sin cifra oficial en español | 809 M | **1,0x** haz 5 + prompt; 1,3x haz 1; **0,33x** con Teams `[medido]`; 2x-4x afinado `[estimado]` | Reuniones técnicas en CPU, después de optimizar. |
| **Whisper large-v3** | Sí | 2,8-3,1 / **4,4** / **2,9**; CV15 4,7; leaderboard multilingüe es 3,65 [F23, F27] `[terceros]` | 1 550 M | 0,3x-0,4x hoy; 0,6x-1,6x afinado `[estimado]` | Solo con GPU: el mejor de la familia en español. |
| Distil-Whisper oficial (v3, v3.5) | **No: solo inglés** [F28] `[autor]` | — | 756 M | — | No aplica. |
| Distil-Whisper comunitario es (`distil-whisper-large-v3-es`, conversión CT2 `Einstellung/faster-distil-whisper-large-v3-es`) | Sí, ajustado en Common Voice 16.1 | 5,1 en su propio test [F28] `[autor]`; sin terceros | ~800 M | Como `turbo` `[estimado]` | Poco interés: **mismo codificador** que `turbo` (el coste en CPU), y el paper de Whisper-LM observó que ajustar solo con Common Voice (frases leídas) **empeoró hasta un 40 %** en MLS/FLEURS [F23] `[terceros]`: riesgo para habla espontánea. |
| **NVIDIA Parakeet-TDT 0.6B v3** | Sí, 25 idiomas europeos [F29] | FLEURS **3,45** / MLS 4,39 / CoVoST 3,41; en su paper, frente a large-v3: 3,45 vs 3,12 / 4,39 vs 4,89 / 3,41 vs 4,32 [F29] `[autor]`; leaderboard es 3,73 `[terceros]` | 600 M; ONNX int8 640 MB | Sin medir aquí. `onnx-asr`: 36x en un Ryzen 9800X3D; `sherpa-onnx`: RTF 0,33 con 2 hilos [F30] `[terceros]`. En este portátil **5x-15x** `[estimado]` | Candidato serio para CPU. CC-BY-4.0. Corre en Windows con `sherpa-onnx` / `onnx-asr` (NeMo exige WSL2). Timestamps por palabra y puntuación. **No tiene `initial_prompt`**: la palanca `vocab` desaparece, solo quedan los `fixes`. |
| NVIDIA Canary-1B v2 | Sí, 25 idiomas [F31] | FLEURS **2,90** / MLS 2,94 / CoVoST 3,81 [F29] `[autor]`; leaderboard es 3,25 | 978 M; ≥6 GB RAM | Sin cifra en CPU; `onnx-asr` lo soporta | Mejor que Parakeet en español pero codificador-decodificador (alucina como Whisper en teoría) y más pesado. |
| Qwen3-ASR 1.7B / 0.6B (enero de 2026, Apache-2.0) | Sí, 30 idiomas [F32] | 1.7B: FLEURS 3,36 / CV 4,65 / MLS 4,63; 0.6B: 4,94 / 7,16 / 7,19 [F32] `[autor]`; leaderboard es 3,87 (1.7B) | 1,7 / 0,6 B | Oficialmente solo GPU. Comunidad: `Qwen3-ASR-GGUF` (Windows, ONNX + llama.cpp) RTF 0,39 en un portátil sin especificar; ONNX int8 0.6B RTF 0,32 en sobremesa [F32] `[terceros]`; aquí **1,5x-2,5x** con 0.6B `[estimado]` | Vigilar; la ruta en Windows es comunitaria y más lenta que Parakeet. Timestamps solo con un alineador aparte. |
| Mistral Voxtral Mini 3B / Small 24B / Realtime 4B | Sí | Mini: FLEURS 3,52 / CV 4,98 / MLS 5,12; Small: 2,72 / 3,31 / 3,62 [F33] `[autor]` | 3 / 24 / 4 B | Mini en CPU (GGUF Q4): **11 s de audio en 70 s** (RTF 6,4) [F33] `[terceros]`; Mini necesita 9,5 GB de VRAM; Realtime ≥16 GB de GPU y llama.cpp no lo soporta | Inviable en esta CPU; con GPU de 16 GB es una opción, sin ventaja clara sobre large-v3. Sin timestamps. |
| Moonshine es (Tiny 34 M / Small 123 M) | Sí | 6,2 / 4,9 en «FLEURS+MLS», 400 clips [F34] `[autor]` | 34-123 M | Muy rápido | Licencia dudosa para uso comercial en idiomas distintos del inglés; el autor documenta repeticiones como fallo habitual. |
| Phi-4-multimodal, Granite Speech 3.3 8B, SeamlessM4T v2 | Sí | Phi-4: CV15 4,47 / FLEURS 3,02 `[autor]` | 5,6-9 B | GPU | Seamless es no comercial; los otros exigen GPU. |
| wav2vec2-XLSR es, Vosk es 0.42 | Sí | 8,8 (CV) / 7,5 (CV) `[autor]` | 315 M / 1,4 GB | Tiempo real en CPU | Sin puntuación ni mayúsculas; no para reuniones. |
| Kyutai STT, Parakeet v2, Canary-Qwen | **No** (en / en-fr) | — | — | — | Descartados. |

### 3.2. Tabla de decisión por situación

| Situación | Sin GPU (hoy y tras optimizar) | Con GPU en la red (sección 5) |
| :--- | :--- | :--- |
| **Daily de 15 min, en vivo, con Teams** | `small`, haz 1-2, `vocab` y `fixes`. 5,4x medido; con Teams sigue >2x. El 12 % de WER se concentra en anglicismos, que es lo que `fixes` corrige. | `large-v3` fp16, haz 5. |
| **Reunión técnica de 1-2 h, en vivo** | `turbo`, haz 5, `vocab`, tras fusión + hilos. Si la cola crece: haz 2. | `large-v3` fp16, haz 5; drenado por lote. |
| **Reunión de decisiones donde la calidad manda** | Grabar y transcribir después con `turbo` en reposo (2x-4x afinado); o `large-v3` de noche (0,6x-1,6x). | `large-v3`, haz 5, `BatchedInferencePipeline`. |
| **Portátil cargado (Teams + IDE + navegador)** | `small`; o Recorder en `BELOW_NORMAL` y drenar después. | Indiferente: el portátil solo captura. |
| **Piloto de velocidad en CPU** | Parakeet-TDT 0.6B v3 con `sherpa-onnx` (int8, búsqueda *greedy*), midiendo WER y siglas en una grabación real frente a `turbo`. | No hace falta. |

---

## 4. Qué modelos locales alucinan menos

### 4.1. Whisper

* **Terceros midieron en habla real.** «Careless Whisper» (FAccT 2024): 13 140 segmentos en inglés
  (AphasiaBank), **1,4 % con frases enteras inventadas**; el **38 %** de esas invenciones eran dañinas;
  el predictor es la **proporción de tiempo sin voz**. Al repetir en diciembre de 2023 solo 12 de 187
  segmentos antes problemáticos seguían alucinando: la API mejoró entre versiones, sin desaparecer.
  Google, AWS, Azure, AssemblyAI y RevAI dieron 0 en los mismos segmentos [F35].
* **Terceros midieron en no-voz, a gran escala.** Con `large-v3` sobre **301 317 clips sin habla**
  (AudioSet, MUSAN, UrbanSound8K, silencio sintético): **40,3 % producen texto**; el 67 % de las
  alucinaciones son solo 1 270 cadenas distintas («thank you» 24,8 %, «thanks for watching» 10,3 %).
  **Silero VAD fue la mejor mitigación individual y VAD + lista de frases la mejor combinada** [F36].
  Es exactamente el diseño actual de Recorder.
* **Terceros midieron el mecanismo.** Calm-Whisper (Interspeech 2025): `large-v3` responde con
  texto al **99,97 %** de UrbanSound8K, frente al **13,5 % de un Conformer-CTC** del mismo tamaño;
  **3 de las 20 cabezas de atención** del decodificador causan más del 75 %; ajustándolas con audio
  no vocal y etiqueta vacía la alucinación baja más del 80 % con +0,07 de WER [F37]. Inglés; sin pesos
  para CTranslate2.
* **Terceros, 2026.** «Hallucination Space Projection»: método **sin reentrenar**, en inferencia, que
  baja la alucinación en no-voz de 31,3 % a 2,4 % a cambio de 0,3-4,4 puntos de WER [F38]. Otro
  trabajo con *steering* por autoencoders dispersos: `large-v3` 86,9 % → 27,3 %, `small` 72,6 % →
  14,1 % [F38]. «The Null Token Knows» (15 idiomas, español incluido pero sin desglose): **la tasa de
  alucinación no baja con el tamaño del modelo** aunque el WER sí [F38]. Ninguno está en
  `faster-whisper`.
* **¿v3 peor que v2?** Deepgram lo afirmó días después del lanzamiento midiendo WER, no
  alucinaciones [F39] `[terceros, débil]`. La única anotación humana encontrada (HALAS, 2026, habla
  real difícil, muestreo sesgado) da **v2 43,8 %, v3 23,8 %, turbo 29,4 %, CrisperWhisper 21,4 %,
  Canary-1B 33,6 %, Parakeet-TDT v2 33,7 %** [F40] `[terceros]`: en habla difícil v3 no es peor que
  v2, y Parakeet también alucina ahí. En el hilo de lanzamiento de v3, usuarios reportan «varias por
  cada 10 minutos» en inglés y, en japonés, que se concentran en silencios y música [F41]
  `[anecdótico]`. **Sobre `turbo` solo hay anécdotas.**
* **El origen de «suscríbete» y «amara.org»** son los créditos de subtítulos sobre silencio o música
  en los datos de entrenamiento; están documentadas variantes en es, pt, de e it [F41]
  `[anecdótico, muy replicado]`. **Hueco declarado:** no se encontró ningún estudio que cuantifique
  alucinaciones de Whisper en español.

### 4.2. Modelos transductores (Parakeet) y codificador-decodificador (Canary)

* **Argumento técnico, con respaldo medido:** un transductor (TDT/RNN-T) o un CTC emite un símbolo
  «blanco» por trama sin voz; no tiene un modelo de lenguaje autorregresivo que «quiera» seguir
  escribiendo. Con **los mismos datos de entrenamiento**, OWSM v3.1 (codificador-decodificador)
  responde «thank you» al ruido y su gemelo OWSM-CTC responde «.» [F42] `[terceros]`. AssemblyAI, con
  método público, midió texto no vacío en clips de ruido: **Whisper large-v3 99,5-100 %, Canary-1B v1
  100 %, su transductor 10,5 %** [F43] `[terceros, vendedor]`. Otro paper de 2026: al inducir pérdida
  de anclaje acústico, los CTC/RNN-T de NeMo producen «fragmentos ininteligibles o bucles, no
  fabricación fluida (0 de 354)» [F42].
* **Parakeet v3.** Su paper dice que entrenó con **36 000 h de no-voz con etiqueta vacía** para
  «reducir alucinaciones heredadas del pseudoetiquetado con Whisper» [F29] `[autor]`; la ficha no
  publica métrica de alucinación, solo WER bajo ruido (6,3 % limpio → 11,7 % a 0 dB). Anécdotas: en
  un servidor de 2 vCPU «en cada segmento silencioso devuelve nada»; en `sherpa-onnx`,
  **`modified_beam_search` sí alucina en silencio y `greedy_search` no**; y un fallo inverso: una cola
  de silencio puede vaciar un segmento corto [F30] `[anecdótico]`.
* **Canary v2.** NVIDIA publica «caracteres por minuto sobre 48 h de MUSAN»: **134,7** (Canary-flash
  60,9), sin comparar con Whisper [F31] `[autor]`. La v1 alucinó como Whisper en la prueba de
  AssemblyAI; la v2 no ha sido re-medida por terceros en silencio.

### 4.3. El resto

* **Voxtral:** el batch `mini-2507` «alucina en la gran mayoría de las muestras de silencio» (incluso
  una fecha en español) y el Realtime «casi las elimina», según un integrador [F33] `[anecdótico]`.
* **Qwen3-ASR:** un paper de 2026 mide 38 veces menos inserciones que Whisper **small** (no large) y
  <4 % de repetición con silencio inyectado frente a 57-60 % de `small` [F32] `[terceros]`; hay bucles
  reportados en chino y el toolkit oficial admite posprocesar «alucinaciones y repeticiones»
  `[anecdótico/autor]`.
* **Moonshine** documenta repeticiones como su fallo más común `[autor]`; **Kyutai** no cubre español;
  **Granite** sin datos.

### 4.4. Resumen

| Modelo | Español | Evidencia sobre alucinación en silencio | Nivel |
| :--- | :--- | :--- | :--- |
| Whisper large-v3 / turbo | Sí | En contra: 40-100 % de clips sin voz producen texto; VAD + lista negra es la mejor mitigación | Terceros |
| Whisper large-v2 | Sí | Igual que v3; peor que v3 en la única anotación humana | Terceros |
| Calm-Whisper / SAE / HSP | Sin evaluar en español | −80 a −92 % en no-voz | Terceros (papers, sin pesos CT2) |
| **Parakeet-TDT 0.6B v3** | Sí | Estructural (CTC/transductor: 10-13 % frente a 99-100 %); 36 000 h de no-voz; «devuelve nada» con *greedy* | Terceros (arquitectura) + autor + anecdótico |
| Canary-1B v2 | Sí | 134,7 car/min en ruido sin comparación; v1 alucinó como Whisper | Autor / terceros |
| Qwen3-ASR | Sí | Menos inserciones que Whisper small; bucles reportados | Terceros (parcial) |
| Voxtral Mini (batch) | Sí | Alucina en silencio según un integrador | Anecdótico |

### 4.5. Qué hacer hoy con `faster-whisper` 1.2.1 `[medido en el código + terceros]`

* **`vad_filter=True` (Silero) es la mejor defensa medida** [F36]. El micrófono de este portátil
  «gatea a cero» cuando no hay voz y produce silencio digital puro, el caso más patológico de los
  estudios; el VAD lo elimina antes del decodificador.
* En `faster-whisper`, un segmento solo se descarta como silencio si `no_speech_prob > 0,6` **y**
  `avg_logprob < −1,0` a la vez: una alucinación *confiada* («Gracias por ver») pasa. El filtro propio
  de Recorder, que evalúa cada umbral por separado, es lo correcto; bajar `no_speech_threshold` a
  0,3-0,4 en el filtro propio es más seguro que subir `logprob_threshold`, que además dispara los
  reintentos por temperatura.
* `hallucination_silence_threshold` existe (heurística sobre las 8 primeras palabras; exige
  `word_timestamps=True`, que encarece el decodificador); usuarios reportan que borra habla real en
  los bordes de la ventana de 30 s [F44] `[anecdótico]`. Redundante si el VAD funciona.
* `condition_on_previous_text=False` (ya activo) es la medida más citada contra transcripciones
  fantasma; `temperature=0` hace determinista pero **anula la vía de escape** de los bucles: si se
  usa, el filtro de `compression_ratio` debe descartar el segmento en vez de esperar un reintento.
* `initial_prompt` mejora términos técnicos pero **el modelo lo repite en silencios** (ocupa el
  hueco de «texto previo») [F44] `[anecdótico]`; conviene corto, en español neutro, sin frases de
  cierre ni listas largas. `hotwords` existe como alternativa que solo afecta al prefijo.
* `suppress_tokens` para «Amara» es peligroso: suprime esos subtokens también dentro de palabras
  normales. La lista negra por segmento es más segura, y el 67 % de las alucinaciones son unas pocas
  cadenas: vale la pena registrar y contar las descartadas.
* Con Parakeet no habría `no_speech_prob` ni `avg_logprob`; la defensa pasaría a ser el VAD, la
  búsqueda *greedy* y la lista negra.

---

## 5. Delegar la transcripción a un segundo equipo

### 5.1. Qué habría que construir

La buena noticia es que casi todo existe. Hay servidores listos sobre `faster-whisper` que exponen
la **API de OpenAI (`POST /v1/audio/transcriptions`)**: Speaches (MIT, Docker, streaming), WhisperLive
(WebSocket, con imágenes Docker) y docker-whisper (compatible con OpenAI, con CUDA) [F45, F46]. Con
`response_format=verbose_json` devuelven los segmentos con `no_speech_prob`, `avg_logprob` y
`compression_ratio`, que es lo que consume el pipeline de filtros de Recorder; **los filtros no
cambian**.

En Recorder el cambio es pequeño:

1. Una clase `RemoteTranscriber` en `engine/` con el mismo contrato que `model.transcribe()`:
   convierte el fragmento a WAV int16, lo envía con `language`, `beam_size`, `initial_prompt` y
   `vad_filter`, y devuelve segmentos con los mismos campos. `whisper_worker._process()` no cambia.
2. Tres claves en `config.json`: `server_url`, `server_timeout_sec` y `spool_dir`.
3. Un **spool en disco**: cada fragmento se escribe como WAV con su `t0` en el nombre antes de
   enviarse y se borra al recibir respuesta.
4. Reintento con espera creciente (el mismo patrón `retry_delay` de `capture.py`) y un aviso en la
   interfaz («⛔ servidor, reintento n»), como ya se hace con las fuentes caídas.

Coste: uno o dos días de trabajo con pruebas, más medio día para montar el servidor (Docker con
CUDA en Windows o Linux, modelo `large-v3` float16).

### 5.2. Red: ancho de banda y latencia

* Cada fragmento sale de `capture.py` como **float32 mono a 16 kHz: 64 KB por segundo, unos 640 KB
  por cada 10 s** `[medido en el código]`. Eso son **512 kbit/s por fuente**; con salida y micrófono a
  la vez, **1 Mbit/s de pico**, y de media 0,5-0,7 Mbit/s porque las dos fuentes rara vez producen
  fragmentos simultáneos `[estimado]`.
* **Convertir a int16 antes de enviar es gratis y lo deja en 256 kbit/s por fuente** sin pérdida
  útil (Whisper trabaja sobre el espectrograma; los 16 bits de WASAPI son la fuente original).
* **¿Compensa comprimir?** En una red local cableada (1 Gbit/s) o Wi-Fi (≥50 Mbit/s), 1 Mbit/s es un
  1-2 % del enlace: **no**. FLAC sin pérdida dejaría ~100-150 kbit/s y Opus a 32 kbit/s un 3 % del
  tamaño `[estimado]`; solo tienen sentido si el servidor está detrás de una VPN o de un punto de
  acceso móvil. Con Opus habría que medir el WER, porque no se encontró una medición de su efecto en
  Whisper.
* **Latencia por fragmento de 10 s** `[estimado]`: subir 320 KB (int16) tarda 26 ms a 100 Mbit/s o
  ~130 ms en un Wi-Fi de 20 Mbit/s; la inferencia de `large-v3` en una RTX 3060 para una ventana de
  30 s ronda 1-3 s. **Del final del fragmento al texto: 2-4 s**, frente a los ~10 s actuales
  (`turbo` a 1,0x) y a los 30 s con Teams abierto.

### 5.3. Si se cae la red a mitad de reunión

Nada se pierde si el spool existe: la captura sigue llenando `chunk_queue` y el disco; al volver el
servidor se drena en orden con las marcas de tiempo originales (`t0` viaja con cada fragmento). Dos
horas con dos fuentes en int16 son **~460 MB** de spool `[estimado]`, irrelevante para el disco. La
única decisión es qué hacer mientras tanto: esperar (texto en vivo interrumpido, nada perdido) o
**caer a un modelo local pequeño** (`small`) para seguir viendo texto, marcando esos tramos como de
menor calidad. Lo segundo es una mejora, no un requisito.

Si el servidor está en la misma oficina, el audio **no sale de la red**, que era la condición de
`stt-nube-y-privacidad.md`. Conviene cerrar el puerto al resto de la red o poner un token.

### 5.4. ¿Compensa frente a una eGPU o a cambiar de portátil?

| Opción | Coste | Calidad | Efecto en el portátil | Veredicto |
| :--- | ---: | :--- | :--- | :--- |
| eGPU por Thunderbolt | — | — | — | **Imposible en este portátil** (sin Thunderbolt/USB4). |
| Sobremesa existente + RTX 3060 12 GB + servidor | **7 679 MXN** + 1-2 días | `large-v3` a 8x-10x | El portátil solo captura: Teams deja de competir con la transcripción. | **La mejor relación**, si hay un sobremesa en la red encendido durante las reuniones. |
| Sobremesa nuevo + GPU | 16 500-22 900 MXN | Ídem | Ídem | Bien si además sirve para otras cosas (LLM local, CI). |
| Mac mini M4 / M6 como servidor | 19 499-19 999 MXN | `large-v3` a 2,5x-4x `[terceros, no uniforme]` | Ídem | Suficiente para dos fuentes, pero más caro y más lento que una GPU de 7 679 MXN. |
| Portátil nuevo con RTX 5060 8 GB | desde 26 659 MXN | `large-v3` a 8x-12x `[estimado]` | Todo en uno; Teams y Whisper vuelven a compartir CPU, ventilador y batería. | Solo si el cambio de portátil iba a hacerse de todas formas. |

**Recomendación de la sección 5: sí, delegar**, en cuanto exista un sobremesa en la red local. Es
la opción más barata que da `large-v3`, la única que descarga al portátil durante la llamada, y su
modo de fallo (red caída) tiene solución barata con el spool. Cambiar de portátil no resuelve mejor
el problema, cuesta más del triple y mantiene la competencia con Teams.

---

## 6. Recomendación ordenada

| Orden | Acción | Coste | Resultado esperado |
| :---: | :--- | ---: | :--- |
| **1** | **Medir en reposo** con `python tools\medir_rendimiento.py` (hilos 4/6/8/10) y `--fusion 30`; poner el `cpu_threads` ganador; **implementar la fusión de fragmentos pendientes** hasta ~28 s en el worker (`rendimiento.md` §3.2). | 0 MXN; 15 min de medición + 1-2 h de código | `turbo` haz 5 de 1,0x a **2x-4x** en reposo `[estimado]`; sin cola en reuniones normales. |
| **2** | **Política por reunión**: `small` haz 1-2 para dailies con Teams abierto; `turbo` para reuniones técnicas; grabar y drenar después cuando la calidad mande. Acortar el `vocab` a siglas y nombres, o probar `hotwords`, si aparecen palabras que nadie dijo. | 0 MXN | Deja de crecer la cola donde más molesta. |
| **3** | **Delegar a un sobremesa de la red con una RTX 3060 12 GB** y Speaches (o equivalente), con `RemoteTranscriber` y spool en Recorder. Si no hay sobremesa, un PC básico más la GPU. | **7 679 MXN** (o 16 500-22 900 MXN con PC) + 1-2 días | `large-v3` fp16 en vivo a 8x-10x; el portátil solo captura; latencia de 2-4 s. |
| 4 (opcional) | Piloto de **Parakeet-TDT 0.6B v3** con `sherpa-onnx` (int8, *greedy*) sobre una grabación real, comparando WER y siglas frente a `turbo`. Solo si el paso 3 se retrasa. | 0 MXN; 1 día | Posible 5x-15x en CPU `[estimado]` y muchas menos alucinaciones en silencio (evidencia arquitectónica, no medida en español); pierde `vocab`. |
| 5 (solo si toca renovar) | Portátil con RTX 5060 de 8 GB. | desde 26 659 MXN | `large-v3` en el propio equipo; no resuelve la competencia con Teams. |
| No | eGPU (imposible aquí), `medium`, `large-v3` en esta CPU, iGPU/OpenVINO como plan principal, Distil-Whisper, Voxtral en CPU. | | |

**Lo primero:** el paso 1, hoy mismo, cuando Recorder no esté transcribiendo. Es gratis, no toca la
calidad y decide si el paso 3 es urgente o puede esperar.

---

## 7. Qué quedó sin verificar

* Las **QuickSpecs oficiales** del ProBook 440 G9 (no se pudieron descargar). La ausencia de
  Thunderbolt se apoya en el inventario PnP del equipo, en la ficha de HP citada por terceros y en
  dos reseñas; un vistazo al puerto USB-C (sin el rayo serigrafiado) lo cierra.
* Las **ganancias de hilos y fusión** son estimaciones a partir de una sola relación medida (1,10x);
  la de hilos puede ser nula en una CPU híbrida. La herramienta de medición existe y tarda 15 min.
* La **velocidad de `large-v3` con faster-whisper en una RTX 3060 o en cualquier RTX 50**: las
  cifras publicadas son de una 2080 Ti (15x), de una 3070 Ti (12x, large-v2), de `openai/whisper`
  (3060: 1,7x) o de un servicio por lotes (3060: ~20x); el 8x-10x sin lote es extrapolación.
* Cualquier cifra de **Parakeet en CPU de portátil** y su comportamiento con **siglas y anglicismos
  en español de México** sin `initial_prompt`.
* **Alucinaciones en español**: no hay medición de terceros para ningún modelo; las cifras de
  Parakeet/Canary en silencio son del autor o anecdóticas.
* **Whisper en la Iris Xe de 96 EU**: no hay benchmark publicado con ningún backend; el 1,3x-2x es
  estimado por analogía con una UHD 730 y una Arc 140V.
* **Efecto de Opus** en el WER si se comprimiera el audio hacia el servidor.
* Los **precios** son de una tienda en un día concreto; el PC básico de 8 819 MXN habría que
  comprobarlo (fuente de alimentación y ranura PCIe x16); los de portátiles con RTX 5070 y de GPUs
  usadas no se obtuvieron.

---

## Fuentes

* [F1] README de faster-whisper (benchmarks en RTX 3070 Ti 8 GB y en i7-12700K; VAD; `BatchedInferencePipeline`): https://github.com/SYSTRAN/faster-whisper
* [F2] HP ProBook 440 G9: ficha de HP (https://support.hp.com/us-en/document/ish_5999031-5999203-16), soporte de HP sobre eGPU (https://h30434.www3.hp.com/t5/Notebook-Hardware-and-Upgrade-Questions/HP-ProBook-440-G9-Notebook-PC-Graphical-upgrade-options/td-p/9235210), Notebookcheck (https://www.notebookcheck.net/HP-ProBook-440-G9-5Y3Z3EA.1180072.0.html), LaptopMedia (https://laptopmedia.com/review/hp-probook-440-g9-review-14-inches-of-office-excellency/)
* [F3] Intel, ficha del Core i7-1255U (GNA 3.0, sin AI Boost): https://www.intel.com/content/www/us/en/products/sku/226259/intel-core-i71255u-processor-12m-cache-up-to-4-70-ghz/specifications.html
* [F4] OpenVINO 2024.0, notas de versión (GNA discontinuado) y documentación del plugin GNA 2023.3: https://www.intel.com/content/www/us/en/developer/articles/release-notes/openvino/2024-0.html
* [F5] Ficha de `openai/whisper-large-v3-turbo` (809 M; decodificador de 32 a 4 capas; aviso de alucinación): https://huggingface.co/openai/whisper-large-v3-turbo
* [F6] whisper.cpp: README (OpenVINO solo codificador), discusiones #1858 (Iris Xe), #2662 (Arc A380), #2996 (UHD 730: SYCL 72 s, CPU 142 s, Vulkan 223 s), issue #3252 (conversor sin `turbo`), README_sycl, issue #4014: https://github.com/ggml-org/whisper.cpp · https://github.com/ggml-org/whisper.cpp/discussions/1858 · https://github.com/ggml-org/whisper.cpp/discussions/2662 · https://github.com/ggml-org/whisper.cpp/discussions/2996 · https://github.com/ggml-org/whisper.cpp/issues/3252 · https://github.com/ggml-org/whisper.cpp/issues/4014
* [F7] whisper.cpp 1.8.3, PR #3492 y Phoronix (Vulkan en iGPU, 3-4x sobre CPU): https://github.com/ggml-org/whisper.cpp/pull/3492 · https://www.phoronix.com/news/Whisper-cpp-1.8.3-12x-Perf
* [F8] Modelos OpenVINO de Whisper, cifra en Arc 140V y bug del decodificador int8: https://huggingface.co/OpenVINO/whisper-large-v3-turbo-int4-ov · https://github.com/elizaOS/eliza/issues/7633 · https://github.com/openvinotoolkit/openvino/issues/33190 · https://github.com/intel/AI-Playground
* [F9] «Self-Host Whisper Large-v3 as a Transcription Server in 2026» (VRAM medida por el autor; velocidades por GPU citadas de 1qubit.de con `openai/whisper`): https://dev.to/jovan_chan_9500711396d4e6/self-host-whisper-large-v3-as-a-transcription-server-in-2026-faster-whisper-fastapi-3d9g · https://www.1qubit.de/en/ai/openai-whisper-performance-benchmarks
* [F10] faster-whisper, issue #1030 y ficha `deepdml/faster-whisper-large-v3-turbo-ct2` (large-v3 y turbo en RTX 2080 Ti, VRAM y WER): https://github.com/SYSTRAN/faster-whisper/issues/1030 · https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2/discussions/3
* [F11] Relleno a 30 s: faster-whisper `audio.py`/`transcribe.py`, issue #171 («not planned»), whisper.cpp issue #1855 (`audio_ctx`), whisper-acft: https://github.com/SYSTRAN/faster-whisper/issues/171 · https://github.com/ggml-org/whisper.cpp/issues/1855 · https://github.com/futo-org/whisper-acft
* [F12] CPU híbrida: llama.cpp discusión #572 (i7-12700H, solo P 2,4x), guía de Intel oneMKL para núcleos heterogéneos, CTranslate2 (rendimiento, paralelismo, variables de entorno), ficha del i7-13700K (sin AVX-512): https://github.com/ggml-org/llama.cpp/discussions/572 · https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-linux/2023-2/managing-performance-with-heterogeneous-cores.html · https://opennmt.net/CTranslate2/performance.html · https://opennmt.net/CTranslate2/parallel.html · https://www.intel.com/content/www/us/en/products/sku/230500/intel-core-i713700k-processor-30m-cache-up-to-5-40-ghz/specifications.html
* [F13] Referencias de CPU y GPU sin método uniforme: snailtext (5700G 0,33x; RTX 3090 5,3x), owehrens (Tesla T4): https://snailtext.app/blog/do-you-need-a-gpu-for-voice-to-text/ · https://owehrens.com/openai-whisper-benchmark-on-nvidia-tesla-t4-a100/
* [F14] SaladCloud, benchmark de large-v3 por lotes (RTX 3060 ≈ 20x, RTX 4080 40x): https://blog.salad.com/whisper-large-v3/
* [F15] Cyberpuerta, tarjetas: RTX 3060 12 GB (https://www.cyberpuerta.mx/Computo-Hardware/Componentes/Tarjetas-de-Video/Tarjeta-de-Video-ASUS-NVIDIA-GeForce-RTX-3060-Dual-V2-OC-12GB-192-bit-GDDR6-PCI-Express-4-0.html), RTX 5060 (https://www.cyberpuerta.mx/Tarjetas-de-Video-NVIDIA-GeForce-RTX-5060/), RTX 5060 Ti (https://www.cyberpuerta.mx/Tarjetas-de-Video-NVIDIA-GeForce-RTX-5060-Ti/), RTX 5070 (https://www.cyberpuerta.mx/Tarjetas-de-Video-NVIDIA-GeForce-RTX-5070/), RTX 4060 Ti (https://www.cyberpuerta.mx/NVIDIA-4060-Ti/)
* [F16] Cyberpuerta, PC de escritorio armados (i7-12700F + RTX 5060: 22 869 MXN; Ryzen 7 5700G sin GPU: 8 819 MXN): https://www.cyberpuerta.mx/PC-s-de-Escritorio-Xtreme-Pc-Gaming/
* [F17] Cyberpuerta, portátiles RTX serie 50 y RTX 40 (RTX 5060 desde 26 659 MXN; RTX 4060 27 991 MXN): https://www.cyberpuerta.mx/Laptops-NVIDIA-RTX-Serie-50/ · https://www.cyberpuerta.mx/Laptops-Gamer-NVIDIA-GeForce-RTX/
* [F18] Xataka México, Mac mini M4 (19 499 MXN tras retirar el de 256 GB) y Mac mini M6 / M5 Pro (19 999 / 39 999 MXN, 22-sep-2026): https://www.xataka.com.mx/ordenadores/apple-acaba-eliminar-uno-sus-productos-atractivos-mexico-mac-mini-15-mil-pesos · https://www.xataka.com.mx/ordenadores/nueva-apple-mac-mini-m6-m5-pro-lanzamiento-precio-mexico-caracteristicas-especificaciones-ficha-tecnica
* [F19] Whisper en Apple Silicon (benchmarks secundarios): https://justvoice.ai/blog/whisper-benchmark-apple-silicon-m3-m4 · https://whispernotes.app/blog/introducing-whisper-large-v3-turbo · https://github.com/ggml-org/whisper.cpp/issues/3139
* [F20] Carcasas eGPU: Razer Core X V2 (349,99 USD sin fuente), Sonnet 750ex, Minisforum DEG1: https://videocardz.com/newz/razer-core-x-v2-now-available-349-99-egpu-enclosure-with-thunderbolt-5 · https://www.adorama.com/cuxsngpu750w.html · https://store.minisforum.com/products/minisforum-deg1-egpu-dock
* [F21] Pérdida por Thunderbolt en inferencia: https://www.jan.ai/post/benchmarking-nvidia-tensorrt-llm · https://localaimaster.com/blog/egpu-local-ai-benchmarks
* [F22] Paper de Whisper (tablas de WER por idioma y tamaño): https://arxiv.org/pdf/2212.04356
* [F23] «Whisper-LM: Improving ASR Models with Language Models for Low-Resource Languages» (WER en español por tamaño, CV13 y MLS; efecto de ajustar solo con Common Voice): https://arxiv.org/pdf/2503.23542
* [F24] Estudio de acentos del español con Whisper (MDPI): https://www.mdpi.com/2076-3417/14/11/4734
* [F25] OpenAI, lanzamiento de `turbo` (≈ large-v2 por idioma): https://github.com/openai/whisper/discussions/2363
* [F26] Ficha de ajuste fino de `turbo` en español (6,91 % en CV17 antes del ajuste): https://huggingface.co/adriszmar/whisper-large-v3-turbo-es
* [F27] Open ASR Leaderboard (paper con pista multilingüe): https://arxiv.org/html/2510.06961v4 · https://huggingface.co/blog/open-asr-leaderboard
* [F28] Distil-Whisper oficial (inglés) y variantes comunitarias en español: https://github.com/huggingface/distil-whisper · https://huggingface.co/marianbasti/distil-whisper-large-v3-es · https://huggingface.co/Einstellung/faster-distil-whisper-large-v3-es
* [F29] Ficha de `nvidia/parakeet-tdt-0.6b-v3` y paper de Canary v2 / Parakeet v3 (WER por idioma frente a large-v3; 36 000 h de no-voz): https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 · https://arxiv.org/pdf/2509.14128
* [F30] Parakeet en CPU: `sherpa-onnx` (int8, RTF 0,33 con 2 hilos; issue #3267 sobre *beam search* y silencio), `onnx-asr` (36x en 9800X3D), NeMo issue #15757, relato en servidor de 2 vCPU: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html · https://github.com/k2-fsa/sherpa-onnx/issues/3267 · https://github.com/istupakov/onnx-asr · https://github.com/NVIDIA-NeMo/Speech/issues/15757 · https://dev.to/thebuciyo/i-replaced-whisper-with-parakeet-on-a-55month-cpu-server-here-is-what-actually-happened-2a0f
* [F31] Ficha de `nvidia/canary-1b-v2` (134,7 car/min en MUSAN) y `canary-1b-flash`: https://huggingface.co/nvidia/canary-1b-v2 · https://huggingface.co/nvidia/canary-1b-flash
* [F32] Qwen3-ASR: repositorio, informe técnico (WER en español), rutas en CPU (`Qwen3-ASR-GGUF`, ONNX 0.6B, puerto en C), paper sobre inserciones, issue #129: https://github.com/QwenLM/Qwen3-ASR · https://arxiv.org/html/2601.21337v1 · https://github.com/HaujetZhao/Qwen3-ASR-GGUF · https://huggingface.co/Daumee/Qwen3-ASR-0.6B-ONNX-CPU · https://github.com/antirez/qwen-asr · https://arxiv.org/abs/2604.21276 · https://github.com/QwenLM/Qwen3-ASR/issues/129
* [F33] Voxtral: paper (WER en español), fichas, GGUF con tiempos en CPU, llama.cpp «not planned» para Realtime, LiveKit #4754 (silencio): https://arxiv.org/html/2507.13264v1 · https://huggingface.co/mistralai/Voxtral-Mini-3B-2507 · https://huggingface.co/cstr/voxtral-mini-3b-2507-GGUF/blob/main/README.md · https://github.com/ggml-org/llama.cpp/issues/20914 · https://github.com/livekit/agents/issues/4754
* [F34] Moonshine (modelos y precisión en español): https://moonshine-voice.readthedocs.io/en/latest/models/available-models/ · https://moonshine-voice.readthedocs.io/en/latest/models/accuracy/
* [F35] Koenecke et al., «Careless Whisper: Speech-to-Text Hallucination Harms», FAccT 2024: https://arxiv.org/abs/2402.08021
* [F36] «Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio» (301 317 clips; VAD + lista negra): https://arxiv.org/abs/2501.11378
* [F37] Wang et al., «Calm-Whisper», Interspeech 2025: https://arxiv.org/abs/2505.12969
* [F38] «Hallucination Space Projection» (2026), *steering* con SAE (2026) y «The Null Token Knows» (2026): https://arxiv.org/abs/2609.04561 · https://arxiv.org/html/2606.07473 · https://arxiv.org/html/2608.15940
* [F39] Deepgram, «Whisper v3 results»: https://deepgram.com/learn/whisper-v3-results
* [F40] HALAS (anotación humana de alucinaciones, 2026): https://arxiv.org/html/2606.23048
* [F41] openai/whisper: lanzamiento de large-v3 (#1762), origen de las frases de subtítulos (#928, #1606): https://github.com/openai/whisper/discussions/1762 · https://github.com/openai/whisper/discussions/928 · https://github.com/openai/whisper/discussions/1606
* [F42] OWSM-CTC frente a OWSM v3.1 y «The Anatomy of an ASR Hallucination» (2026): https://arxiv.org/html/2402.12654v1 · https://arxiv.org/html/2609.04404
* [F43] AssemblyAI, «Anatomy of Industrial Scale Multilingual ASR» (clips de no-voz: Whisper 99,5-100 %, transductor 10,5 %): https://arxiv.org/html/2404.09841v1
* [F44] openai/whisper: PR #1838 (`hallucination_silence_threshold`), #1992 (prompt y alucinaciones), #679: https://github.com/openai/whisper/pull/1838 · https://github.com/openai/whisper/discussions/1992 · https://github.com/openai/whisper/discussions/679
* [F45] Speaches / faster-whisper-server (compatible con OpenAI, MIT): https://github.com/fedirz/faster-whisper-server · https://railway.com/deploy/speaches
* [F46] WhisperLive (WebSocket) y docker-whisper (OpenAI-compatible con CUDA): https://github.com/collabora/WhisperLive · https://github.com/hwdsl2/docker-whisper
