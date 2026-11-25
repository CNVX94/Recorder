# Plan de mejoras: experiencia de uso, temas, terminal y rendimiento

Noviembre de 2026. Plan por pasos con un prompt autocontenido para cada uno: se copia tal cual en
una sesión nueva abierta en este repositorio. Cada prompt lleva su contexto y sus reglas, así que no
depende de esta conversación ni de los demás prompts (solo de que los pasos previos estén aplicados).

---

## 1. Punto de partida (lo que hay hoy)

| Área | Estado actual | Consecuencia para el plan |
| :--- | :--- | :--- |
| Índice de código | CodeGraph inicializado el 24-nov-2026 (`codegraph init -i`): 91 archivos, 2 578 símbolos. `.codegraph/.gitignore` ya excluye la base de datos. | Todos los prompts piden explorar con `codegraph_*` antes de abrir archivos. En otro equipo: `codegraph init -i` en la raíz. |
| Colores | Catppuccin Mocha fijo en constantes de `recorder/ui/theme.py` (`BG`, `PANEL`, `FG`…), copiado a mano en `recorder/cli/consola.py` porque `recorder.ui` carga tkinter. | Hace falta una paleta única sin tkinter antes de cualquier tema. |
| Ayuda al usuario | No hay tooltips. Las explicaciones viven en el README y en `daily -h`. | Un módulo único de textos que usen ventana y terminal. |
| Ventana | Tkinter, tamaño de diseño 1040×560 con `fit_window` (DPI-aware). Cabecera con estado, medidores y botones empacados con `pack`. | El responsive pide `grid` con pesos y puntos de corte. |
| Terminal | `daily menu` es un menú numerado con `input()` (`recorder/cli/menu.py`). La pantalla en vivo (`recorder/cli/live.py`) ya lee teclas con `msvcrt` y pinta con `rich.Live`. Solo Windows. | El patrón de `live.py` se reutiliza; falta el lector de teclas para Linux. |
| GPU integrada | **No se usa en automático, a propósito**: `choose_vulkan_device` (`recorder/config/schema.py`) nunca elige una integrada; solo si `whispercpp_device` ≥ 0, y entonces como mucho `large-v3-turbo`. Nunca se ha medido whisper.cpp + Vulkan en la Iris Xe del i7-1255U. | Por eso «no queda claro si se aprovecha»: la app no muestra el motor real. Primero mostrarlo, después medir y decidir. |
| Métricas | `StatusSnapshot` (`recorder/session.py`) da cola pendiente y atraso. No hay CPU, RAM, GPU ni velocidad por fragmento. `cpu_threads: 0` = 4 hilos aunque haya 10 núcleos (`docs/rendimiento.md`). | Un muestreador ligero sin dependencias nuevas (ctypes, como `tools/medir_rendimiento.py`). |
| Ejecutable | Ya existe: `packaging/recorder.spec` genera `Recorder.exe` (ventana) y `daily.exe` (consola), con instalador Inno Setup. | La intro se empaqueta como assets del ejecutable. |

### Decisiones tomadas por defecto (cámbialas antes de lanzar el paso que afecta)

1. **Se mantiene Tkinter** (sin migrar a Qt ni a una interfaz web). Fundidos, transiciones de color, tooltips e intro por fotogramas son viables en Tk.
2. **El tema cristal queda condicionado a una prueba** (paso 2): Tk pinta fondos opacos, así que el «glass» real solo se consigue con el fondo de sistema de Windows 11 (Mica/Acrylic) en marcos y barra de título más transparencia de ventana. Si la prueba no es legible, se entregan claro y oscuro y se decide aparte. **Resultado: descartado.** Mica solo en la barra apenas se distingue del oscuro; Acrylic en toda la ventana lava los colores; `-alpha` mezcla el texto de detrás; y el color clave con Acrylic deja halos en las letras, deja pasar los clics a la ventana de detrás y no garantiza el contraste AA. Capturas en `docs/capturas-ui/cristal-prototipo-*.png`.
3. **Terminal con `rich` + lector de teclas propio** (sin Textual ni otras dependencias).
4. **La GPU integrada sigue desactivada por defecto** hasta medirla en el equipo (paso 6).
5. **Grabar en Linux queda fuera**: la captura es WASAPI (`pyaudiowpatch`). La terminal se hace portable (menús, opciones, notas), pero grabar en Linux necesita otro backend de audio (PulseAudio/PipeWire) y es una fase aparte.
6. **La intro sale solo la primera vez** y bajo demanda desde el menú.

---

## 2. Orden, dependencias y paralelismo

| Paso | Qué | Perfil | Depende de | Archivos principales | En paralelo con |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 0 | CodeGraph | — | — | `.codegraph/` | **Hecho** |
| 1 | Rendimiento I: motor real y métricas | código | — | `session.py`, nuevo `metricas.py`, `engine/*`, `cli/live.py` | **Hecho** |
| 2 | Sistema de temas | código | — | `ui/*`, `cli/consola.py`, `cli/configurar.py`, `config/schema.py` | **Hecho** (cristal descartado) |
| 3 | Textos de ayuda y tooltips | código | 2 | nuevo `ayuda.py`, `ui/*` | **Hecho** |
| 4 | Ventana: menú, responsive, animaciones, panel de rendimiento | código | 1, 2, 3 | `ui/*` | **Hecho** |
| 5 | Terminal interactiva | código | 1, 2, 3 | `cli/*` | **Hecho**; el pulido de todas las vistas de terminal sigue en `docs/plan-pulido-terminal.md` |
| 6 | Rendimiento II: ajuste por hardware y GPU integrada | código | 1, 4, 5 | `engine/*`, `config/*`, `ui/*`, `cli/*` | 7 |
| 7 | Diseño de la intro | diseño | 2 | `docs/intro/`, `recorder/assets/intro/` | 3, 4, 5, 6 |
| 8 | Intro en la app y empaquetado | código | 4, 7 | nuevo `ui/intro.py`, `packaging/*` | — |
| 9 | Verificación integrada | código | todos | `docs/verificacion-mejoras-ux.md` | — |

* Si dos pasos van en paralelo, cada uno en su propia copia de trabajo (worktree) y se integran uno tras otro.
* Pasos 4 y 5 tocan los dos `recorder/ayuda.py`: cada uno añade sus textos solo en su sección («Ventana» / «Terminal») para que la integración sea trivial.
* Campos nuevos de `config.json` y quién los crea: `theme` y `animations` (paso 2), ajustes de rendimiento (paso 6), `intro_seen` (paso 8). Los pasos 4 y 5 no añaden campos.
* Cada paso termina con un mensaje de commit sugerido; el commit lo haces tú después de revisar.

---

## 3. Vocabulario de los detalles visuales

Para pedir y revisar los detalles con el término exacto:

| Término | Qué es | Dónde se usa aquí |
| :--- | :--- | :--- |
| Fade-in / fade-out (fundido de entrada/salida) | Opacidad de 0 a 1 o al revés | Apertura y cierre de ventana, diálogos, intro |
| Crossfade (fundido cruzado) | Una vista se desvanece mientras aparece la otra | Cambio de tema, cambio de escena en la intro |
| Easing (curva de aceleración) | Cómo varía la velocidad de una animación: `ease-out` frena al final, `ease-in-out` arranca y frena suave | Todas las transiciones |
| Hover / pressed / focus state | Aspecto al pasar el ratón, al pulsar y al recibir el foco con teclado | Botones, opciones de menú |
| Focus ring (anillo de foco) | Borde visible del control activo al navegar con Tab | Accesibilidad con teclado |
| Microinteracción | Respuesta pequeña a una acción (un botón que cambia de color, un check que aparece) | Botones, guardar ajustes |
| Highlight decay (resaltado que se desvanece) | Un elemento nuevo aparece resaltado y vuelve a su color poco a poco | Última línea transcrita |
| Pulse (pulso) | Variación lenta y cíclica de brillo u opacidad | Indicador de grabación |
| Toast | Aviso efímero que aparece y se va solo, sin bloquear | Confirmaciones («Captura guardada») |
| Stagger (escalonado) | Varios elementos entran uno tras otro con un pequeño retraso | Opciones del menú, escenas de la intro |
| Tooltip | Globo de ayuda al pasar el ratón o enfocar un control | Todos los controles |
| Sparkline | Mini-gráfica de tendencia sin ejes | Panel de rendimiento |
| Reduced motion (movimiento reducido) | Preferencia del sistema o del usuario para quitar animaciones | Opción `animations` |
| Contraste WCAG AA | Relación de luminancia mínima: 4,5:1 texto normal, 3:1 componentes e iconos | Prueba automática de cada tema |
| Breakpoint (punto de corte) | Ancho a partir del cual el diseño se reorganiza | Ventana amplia / compacta / estrecha |

---

## 4. Prompts

### Paso 0. CodeGraph (hecho)

Ya está: `codegraph init -i` en la raíz, índice en `.codegraph/codegraph.db` (ignorado por
`.codegraph/.gitignore`). En otro equipo basta con instalar el CLI de CodeGraph y repetir el
comando. Commit sugerido (opcional, solo versiona el `.gitignore` interno):

```text
Agrega la configuración local del índice de código
```

---

### Paso 1. Rendimiento I: motor real y métricas

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams (audio WASAPI loopback + micrófono con pyaudiowpatch; faster-whisper int8 en CPU o whisper.cpp con Vulkan en GPU) y escribe una nota Markdown con capturas. Dos interfaces sobre el mismo núcleo (recorder/session.py: RecorderSession y StatusSnapshot): la ventana Tkinter (recorder/ui/) y la terminal con rich (recorder/cli/, comando `daily`). Se empaqueta con PyInstaller (packaging/recorder.spec) e Inno Setup. Equipo de desarrollo: portátil i7-1255U (2 núcleos P + 8 E, gráfica integrada Iris Xe, sin NVIDIA). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) para entender el código antes de abrir archivos; si no responde, ejecuta `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas salvo que la biblioteca estándar, tkinter, rich, numpy o Pillow no basten; si propones una, justifícala y espera aprobación.
5. Código, comentarios y textos en español, como el resto del repositorio. Cambios mínimos y localizados.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. No toques config.json del usuario ni reproduzcas audio por los altavoces sin comprobar antes que no suena nada más ni hay una llamada en curso.

Tarea: que se sepa en todo momento con qué motor y dispositivo se transcribe de verdad y cuánto le cuesta al equipo, con los datos listos para que la ventana y la terminal los pinten en pasos posteriores.

Hechos ya conocidos
- resolve_runtime y choose_vulkan_device (recorder/config/schema.py) eligen el motor. En automático nunca se elige una GPU integrada; solo si whispercpp_device >= 0. Hoy la interfaz no deja claro si corre CPU, CUDA o Vulkan, ni en qué GPU, ni si hubo caída a CPU.
- cpu_threads: 0 equivale a 4 hilos de CTranslate2 (docs/rendimiento.md).
- tools/medir_rendimiento.py ya mide la CPU del sistema con GetSystemTimes por ctypes: reutiliza el enfoque.
- StatusSnapshot ya trae pendiente y atraso.

Qué hacer
1. Un módulo sin interfaz (por ejemplo recorder/metricas.py) que muestree cada 1-2 s en un hilo ligero: CPU % del proceso (sumando whisper-server.exe si está en marcha) y del sistema, RAM del proceso, uso de GPU (contadores PDH «GPU Engine» por ctypes; si no se pueden leer, «n/d» sin error) y, del transcriptor: factor de tiempo real por fragmento (segundos de audio / segundos de proceso) con media móvil, tiempo del último fragmento, cola y atraso.
2. «Motor efectivo»: estructura y texto corto con motor (faster-whisper / whisper.cpp), dispositivo (CPU con N hilos, o nombre de GPU indicando integrada o dedicada), modelo, haz, y si hubo caída a CPU y por qué.
3. Exponerlo en StatusSnapshot (o un snapshot hermano) sin romper a quien ya lo usa.
4. En la pantalla en vivo de la terminal (recorder/cli/live.py) añade solo una línea mínima en el pie con motor efectivo y velocidad; la ventana no se toca en este paso (otro paso cambia sus colores en paralelo).
5. Al cerrar la sesión, escribe en el registro (recorder/registro.py) un resumen: motor efectivo, velocidad media y p95, CPU media, pico de cola.
6. Coste: el muestreo debe consumir menos del 1 % de CPU y nada corre en el hilo de audio.

Aceptación
- Pruebas con relojes y contadores falsos para velocidad y CPU %, y para la descripción del motor en: CPU, CUDA, Vulkan dedicada, Vulkan integrada forzada y caída a CPU.
- pytest y selftest pasan.
- En el informe, responde con datos de este equipo (lee config.json sin modificarlo): ¿qué motor y qué dispositivo usa la configuración actual, y con cuántos hilos?

Fuera de alcance: cambiar la elección del motor, el diseño final de las pantallas, mediciones de velocidad.
```

---

### Paso 2. Sistema de temas (claro, oscuro, cristal)

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams (audio WASAPI loopback + micrófono con pyaudiowpatch; faster-whisper int8 en CPU o whisper.cpp con Vulkan en GPU) y escribe una nota Markdown con capturas. Dos interfaces sobre el mismo núcleo (recorder/session.py): la ventana Tkinter (recorder/ui/) y la terminal con rich (recorder/cli/, comando `daily`). Se empaqueta con PyInstaller (packaging/recorder.spec) e Inno Setup. Equipo de desarrollo: portátil i7-1255U con Iris Xe, Windows 11. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) para entender el código antes de abrir archivos; si no responde, ejecuta `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas salvo que la biblioteca estándar, tkinter, rich, numpy o Pillow no basten; si propones una, justifícala y espera aprobación.
5. Código, comentarios y textos en español, como el resto del repositorio. Cambios mínimos y localizados.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.

Tarea: temas claro, oscuro y cristal, cuidando la vista del usuario (contraste y paleta agradable), aplicables en caliente.

Hechos ya conocidos
- Los colores son constantes Catppuccin Mocha en recorder/ui/theme.py (BG, PANEL, FG, DIM, ACC, MIC, ERR, SUCCESS, BORDER y los estilos BTN_STYLE, ENTRY_STYLE, LABEL_STYLE, HEADER_STYLE), importadas por la ventana y los diálogos. recorder/cli/consola.py las copia en un rich.Theme porque importar recorder.ui carga tkinter.
- fit_window y work_area (theme.py) ya ajustan tamaños a la escala de Windows.

Qué hacer
1. Paleta por tokens semánticos en un módulo sin tkinter (por ejemplo recorder/paleta.py): fondo, superficie, superficie_elevada, borde, texto, texto_tenue, acento, texto_sobre_acento, mic, error, ok, aviso, foco, tooltip_fondo, tooltip_texto, seleccion. Temas: «oscuro» (el Mocha actual, sin cambios visibles), «claro» (base Catppuccin Latte), «cristal» (oscuro con superficies translúcidas) y «sistema» (sigue el modo de Windows leyendo AppsUseLightTheme en el registro).
2. Contraste WCAG 2.2 AA: texto >= 4,5:1 y componentes/anillo de foco >= 3:1 en cada tema. Una prueba calcula la relación de contraste de cada par usado y falla si alguno baja.
3. Ventana: sustituye el uso directo de constantes por la paleta activa, con un único punto que aplique el tema en caliente a la ventana y a los diálogos abiertos, sin reiniciar. Barra de título clara u oscura según el tema con DWM (DWMWA_USE_IMMERSIVE_DARK_MODE).
4. Cristal, prueba antes de construir: Tk pinta fondos opacos; el efecto posible es el fondo de sistema de Windows 11 (DWMWA_SYSTEMBACKDROP_TYPE: Mica o Acrylic) en marco y barra de título, transparencia de ventana (-alpha) y superficies «escarchadas». Haz primero un prototipo mínimo, guarda una captura en docs/capturas-ui/ y evalúa legibilidad. Si no es legible o se ve pobre, no lo implementes a medias: entrega claro y oscuro y describe en el informe lo que se ve y las alternativas, para decidir.
5. Configuración en recorder/config/schema.py: «theme» (oscuro | claro | cristal | sistema; por defecto oscuro para no cambiar nada a nadie) y «animations» (completas | reducidas | ninguna; por defecto reducidas si Windows tiene desactivadas las animaciones, SPI_GETCLIENTAREAANIMATION, y completas si no). Un config.json antiguo sin estos campos debe cargar igual. Este paso solo crea «animations»; las animaciones llegan después.
6. Selector de tema en Opciones de la ventana y en `daily config` (recorder/cli/configurar.py).
7. Terminal: consola.py toma los colores de la misma paleta; «claro» usa la variante clara, «cristal» equivale a oscuro. El modo ASCII queda igual.

Aceptación
- Prueba de contraste y prueba de carga de configuraciones antiguas.
- Capturas de cada tema entregado a 100 % y 125 % en docs/capturas-ui/.
- pytest y selftest pasan; tests/test_main_window.py y tests/test_dialogs.py sin cambios de comportamiento.

Fuera de alcance: animaciones, tooltips, rediseño del menú, métricas (otro paso trabaja en paralelo en recorder/session.py y recorder/cli/live.py: no los toques).
```

---

### Paso 3. Textos de ayuda y tooltips

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams (audio WASAPI loopback + micrófono; faster-whisper en CPU o whisper.cpp con Vulkan en GPU) y escribe una nota Markdown con capturas. Dos interfaces sobre el mismo núcleo (recorder/session.py): la ventana Tkinter (recorder/ui/) y la terminal con rich (recorder/cli/, comando `daily`). Los colores salen de una paleta por temas (recorder/paleta.py o el módulo de paleta que exista; búscalo con codegraph) con tokens tooltip_fondo y tooltip_texto, y config.json tiene «animations» (completas | reducidas | ninguna). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas.
5. Código, comentarios y textos en español. Cambios mínimos y localizados.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.

Tarea: que alguien que abre Recorder por primera vez entienda cada control sin leer el README.

Qué hacer
1. Inventario: recorre todos los controles de recorder/ui/main_window.py y recorder/ui/dialogs/*.py (botones, casillas, listas, campos, medidores, cabecera) y las opciones y pantallas de recorder/cli/ (menu.py, configurar.py, calibrar.py, live.py).
2. Un único módulo de textos sin tkinter ni rich (por ejemplo recorder/ayuda.py), con secciones «Ventana», «Terminal», «Común» y «Glosario»: clave -> título corto + explicación.
   Reglas de redacción: tuteo, lenguaje llano, 1-2 frases (máximo 180 caracteres); di qué hace, cuándo conviene tocarlo y qué pasa al cambiarlo. Explica o evita la jerga (haz de búsqueda/beam, VAD, alucinaciones, Vulkan, flash attention, loopback, int8, hilos, cola). Si un control puede estar desactivado, el texto dice por qué. Los medidores y símbolos (🔊 🎤 ⛔ 🔇 ☕, cola, atraso) explican qué significan y qué hacer.
3. Tooltip para Tk (componente pequeño propio): aparece tras ~450 ms de hover o al recibir el foco con teclado; fade-in breve con alpha que respeta «animations»; se oculta al salir, al hacer clic o con Esc; texto ajustado a ~320 px; nunca se sale del área útil del monitor (work_area); colores tooltip_fondo / tooltip_texto; muestra el atajo de teclado si el control lo tiene.
4. Conecta los tooltips a todo el inventario de la ventana y sus diálogos.
5. Terminal: una función que devuelva la línea de ayuda de una opción (la usará el menú interactivo de otro paso); úsala ya en el menú actual de recorder/cli/menu.py si encaja sin romper tests/test_cli_menu.py (o ajusta esas pruebas al texto nuevo, explicándolo).
6. Relectura en frío: lee cada texto como alguien sin contexto y reescribe lo que exija conocer el código.

Aceptación
- Prueba: toda clave usada por la ventana o la terminal existe en el módulo de textos y ningún texto pasa del largo máximo.
- Tooltips legibles en todos los temas (captura de uno por tema en docs/capturas-ui/).
- pytest y selftest pasan.

Fuera de alcance: rediseñar controles o el menú.
```

---

### Paso 4. Ventana: menú, responsive, animaciones y panel de rendimiento

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams y escribe una nota Markdown con capturas. La ventana es Tkinter (recorder/ui/main_window.py y recorder/ui/dialogs/), sobre el núcleo recorder/session.py, con sondeo cada 200 ms. Ya existen: paleta por temas con aplicación en caliente (búscala con codegraph: módulo de paleta y recorder/ui/theme.py), campo «animations» en config (completas | reducidas | ninguna), textos de ayuda y tooltips (recorder/ayuda.py o equivalente) y métricas de rendimiento con «motor efectivo» en el snapshot de la sesión (recorder/metricas.py o equivalente). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1. Equipo: i7-1255U, sin NVIDIA.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas.
5. Código, comentarios y textos en español. No añadas campos a config.json en este paso. Textos de ayuda nuevos solo en la sección «Ventana» del módulo de textos.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. No toques recorder/cli/ (otro paso trabaja ahí en paralelo).

Tarea: una ventana principal más clara, que se adapte al tamaño, con detalles de movimiento profesionales y un panel de rendimiento.

Qué hacer
1. Menú y navegación: hoy la cabecera mezcla estado, medidores y botones. Propón y aplica una estructura clara: acciones principales siempre visibles (Pausar/Reanudar, Capturar, Abrir nota) y el resto en un menú «Más» o barra lateral (Opciones, Calibrar, Reagrupar nota, Rendimiento, Tema, Ayuda; deja el hueco para «Ver introducción», que llega en otro paso). Atajos de teclado (por ejemplo Ctrl+P pausa, Ctrl+, opciones, F1 ayuda, Ctrl+Shift+T tema) mostrados en los tooltips. Anillo de foco visible y orden de Tab lógico.
2. Responsive: grid con pesos y tamaños mínimos; puntos de corte por ancho: amplio (>= 1000 px a 100 %: icono y texto), compacto (700-1000: solo icono con tooltip), estrecho (< 700: cabecera en dos filas). El estado largo se recorta con elipsis y nunca empuja los botones fuera. Comprueba a 100, 125 y 150 % de escala y en 1366×768.
3. Animaciones con un helper pequeño basado en after (máximo ~60 fps, ease-out por defecto, cancelable, sin animaciones acumuladas sobre el mismo widget) que respete «animations» (reducidas = solo fundidos cortos; ninguna = cambios instantáneos):
   - fade-in de la ventana y de los diálogos (~180 ms) y fade-out al cerrarlos;
   - transición de color en hover y pulsación de botones (~120 ms);
   - fundido cruzado al cambiar de tema;
   - resaltado de la última línea transcrita que se desvanece (~1,5 s);
   - pulso suave del indicador de grabación (lento, sin parpadeo);
   - toasts para confirmaciones que no requieren decisión, en lugar de diálogos modales.
4. Panel de rendimiento plegable con los datos del snapshot: motor efectivo, velocidad (x tiempo real), CPU, GPU, RAM, cola y atraso, con sparklines en Canvas de los últimos ~2 min. Solo se redibuja si está visible. Cada dato con tooltip.
5. Coste: grabando con la ventana visible, animaciones y panel no deben subir la CPU del proceso más de 1-2 puntos; nada bloquea los hilos de audio ni de transcripción.

Aceptación
- Pruebas de la lógica pura: selección de punto de corte por ancho, interpolación de color y easing, cancelación de animaciones, «ninguna» = instantáneo.
- tests/test_main_window.py y tests/test_dialogs.py pasan (ajústalos solo si cambia la estructura, explicando por qué).
- Capturas en docs/capturas-ui/ de cada tema en ancho amplio y compacto.
- CPU del proceso grabando antes y después (mismo escenario), anotada en el informe.

Fuera de alcance: terminal, introducción, asistente de ajuste de rendimiento.
```

---

### Paso 5. Terminal interactiva

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). Ya existen: paleta por temas aplicada también a la consola (recorder/cli/consola.py), textos de ayuda por opción (recorder/ayuda.py o equivalente, sección «Terminal») y métricas con «motor efectivo» en el snapshot de la sesión (recorder/metricas.py o equivalente). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas (nada de Textual ni curses de terceros): rich y la biblioteca estándar.
5. Código, comentarios y textos en español. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» del módulo de textos.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. No toques recorder/ui/ (otro paso trabaja ahí en paralelo).

Tarea: una terminal con pantallas navegables por teclado, vivas (se actualizan) y con «botones», rápida de usar en Windows y Linux.

Hechos ya conocidos
- `daily menu` (recorder/cli/menu.py) es un menú numerado con input(); tests/test_cli_menu.py lo prueba con la entrada inyectada.
- La pantalla en vivo (recorder/cli/live.py) ya lee teclas sin bloquear con msvcrt (leer_tecla) y pinta con rich.Live: reutiliza ese patrón.
- La captura de audio es solo Windows (WASAPI): en Linux no se puede grabar.

Qué hacer
1. Lector de teclas multiplataforma (por ejemplo recorder/cli/teclas.py): Windows con msvcrt (flechas como prefijo \xe0 o \x00 + código), Linux/macOS con termios + tty + select (ESC [ A/B/C/D, Esc suelto con espera corta). Normaliza a: arriba, abajo, izquierda, derecha, enter, esc, tab, retroceso o el carácter. Restaura siempre la terminal (try/finally, también con Ctrl+C). Que live.py use este lector.
2. `daily menu` interactivo: ↑/↓ (y j/k) mueve, Enter abre, Esc o q sale, los números siguen siendo atajos. La opción seleccionada resaltada con el acento de la paleta y su línea de ayuda debajo. Pie con teclas como botones: [Enter] Abrir · [Esc] Salir · [?] Ayuda · [t] Tema. Cabecera viva refrescada cada ~1 s (nota de hoy, calidad, motor efectivo, equipo) sin parpadeo: refresca solo si algo cambió o en el tic.
3. Pantallas navegables, Esc vuelve a la anterior:
   - Inicio (el menú).
   - Opciones: lista de ajustes con su valor; ←/→ cambia valores de lista, Enter edita texto; reutiliza la lógica de recorder/cli/configurar.py y guarda igual que hoy.
   - Rendimiento: métricas del snapshot con barras y tendencia (si no hay sesión grabando, dilo y muestra el motor que se usaría).
   - Ayuda: atajos y glosario del módulo de textos.
4. Si stdin no es una TTY (tuberías, pruebas), conserva el menú numerado actual: las pruebas existentes siguen pasando.
5. Modo ASCII (conhost) y anchos estrechos (desde 60 columnas) funcionan. Fuera de Windows, «Grabar» y «Abrir la ventana» aparecen desactivados con su motivo en la línea de ayuda.
6. Detalles visuales posibles en terminal: cambio de pantalla limpio (sin restos), selección que cambia de color al moverse, spinner mientras algo carga, colores de la paleta activa.

Aceptación
- Pruebas de decodificación de teclas (secuencias de Windows y POSIX), de navegación con secuencias guionizadas y de restauración de la terminal tras una excepción.
- tests/test_cli_*.py pasan.
- Probado a mano en Windows Terminal y en conhost (ASCII). Si hay WSL disponible, prueba el menú en Linux y anótalo; si no, dilo.

Fuera de alcance: grabar en Linux (necesita otro backend de audio).
```

---

### Paso 6. Rendimiento II: ajuste por hardware y GPU integrada

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams (faster-whisper int8 en CPU, CUDA si hay NVIDIA, o whisper.cpp con Vulkan en GPU como proceso aparte) y escribe una nota Markdown. Interfaces: ventana Tkinter (recorder/ui/) y terminal con rich (recorder/cli/), ambas con panel/pantalla de rendimiento alimentados por las métricas y el «motor efectivo» del snapshot de la sesión (recorder/metricas.py o equivalente). Textos de ayuda en recorder/ayuda.py o equivalente. Equipo de desarrollo: i7-1255U (2 núcleos P con HT + 8 E), Iris Xe integrada, sin NVIDIA. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1. Lee docs/rendimiento.md, docs/gpu-amd-vulkan.md y docs/recomendacion-hardware.md antes de planear.

Reglas de trabajo
1. Trabaja por pasos. Primero planea: explora con codegraph y escribe un plan breve y numerado (archivos, cambios, riesgos, cómo verificarás). Después ejecuta un paso cada vez, comprobándolo antes de pasar al siguiente y diciendo en qué paso vas. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y, solo al final, propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas.
5. Sin valores fijos en el código (hardcode): colores desde la paleta (recorder/paleta.py), textos visibles desde recorder/ayuda.py, tiempos, tamaños y umbrales en constantes con nombre, y rutas desde la configuración o recorder/rutas.py; nunca rutas, dispositivos ni datos de este equipo o del usuario. Código, comentarios y textos en español. Ningún cambio silencioso de configuración: todo cambio lo confirma el usuario.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Antes de reproducir audio de prueba por los altavoces, comprueba que no suena nada más ni hay una llamada en curso. No instales software del sistema (Visual Studio, CMake, Vulkan SDK).

Tarea: que cada usuario ajuste el rendimiento a su hardware con datos, y responder si la gráfica integrada se aprovecha y si conviene.

Hechos ya conocidos
- tools/medir_rendimiento.py mide velocidad y WER con una muestra sintética, pero tarda ~15 min, exige el equipo en reposo y no va dentro del ejecutable.
- `daily recomendar` (recorder/cli/recomendar.py, recorder/config/schema.py) recomienda presets por hardware y alimentación.
- En automático nunca se usa la GPU integrada (choose_vulkan_device); whispercpp_device >= 0 la fuerza y limita el modelo a large-v3-turbo. En este i7-1255U nunca se midió whisper.cpp + Vulkan en la Iris Xe frente a la CPU.

Qué hacer
1. Medir antes de programar: con config.json actual (sin modificarlo), ¿está instalado whisper.cpp (whispercpp_dir con bin\whisper-server.exe)? Si lo está, mide CPU (4/6/8/10 hilos) frente a Vulkan en la integrada con tools/medir_rendimiento.py sobre una muestra corta. Si no lo está, no lo instales: indica en el informe los pasos (tools/instalar_whispercpp.ps1). Comprueba que el equipo esté en reposo como hace la herramienta; si no lo está, dilo y no saques conclusiones. Anota los resultados en docs/rendimiento.md.
2. «Medir mi equipo» dentro de la app (ventana y terminal): prueba corta (2-3 min máximo, barra de progreso, cancelable) con la lógica de medición movida a recorder/ para que vaya en el ejecutable (tools/medir_rendimiento.py la reutiliza). Prueba solo los candidatos con sentido en ese hardware: CPU con varios hilos, GPU dedicada y la integrada solo si el usuario la permite. Muestra una tabla: velocidad (x tiempo real), CPU usada y si aguanta dos fuentes a la vez (>= 2,0x). Botón «Aplicar el mejor» que escribe solo las claves afectadas, tras confirmación. En la terminal es una pantalla más del menú (paquete recorder/cli/pantallas/), con la vista «Medir mi equipo» de docs/terminal-especificacion.md si existe, nunca preguntas en el historial; pruébala en la consola de Windows PowerShell 5.1 (conhost), que es donde se usa a diario.
3. Ajustes manuales con efecto visible en el panel de rendimiento: motor y dispositivo; hilos (con aviso de núcleos P/E en CPU híbridas); «Permitir GPU integrada» (desactivado por defecto; su texto de ayuda explica que comparte RAM y GPU con Teams); prioridad del proceso (normal por defecto, «por debajo de lo normal» para no molestar a Teams, nunca alta ni tiempo real). Si un cambio requiere recargar el modelo, dilo y aplícalo en la siguiente sesión, o recargando sin perder la cola si el worker lo permite con seguridad. Los campos nuevos de config.json cargan bien en configuraciones antiguas.
4. Coherencia: `recomendar` y el asistente usan los mismos datos; la última medición (fecha y resultados) se guarda y la recomendación la tiene en cuenta.

Aceptación
- Pruebas con motores falsos: elección del mejor candidato, cancelación, escritura solo de las claves afectadas, configuraciones antiguas.
- pytest y selftest pasan.
- El informe responde con datos: ¿se aprovecha hoy la gráfica integrada en este equipo?, ¿conviene activarla?, ¿qué configuración recomiendas y por qué?
```

---

### Paso 7. Diseño de la introducción (perfil diseño)

```text
Contexto del proyecto
Recorder es una app de escritorio para Windows que transcribe en vivo las dailies de Teams en el propio equipo (sin nube) y deja una nota Markdown ordenada con capturas de pantalla. Se distribuye como ejecutable con instalador (Recorder.exe ventana, daily.exe terminal). La interfaz es Tkinter con temas claro, oscuro y sistema; la paleta está en el módulo de paleta del repositorio (búscalo con las herramientas codegraph_*; si el índice no responde, `codegraph init -i`). El icono actual lo genera packaging/generar_icono.py (recorder/assets/recorder.ico): la identidad visual parte de ahí. Tipografías disponibles: Segoe UI Variable / Segoe UI. Blender está conectado por MCP para modelar y renderizar. Usa el flujo /design para la propuesta visual si está disponible; si no, entrega el storyboard como documento con imágenes.

Reglas de trabajo
1. Trabaja por pasos. Primero planea (propuesta de concepto y storyboard en texto); después produce los entregables uno a uno, revisando cada uno antes del siguiente y diciendo en qué paso vas.
2. No hagas commits ni push. Solo al final, propón un mensaje de commit en español («Agrega…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en los entregables, nombres de archivo ni el commit propuesto.
4. En Blender: inspecciona la escena antes de tocarla y no borres objetos existentes sin confirmar; trabaja en una colección o archivo propio.
5. No escribas código de la aplicación. En la especificación, cada color por su token de la paleta y cada duración con nombre: nada de valores sueltos que el código tenga que copiar a mano.
6. Termina con: entregables y rutas, duración total, peso total de assets, miniaturas de cada escena y preguntas abiertas.

Tarea: diseñar una presentación de la app sencilla, dinámica, corta (6-8 s) y que se pueda saltar desde el primer fotograma, para la primera vez que se abre el ejecutable.

Restricción técnica (importante): se reproducirá en Tkinter. Solo es posible: secuencias de fotogramas PNG, texto, formas de Canvas, fundidos de color y transparencia de la ventana. Sin vídeo ni códecs. Todo lo diseñado debe poder reproducirse así.

Entregables
1. Storyboard de 4-5 escenas con tiempos. Propuesta de partida (mejórala): revelado del logotipo -> «Graba tu daily» (ondas de audio que se convierten en texto) -> «Transcribe en tu equipo, sin nube» -> «Notas en Markdown con capturas» -> «Comenzar». Para cada escena: duración, qué se mueve, curva de aceleración (ease-out, ease-in-out), transición a la siguiente (fundido cruzado, escalonado) y texto exacto.
2. Especificación de movimiento: duraciones, easing, fundidos, escalonado, y la versión «movimiento reducido» (solo fundidos).
3. Logotipo 3D animado renderizado en Blender como secuencia PNG (24-30 fps, 480-640 px, fondo transparente o el del tema), más un fotograma estático de reserva. Variantes para tema claro y oscuro si el contraste lo pide. Presupuesto total de assets: 3 MB como máximo.
4. Versión de terminal: logotipo ANSI de 1 s como máximo en tres juegos de símbolos: completo (Windows Terminal), consola (la consola clásica de Windows PowerShell y cmd: solo los caracteres verificados en docs/plan-pulido-terminal.md §1, sin emoji ni ▶) y ASCII puro. Que se lea sobre fondo negro y sobre el azul #012456 de PowerShell.
5. Accesibilidad: nada que destelle más de 3 veces por segundo, contraste AA en los textos, botón «Saltar» visible siempre; Esc, Enter, Espacio y clic saltan.

Dónde
- Especificación y storyboard: docs/intro/ (markdown + imágenes ligeras).
- Fotogramas finales: recorder/assets/intro/.
- Archivo .blend: fuera del repositorio si pesa más de 5 MB (anota la ruta en la especificación).
```

---

### Paso 8. Introducción en la app y empaquetado

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams. Ventana Tkinter (recorder/ui/) y terminal con rich (recorder/cli/), sobre el núcleo recorder/session.py. Se empaqueta con PyInstaller (packaging/recorder.spec, packaging/build.ps1) e Inno Setup (packaging/recorder.iss); con Recorder instalado la configuración vive en %APPDATA%\Recorder\config.json. Ya existen: paleta por temas, campo «animations» (completas | reducidas | ninguna), helper de animaciones y menú «Más» de la ventana, y el diseño de la introducción: especificación en docs/intro/ y fotogramas en recorder/assets/intro/. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Trabaja por pasos. Primero planea: lee docs/intro/, explora con codegraph y escribe un plan breve y numerado (archivos, cambios, riesgos, cómo verificarás). Después ejecuta un paso cada vez, comprobándolo antes de pasar al siguiente y diciendo en qué paso vas. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y, solo al final, propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas (Pillow ya está si hace falta).
5. Sin valores fijos en el código (hardcode): colores desde la paleta (recorder/paleta.py), textos visibles desde recorder/ayuda.py, tiempos, tamaños y umbrales en constantes con nombre, y rutas desde la configuración o recorder/rutas.py; nunca rutas, dispositivos ni datos de este equipo o del usuario. Código, comentarios y textos en español.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Si cambias el config.json instalado para probar, guarda una copia antes y restáurala al terminar.

Tarea: reproducir la introducción diseñada en la app y en el ejecutable.

Qué hacer
1. recorder/ui/intro.py: ventana sin bordes centrada (fit_window / work_area), reproduce los fotogramas con after al ritmo de la especificación, superpone los textos con sus fundidos, botón «Saltar» y Esc / Enter / Espacio / clic. Respeta «animations»: reducidas = solo fundidos; ninguna = sin intro animada. Al terminar o saltar: fade-out y se abre la ventana principal.
2. Cuándo sale: la primera vez (campo «intro_seen» en config.json, compatible con configuraciones antiguas) y bajo demanda desde «Ver introducción» en el menú «Más». `--sin-intro` la omite.
3. No debe retrasar la grabación: si la carga del modelo puede empezar mientras se ve la intro sin romper la regla de PortAudio (los streams se abren en el hilo principal con una sola instancia de PyAudio), aprovéchalo; si no, la intro va antes y se documenta.
4. Terminal: el logotipo de 1 s como máximo en el primer `daily`, saltable con cualquier tecla, con el juego de símbolos activo (completo / consola / ASCII, docs/plan-pulido-terminal.md §3) y omitible con `--sin-intro`. Pruébalo en la consola de Windows PowerShell 5.1 con la función `daily` del perfil: al terminar, el prompt queda limpio.
5. Si faltan los fotogramas (ejecución desde el código sin ellos), la intro se omite sin error.
6. Empaquetado: añade recorder/assets/intro/ a packaging/recorder.spec, construye con packaging\build.ps1, mide el tamaño del instalador antes y después, e instala y prueba la primera ejecución de Recorder.exe y daily.exe.

Aceptación
- Pruebas: salto por cada tecla y clic, «intro_seen» persistido, assets ausentes, `--sin-intro`, «animations: ninguna».
- tests/test_instalado.py pasa si aplica.
- Informe con el tamaño del instalador antes y después y la duración real medida de la intro.
```

---

### Paso 9. Verificación integrada

```text
Contexto del proyecto
Recorder es una app de escritorio en Python 3.14 para Windows que transcribe en vivo las dailies de Teams. Se han aplicado mejoras en varios pasos: métricas y motor efectivo, temas claro/oscuro/sistema, textos de ayuda y tooltips, ventana con menú nuevo, responsive, animaciones y panel de rendimiento, terminal interactiva, asistente de ajuste de rendimiento e introducción animada (detalle en docs/plan-mejoras-experiencia-y-rendimiento.md). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` y `python recorder.py --selftest`. Empaquetado: packaging\build.ps1. Shell: PowerShell 5.1.

Reglas de trabajo
1. Trabaja por pasos. Primero planea el recorrido de verificación, numerado; después ejecútalo un paso cada vez, anotando el resultado de cada uno antes del siguiente.
2. No hagas commits ni push. Corrige solo lo trivial (y dilo); lo demás se anota. Si corriges algo, propón al final un mensaje de commit.
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, documentación ni commits propuestos.
4. Antes de reproducir audio de prueba por los altavoces, comprueba que no suena nada más ni hay una llamada en curso. Si modificas config.json para probar, guarda una copia y restáurala.
5. Informa los fallos con su salida real; no los suavices.

Tarea: comprobar que todo junto funciona, se ve bien y no cuesta rendimiento.

Qué hacer
1. `python -m pytest`, `python recorder.py --selftest`, build del ejecutable y del instalador.
2. Recorrido manual con capturas en docs/capturas-ui/ (nombre: tema_escala_ancho.png): ventana en cada tema, a 100/125/150 % y en 1366×768; terminal en la consola de Windows PowerShell 5.1 (la del día a día: conhost con color real, fondo negro y azul #012456), en cmd, con `--ascii`, y en Windows Terminal o PowerShell 7 si están instalados; introducción en primera ejecución del instalado (`Recorder.exe` y `daily.exe`).
3. Contraste: la prueba automática de temas y una revisión a ojo de hover, foco y desactivado.
4. Coste: sesión de unos 10 minutos grabando en CPU con audio de prueba: CPU del proceso y velocidad con panel y animaciones activados y con «animations: ninguna» y panel plegado. Anota la diferencia.
5. Busca en el diff completo respecto a la rama principal menciones a asistentes, agentes o herramientas de IA (código, docs, textos de la app), y valores fijos (hardcode): colores fuera de la paleta, textos visibles fuera de recorder/ayuda.py, rutas o datos de este equipo.
6. Informe en docs/verificacion-mejoras-ux.md: qué pasó, qué falló (con salida), capturas, pendientes, y la lista de commits sugeridos en orden si los pasos aún no se han confirmado.
```

---

## 5. Fuera de este plan (para más adelante)

* **Grabar en Linux**: backend de captura con PulseAudio/PipeWire (monitor de la salida + micrófono) detrás de la misma interfaz que `recorder/audio/`.
* **Cambio de toolkit** (Qt o interfaz web) solo si la prueba de cristal del paso 2 o las animaciones del paso 4 se quedan cortas en Tk.
* **Fusión de fragmentos pendientes en el worker** (`docs/rendimiento.md` §3.2): la palanca estructural de velocidad más grande que queda; encaja después del paso 6, cuando haya mediciones.
