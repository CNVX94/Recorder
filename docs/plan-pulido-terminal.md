# Plan de pulido: pantallas de terminal

Noviembre de 2026. Sigue al paso 5 de `docs/plan-mejoras-experiencia-y-rendimiento.md` (terminal
interactiva, commit «Agrega menú navegable por teclado en la terminal»). Objetivo: que **todas** las
pantallas de `daily` sean limpias, controladas y con el mismo estilo que el menú nuevo. Plan por
pasos con un prompt autocontenido para cada uno: se copia tal cual en una sesión nueva abierta en
este repositorio.

**Revisado el 24-nov-2026 (segunda verificación)**: se comprobó de nuevo entrando desde el menú a
cada opción, en cmd y en **Windows PowerShell 5.1** (la función `daily` del perfil, que es como se
usa a diario). Cambios respecto a la primera versión: la grabación pasa a pantalla completa
(decisión 1), Rendimiento entra en el rediseño, la consola de PowerShell tiene su propio paso
(2b: color real y símbolos seguros) y se añaden las vistas que faltaban (arranque y fin de la
grabación, vuelta al menú, «Medir mi equipo», ventana abierta). Hallazgos nuevos: 21-28.

---

## 1. Punto de partida (verificado el 24-nov-2026)

### Cómo se tomó la evidencia

* **Consola clásica real (conhost)**: `tools/capturar_terminal.py` abre cada comando en una consola
  nueva con un config.json y unas notas sintéticos (no toca los del usuario), teclea con
  `WriteConsoleInputW` y guarda en cada paso el búfer de texto y la ventana en PNG. Conhost se
  detecta como consola antigua: ASCII y 16 colores. Resultado en `docs/capturas-terminal/<escenario>/`.
* **Terminal moderna (truecolor, tema oscuro)**: `tools/capturar_terminal_svg.py` ejecuta los mismos
  flujos dentro del proceso con una consola que graba. Resultado en `docs/capturas-terminal/svg/`
  (`galeria.html` las reúne; `galeria.png` es la vista general).
* **Revisión de diseño** independiente sobre esa evidencia y el código, contrastada después con el
  código (§2 recoge solo lo confirmado).

Límites: Windows Terminal no está instalado en el equipo de desarrollo (se usó un terminal ConPTY
equivalente para el menú); WSL no tiene ninguna distribución Linux; el Ctrl+C inyectado como tecla
no equivale al del teclado, así que Ctrl+C en una pregunta de modo línea queda **sin verificar**.
Las capturas de conhost muestran nombres reales de dispositivos de audio y del equipo.

**Segunda verificación (24-nov-2026)**: con el mismo método y datos sintéticos, entrando desde
`daily menu` a cada opción: `docs/capturas-terminal/desde-el-menu/` (calibrar, reagrupar,
recomendar, rendimiento, grabar) y, lanzado con la función `daily` del perfil de Windows PowerShell
5.1, `docs/capturas-terminal/powershell/menu/`. Las capturas de la grabación con audio real se
descartaron (transcribieron lo que sonaba en el equipo); queda solo `grabar/02_abre.png`.

### La consola de PowerShell, que es la del día a día

| Hecho | Detalle |
| :--- | :--- |
| Cómo se lanza | `function daily { python "...\recorder.py" $args }` en `Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`. Windows PowerShell 5.1; **no hay Windows Terminal ni PowerShell 7 (`pwsh`)** en el equipo: siempre es conhost. |
| Qué detecta rich hoy | Consola antigua (`legacy_windows=True`, 16 colores): todo sale en **ASCII** y la paleta se reduce a 16 colores. Igual que en cmd (`powershell/menu/01_inicio.png`). |
| Color real | Activando `ENABLE_VIRTUAL_TERMINAL_PROCESSING` (`SetConsoleMode`, 0x0004) **antes de crear la primera `Console`** (rich cachea la detección), la misma consola pasa a `truecolor` y la paleta se ve tal cual (`powershell/color-real-vt.png`). Verificado. |
| Símbolos en conhost (Consolas) | Se ven bien: `─ █ ░ ‹ › ‥ ● · « »`. Salen como cuadro: `▶` y `▁▂▃▅▆▇` (solo `▄ █` existen). Se pintan encima del espacio siguiente: `✔ ⚠` y todos los emoji (monocromos). |
| Fondo | Una consola nueva es negra; el acceso directo «Windows PowerShell» del menú Inicio usa **fondo azul `#012456`** con texto gris. La paleta debe leerse en los dos (o pintar su propio fondo en pantalla completa). |
| Variable `NO_COLOR` | El entorno de las herramientas automáticas la trae puesta (`NO_COLOR=1`); la del usuario no. Las capturas y las pruebas de color deben quitarla. |

### Estado por pantalla

| Pantalla | Cómo es hoy | Evidencia | Consecuencia para el plan |
| :--- | :--- | :--- | :--- |
| Menú (`daily menu`, `cli/pantallas.py`) | Pantallas navegables: cabecera viva, ruta, lista con ▶, ayuda de lo elegido, pie de botones. | `menu/`, `svg/menu-*.svg` | Es la referencia. Tiene tres fallos propios (§2). |
| Calibrar (`cli/calibrar.py`) | Menú numerado de 8 opciones que se reimprime entero tras cada acción; preguntas en línea; prueba de frases con `frase>`. | `calibrar/`, `calibrar-60/`, `svg/calibrar*.svg` | Pasar a pantalla con lista de ajustes y prueba en vivo. |
| Reagrupar nota (`cli/sintesis.py`) | Elegir nota por número, 6 preguntas seguidas a ciegas, vista previa de 10 líneas al final y confirmar. | `sintesis/`, `sintesis-60/`, `svg/sintesis.svg` | Pasar a pantalla con interruptores y vista previa que cambia al momento. |
| Recomendación (`cli/recomendar.py`) | Tres líneas de texto plano sin color; el motivo es un párrafo de 6 líneas; no se puede aplicar desde ahí. | `recomendar/`, `svg/recomendar.svg` | Pantalla tipo tarjeta «ahora / recomendado» con «Aplicar». |
| Asistente `daily config` (`cli/configurar.py`) | Secciones por número y preguntas en línea; tras confirmar el guardado de una sección, sale. | `config/`, `config-ver/`, `svg/config.svg` | En terminal real, `daily config` abre la pantalla Opciones; el asistente queda para entrada redirigida. |
| Grabación (`daily`, `cli/live.py`) | `rich.Live` sin pantalla alternativa: cabecera y frases van al historial de la terminal, mezcladas con lo anterior; la línea de fuentes se parte a mitad de nombre. El panel [o] solo acepta números. Al terminar, si se abrió desde el menú, **no vuelve al menú**: deja el prompt de PowerShell. | `grabar/`, `desde-el-menu/grabar/`, `svg/grabar.svg` | **Pantalla completa** (decisión 1): transcripción desplazable, estado y pie fijos; al salir, un resumen corto. |
| Rendimiento (`cli/pantallas.py`) | Sí abre dentro de la pantalla, pero pobre: dos barras (CPU y GPU del equipo), «midiendo…» los primeros segundos, tendencia «__» y dos tercios de la pantalla vacíos. Durante la grabación las cifras solo están en una línea del pie y no hay vista de rendimiento. | `desde-el-menu/rendimiento/` | Rediseño (paso 6b): equipo, margen antes de grabar y, durante la grabación, una vista en vivo. |
| Paso del menú a un comando | Sale de la pantalla alternativa al historial, imprime la ayuda del menú, el comando repite su propia intro y su menú numerado (Calibrar lo reimprime entero tras cada acción) y vuelve «pulsando una tecla». Confirmado para Calibrar, Reagrupar y Recomendación, en cmd y en PowerShell. | `menu/02_*`, `menu/03_*`, `desde-el-menu/*`, `powershell/menu/` | Desaparece cuando cada comando tenga su pantalla. |
| Abrir la ventana | Termina el menú; la terminal no dice nada mientras la ventana está abierta (visto en el código, sin captura). | — | Estado «La ventana está abierta» y vuelta al menú al cerrarla. |

### Decisiones tomadas por defecto (cámbialas antes de lanzar el paso que afecta)

1. **La grabación pasa a pantalla completa** (cambiado el 24-nov-2026: mezclada con el historial estorba y no se entiende). La nota en disco es el registro completo; al salir se imprime un resumen de pocas líneas. El modo de historial actual se conserva solo con `daily --historial` (para quien quiera copiar de la terminal) y con la salida redirigida.
2. **El modo línea no se toca**: con la entrada redirigida (scripts, pruebas) cada comando funciona como hoy. Es el contrato de `tests/test_cli_*.py`.
3. **←/→ nunca aplica un dispositivo de audio en vivo**: reabriría el audio a cada paso en plena reunión. Se elige con Enter.
4. **Sin ratón ni ventanas modales**; marcos y símbolos solo con caracteres verificados en conhost (§1, tabla de PowerShell).
5. **Una pantalla por módulo** (paso 3) para que Calibrar, Reagrupar, Recomendación, Rendimiento y grabación puedan hacerse en paralelo.
6. **Color real en la consola de PowerShell y cmd** (paso 2b): se activa el modo VT al arrancar. Color y símbolos se deciden por separado: el color por lo que admite la consola, los símbolos por un juego «completo» (Windows Terminal, VS Code), «consola» (conhost: sin emoji ni `▶`) o «ASCII» (consola sin VT, `--ascii`).

---

## 2. Hallazgos confirmados

Gravedad: **A** alta (estorba o puede hacer perder algo), **M** media, **B** baja.

| # | Pantalla | Hallazgo | Grav. | Dónde |
| :-: | :--- | :--- | :-: | :--- |
| 1 | Grabación | Con audio pendiente, al salir pregunta «[e] esperar · [s] salir perdiéndolos · [c] cancelar»: **Esc no cancela** y `c`, que en el pie es «captura», pasa a ser «cancelar». | A | `live.py:80`, `_tecla` |
| 2 | Calibrar | Vocabulario y frases a ignorar no se editan: Enter conserva o se reescribe entero. La ventana sí permite editarlos. | A | `preguntas.py:92-99`, `calibrar.py:115,156` |
| 3 | Calibrar | «8 Salir sin guardar» descarta los cambios sin preguntar, pegado a «7 Guardar y salir». | A | `calibrar.py:135-139` |
| 4 | Calibrar | El menú de 8 líneas se reimprime tras cada acción; a 60 columnas las opciones largas vuelven a la columna 0 y ocupan 13 líneas. | A | `svg/calibrar-60.txt`, `calibrar-60/03_*` |
| 5 | Reagrupar | Seis preguntas sí/no a ciegas y la vista previa solo al final; si no gusta, se empieza de cero. | A | `sintesis.py:184-202` |
| 6 | Recomendación | Párrafo largo sin acción ni comparación con lo que tienes («[medida]», «int8», «haz 5», «whispercpp_device» sin explicar). | A | `recomendar.py:45-49` |
| 7 | Asistente | En terminal real `daily config` abre el asistente viejo aunque la pantalla Opciones existe. Tras confirmar el guardado de una sección sale del asistente, y Enter en «¿Guardar?» es «sí». | A | `configurar.py:185-187,208` |
| 8 | Menú · Opciones | El aviso «hay cambios sin guardar» solo salta una vez: `avisado` no se reinicia al seguir editando. | A | `pantallas.py` (`Opciones.tecla`) |
| 9 | Menú · Opciones | Enter en un ajuste de lista pasa al siguiente valor aunque el pie dice «[Enter] Editar»; con 5 dispositivos o 20 ventanas, ←/→ es ir a ciegas. | M | `pantallas.py` (`Opciones.tecla`) |
| 10 | Menú · Opciones | Campo de texto sin cursor movible: para corregir una letra de una ruta hay que borrar hasta ella. | M | `pantallas.py` (edición) |
| 11 | Menú · Opciones | «GPU de whisper.cpp» y «Flash attention» se ven con la carpeta de whisper.cpp vacía (el asistente las oculta); «Hilos de CPU 0» no dice que es automático (4). | M | `pantallas.py` (`_componer`) |
| 12 | Calibrar | Umbrales preguntados con jerga (`no_speech_prob`, `avg_logprob`, «decodificador») y sin decir hacia dónde descarta más; los textos llanos ya existen en `ayuda.py` y no se usan. | M | `calibrar.py:62-66`, `ayuda.py` (`umbral_*`) |
| 13 | Calibrar | La prueba de frases aplica las correcciones sin decirlo («Revisa cuba…» → «ACEPTADA: Revisa QA…»). | M | `svg/calibrar-60.txt` |
| 14 | Grabación | El panel [o] solo acepta números, sin fila elegida ni línea de ayuda; su índice ocupa 4 líneas partidas a 100 columnas; no hay [?]. | M | `live.py` (`_lineas_panel`), `grabar/03_*`, `grabar/04_*` |
| 15 | Reagrupar | «No es un resumen» aparece tres veces en la misma pantalla; cifras confusas («10 líneas → 2 bloques · 24 líneas»); a 60 columnas la tabla de notas se parte. | M | `sintesis.py:116,124-127`, `sintesis-60/01_*` |
| 16 | Todas (ASCII) | Al quitar un emoji queda un espacio al principio (« Calibración…», « Salida de audio»); líneas largas sin sangría al partirse. | M | `consola.py` (`asciify`), `menu/02_*`, `grabar/04_*` |
| 17 | Asistente | La tabla de cambios usa jerga («Haz», «Precisión», «Dispositivo»). | B | `configurar.py:79-80` |
| 18 | Reagrupar (nota) | La cabecera de la copia reagrupada va sin tildes («transcripcion», «aqui», «leyendola»): llega a la nota del usuario. | B | `digest/writer.py:110-112` |
| 19 | Textos | Contradicción: la ayuda de «Descartar frases cortas» dice que casi siempre son relleno; Reagrupar avisa de que se lleva «Sí, va.». | B | `ayuda.py` (`descartar_cortas`), `sintesis.py:197` |
| 20 | Menú | Al volver de un comando vale cualquier tecla y la ayuda del menú duplica la intro del comando. | B | `pantallas.py` (`_ejecutar`) |
| 21 | Menú → comandos | Calibrar, Reagrupar y Recomendación salen de la pantalla limpia al historial de la terminal, con preguntas en línea y «[una tecla] volver al menú». Es la queja principal del usuario (sube a A lo que el hallazgo 20 dejaba en B). | A | `pantallas.py` (`Inicio.abrir` → `salir(accion)`, `_ejecutar`), `desde-el-menu/*` |
| 22 | Grabación | Va al historial mezclada con lo anterior; al terminar, si se abrió desde el menú, deja el prompt de PowerShell en vez de volver al menú. | A | `pantallas.py` (`_ejecutar`: `return grabar(...)`), `desde-el-menu/grabar/` |
| 23 | PowerShell / cmd | conhost se detecta como consola antigua: ASCII y 16 colores; la paleta y la fila elegida apenas se distinguen. Activar VT antes de la primera `Console` da color real (verificado). | A | `consola.py` (`make_console`), `powershell/menu/`, `powershell/color-real-vt.png` |
| 24 | Rendimiento | Dos barras y dos tercios de pantalla vacíos; la tendencia empieza como «__»; sin RAM ni margen en palabras. Durante la grabación no hay vista de rendimiento, solo una línea del pie. | M | `pantallas.py` (`Rendimiento`), `desde-el-menu/rendimiento/` |
| 25 | Símbolos | En conhost con color real, `▶` y `▁▂▃▅▆▇` salen como cuadros y `✔ ⚠` y los emoji pisan el espacio siguiente. Hoy no se nota (ASCII); aparecerá al activar el color. | M | `consola.py` (`ASCII`, `EMOJI_SEGURO`), `pantallas.py` (`MARCA`, `CHISPAS`) |
| 26 | Grabación | Arranque y fin sin pantalla propia: «Iniciando…», carga del modelo, vaciado de la cola y ruta final se imprimen en el historial. | M | `live.py` (`_cabecera`, `_despedida`) |
| 27 | Cabecera | La línea del equipo se corta sin «…» en ASCII («portáti»). | B | `pantallas.py` (`t`: `crop` en ASCII) |
| 28 | Abrir la ventana | El menú termina y la terminal se queda sin decir nada mientras la ventana está abierta. | B | `pantallas.py` (`_ejecutar`) |

---

## 3. Sistema común para las pantallas

**Esqueleto** (el de `Terminal.marco()`): cabecera, regla, ruta («Inicio › Calibrar»), cuerpo, línea
de ayuda de lo elegido, aviso y pie de botones. Fuera de Inicio la cabecera baja a una línea (nota,
calidad, motor). A la derecha de la ruta, «● cambios sin guardar» en `acento` cuando los haya. Si el
pie no cabe, quedan las teclas principales y «[?] Más».

**Componentes** (extraídos de `Opciones` a un módulo común):

| Componente | Aspecto | Teclas |
| :--- | :--- | :--- |
| Lista de ajustes | `▶ etiqueta   valor`; fila elegida en `elegido`, valores en `tenue`; separador `borde` antes de las acciones | ↑↓ j/k, Inicio/Fin, 1-9 |
| Campo de texto | `› texto▌`, cursor en `acento`, ventana deslizante si no cabe | ←→, Inicio/Fin, Retroceso/Supr; Enter acepta; Esc restaura |
| Interruptor | `sí` / `no` | Espacio, ←→ o Enter alternan |
| Valor numérico con paso | `‹ 0.60 ›` y su rango («descarta más ‥ menos») | ←→ ±paso; Enter para teclear |
| Lista de selección | Subpantalla con ▶ y «(actual)», recortada alrededor de lo elegido | ↑↓, 1-9, Enter elige, Esc vuelve |
| Vista previa | Panel con título, cifras y «1-12 de 24» | RePág/AvPág |
| Confirmación | El cuerpo pasa a «antes → después» | Enter confirma, Esc sigue |
| Aviso pasajero | Una línea sobre el pie en `ok` o `error`; se va con la siguiente tecla | — |
| Spinner | `Terminal.spinner()` (ya existe) | Esc cancela si se puede |
| Vacío / error | Una línea `tenue` o `error` que dice qué hacer («No hay notas todavía: se crean al grabar.») | Esc |

En ASCII: `>`, `<valor>`, `_` como cursor, barras `#`/`.`, sin espacio sobrante donde había un emoji.

**Juegos de símbolos** (paso 2b; la especificación del paso 2 fija los definitivos):

| Juego | Cuándo | Color | Símbolos |
| :--- | :--- | :--- | :--- |
| completo | Windows Terminal (`WT_SESSION`), VS Code (`TERM_PROGRAM=vscode`), terminales de Linux/macOS | el que admita (truecolor casi siempre) | todos, emoji incluidos |
| consola | conhost con VT activado: cmd y **Windows PowerShell** | truecolor | solo los verificados en Consolas (`─ █ ░ ‹ › ‥ ● · « »`); sin emoji, sin `▶`, sin `▁▂▃` |
| ASCII | consola sin VT, `--ascii`, salida redirigida | 16 colores o ninguno | los de hoy (`>`, `#`, `.`, `-`) |

**Modelo de teclas**

| Tecla | Pantallas | Grabación |
| :--- | :--- | :--- |
| ↑↓ j/k | mover | mover, solo dentro del panel [o] |
| ←→ | cambiar el valor | no cambian nada |
| Enter | abrir / editar / confirmar | elegir en el panel |
| Esc, q | un nivel atrás | cierra el panel; cancela la pregunta de salida; `q` en el pie = salir |
| ? | ayuda | leyenda de teclas |
| g | guardar | — (se aplica al elegir) |
| t | tema | — |
| 1-9 | atajo a la fila | atajo en el panel |
| Ctrl+C | salir sin guardar | salir (pregunta si hay pendiente) |

**Textos**: etiquetas cortas y la explicación en la línea de ayuda (de `ayuda.py`). Ejemplos:
«Calibración anti-alucinaciones y léxico personal» → «Calibrar»; «Umbrales del decodificador» →
«Filtros de frases dudosas»; «Anti-bucles (ratio de compresión…)» → «Filtro de repeticiones»;
«Probar frases (sandbox…)» → «Probar una frase»; «ACEPTADA / DESCARTADA» → «Se queda / Se
descarta: contiene «…» (Frases a ignorar)»; «salir perdiéndolos» → «Salir sin esperar»; «Hilos de
CPU 0» → «automático (4)». El aviso de reinicio se dice una vez, al guardar: «Guardado. Vale desde
la próxima grabación.»

---

## 4. Orden, dependencias y paralelismo

| Paso | Qué | Perfil | Depende de | Archivos principales | En paralelo con |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | Correcciones inmediatas (hallazgos 1, 3, 8, 16, 17, 18, 19) | código | — | `cli/live.py`, `cli/calibrar.py`, `cli/pantallas.py`, `cli/consola.py`, `digest/writer.py`, `ayuda.py` | **Hecho** |
| 2 | Especificación visual y de textos de **todas** las vistas | diseño | — | `docs/terminal-especificacion.md` | 2b |
| 2b | Color real y símbolos seguros en la consola de PowerShell y cmd | código | — | `cli/consola.py`, arranque (`recorder/__main__.py`, `recorder.py`), `tools/capturar_terminal.py` | 2 |
| 3 | Base común: teclas nuevas, componentes y una pantalla por módulo | código | 1, 2, 2b | `cli/teclas.py`, `cli/pantallas.py` → `cli/pantallas/` | — |
| 4 | Calibrar como pantalla | código | 3 | nuevo `cli/pantallas/calibrar.py` | 5, 6, 6b |
| 5 | Reagrupar con vista previa viva | código | 3 | nuevo `cli/pantallas/reagrupar.py` | 4, 6, 6b |
| 6 | Recomendación como pantalla, con «Aplicar» | código | 3 | nuevo `cli/pantallas/recomendacion.py` | 4, 5, 6b |
| 6b | Rendimiento rediseñado (menú y vista en vivo reutilizable) | código | 3 | nuevo `cli/pantallas/rendimiento.py` | 4, 5, 6 |
| 7 | Grabación a pantalla completa | código | 3, 6b | `cli/live.py` | 4, 5, 6 |
| 8 | Cada comando abre su pantalla; grabar y la ventana vuelven al menú | código | 4, 5, 6, 7 | `cli/app.py`, `cli/pantallas/`, `cli/configurar.py`, `cli/calibrar.py`, `cli/sintesis.py`, `cli/recomendar.py` | — |
| 9 | Verificación con evidencia antes/después, en cmd y en PowerShell | código | todos | `docs/capturas-terminal/`, `docs/verificacion-pulido-terminal.md` | — |

* Si dos pasos van en paralelo, cada uno en su propia copia de trabajo (worktree) y se integran uno tras otro.
* Los pasos 4-7 añaden textos a la sección «Terminal» de `recorder/ayuda.py`, cada uno con su prefijo (`calibrar_`, `reagrupar_`, `recomendacion_`, `rendimiento_`, `grabacion_`), para que integrar sea trivial.
* «Medir mi equipo» es del paso 6 de `docs/plan-mejoras-experiencia-y-rendimiento.md` (pendiente); aquí solo se especifica su vista (paso 2) para que ese paso la construya igual que las demás.
* Ningún paso añade campos a `config.json`.
* Cada paso termina con un mensaje de commit sugerido; el commit lo haces tú después de revisar.

---

## 5. Prompts

El bloque «Contexto del proyecto» y las «Reglas de trabajo» se repiten en cada prompt para que sea autocontenido.

### Paso 1. Correcciones inmediatas (hecho)

Aplicado el 24-nov-2026. Además de lo pedido, la cabecera YAML de la copia reagrupada (`aviso:` y
`opciones:`) también lleva ya sus tildes. Comprobado en la consola clásica real: el título de
Calibrar ya no empieza con un espacio.

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). En una terminal real `daily menu` abre pantallas navegables (recorder/cli/pantallas.py: Inicio, Opciones, Rendimiento, Ayuda) con rich.Live en pantalla alternativa, lector de teclas común (recorder/cli/teclas.py), consola y modo ASCII (recorder/cli/consola.py), paleta por tokens (recorder/paleta.py) y textos de ayuda (recorder/ayuda.py, sección «Terminal»). Calibrar, Reagrupar nota (sintesis), Recomendación y el asistente `daily config` siguen en modo línea con recorder/cli/preguntas.py; la grabación (`daily`, recorder/cli/live.py) usa rich.Live sin pantalla alternativa. Hallazgos, evidencia y plan completo: docs/plan-pulido-terminal.md y docs/capturas-terminal/. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto: rompe una prueba de color) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada redirigida se conserva el modo línea actual. No toques recorder/ui/ ni el config.json del usuario (para probar a mano, RECORDER_CONFIG apuntando a una copia).

Tarea: corregir los fallos pequeños que molestan hoy, sin rediseñar ninguna pantalla.

Qué hacer (hallazgos de docs/plan-pulido-terminal.md §2)
1. Grabación (hallazgo 1): en la pregunta de salir con audio pendiente, Esc cancela (sigue grabando) y el pie lo dice: «[e] Esperar y salir · [s] Salir sin esperar · [Esc] Seguir grabando». `c` deja de significar «cancelar» ahí. Ajusta TECLAS_CIERRE y sus textos «cierre_*» en recorder/ayuda.py.
2. Calibrar (hallazgo 3): «Salir sin guardar» con cambios pide confirmación («¿Salir y perder los cambios?», por defecto no).
3. Opciones del menú (hallazgo 8): el aviso de cambios sin guardar vuelve a saltar si, tras avisar, se sigue editando (reinicia el estado al cambiar cualquier cosa).
4. ASCII (hallazgo 16): al quitar un emoji no queda un espacio al principio de la línea ni dos espacios seguidos.
5. Tabla de cambios del asistente (hallazgo 17): etiquetas llanas para Haz, Precisión y Dispositivo.
6. Copia reagrupada (hallazgo 18): tildes en la cabecera que escribe recorder/digest/writer.py («transcripción», «aquí», «leyéndola»); revisa sus pruebas.
7. Textos (hallazgo 19): unifica la ayuda de «Descartar frases cortas» y la pregunta de Reagrupar: quitan frases de menos de 4 palabras, también respuestas como «Sí, va.».

Aceptación
- Pruebas: Esc cancela la pregunta de salida en la grabación (con el teclado guionizado de tests/test_cli_live.py); confirmación al salir de Calibrar con cambios; aviso de Opciones tras editar de nuevo; asciify sin espacios sobrantes.
- tests/test_cli_*.py, tests/test_digest*.py, pytest y selftest pasan.

Fuera de alcance: rediseñar pantallas (pasos 3-8).
```

---

### Paso 2. Especificación visual y de textos de todas las vistas (perfil diseño)

```text
Contexto del proyecto
Recorder es una app que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Tiene modo terminal con rich (comando `daily`). Hoy conviven dos estilos:
- Pantallas limpias a pantalla completa (recorder/cli/pantallas.py, rich.Live con pantalla alternativa): Inicio, Opciones, Rendimiento y Ayuda, con cabecera viva, ruta «Inicio › Opciones», lista con ▶, línea de ayuda de lo elegido y pie de botones «[Enter] Abrir · [Esc] Salir…».
- Vistas que se escriben en el historial de la terminal, mezcladas con lo anterior, pregunta a pregunta: Calibrar (filtros de frases inventadas y vocabulario, con prueba de frases), Reagrupar nota (copia ordenada por hora y tramos, no resume), Recomendación (qué calidad conviene al equipo), el asistente `daily config` y la grabación (`daily`, que imprime las frases en el historial con un pie vivo). Al terminar un comando se vuelve al menú «pulsando una tecla»; al terminar de grabar no se vuelve al menú.
El usuario lo usa a diario en Windows PowerShell 5.1 dentro de la consola clásica (conhost; no hay Windows Terminal), donde hoy todo sale en ASCII y 16 colores. Ya se verificó que activando el modo VT la misma consola muestra la paleta en color real; con la fuente Consolas se ven bien ─ █ ░ ‹ › ‥ ● · « », salen como cuadro ▶ y ▁▂▃▅▆▇, y ✔ ⚠ y los emoji pisan el espacio siguiente. El acceso directo de PowerShell usa fondo azul #012456; una consola nueva, negro.
Evidencia: docs/capturas-terminal/ (svg/galeria.png: terminal moderna; carpetas por escenario: conhost; desde-el-menu/: lo que se ve al entrar desde el menú a cada opción; powershell/: la consola del día a día, y powershell/color-real-vt.png con color real). Hallazgos (1-28), decisiones, sistema común, juegos de símbolos y orden de los pasos: docs/plan-pulido-terminal.md. Ventana de escritorio equivalente, para la coherencia: docs/capturas-ui/oscuro-100-*.png y claro-100-*.png. Paleta por tokens en recorder/paleta.py (texto, tenue, acento, mic, error, ok, borde, elegido…), con contraste AA en tema claro y oscuro. Textos de ayuda en recorder/ayuda.py (tuteo, lenguaje llano, una o dos frases de hasta 180 caracteres). Métricas disponibles para Rendimiento: recorder/metricas.py (motor efectivo, velocidad por fragmento, cola, atraso, CPU del proceso y del sistema, GPU, RAM). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* para consultar el código sin abrir archivos de más; si no responde, `codegraph init -i`.

Reglas de trabajo
1. Primero planea (inventario de vistas, orden, preguntas abiertas), después produce los entregables.
2. No hagas commits ni push. Propón un mensaje de commit en español («Agrega…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en los entregables, nombres de archivo ni el commit propuesto.
4. No escribas código de la aplicación. Usa el flujo /design para la propuesta visual; las maquetas finales van además en texto monoespaciado dentro de la especificación, para que el código las copie sin interpretar.
5. Termina con: entregables y rutas, decisiones tomadas, preguntas abiertas y qué vistas quedaron fuera y por qué.

Restricciones técnicas
- Solo lo que rich pinta en una terminal: texto, colores de la paleta, negrita, atenuado, inverso y reglas. Sin ratón ni ventanas modales. Marcos solo con caracteres verificados en conhost.
- Tres juegos de símbolos (docs/plan-pulido-terminal.md §3): completo (Windows Terminal, VS Code), consola (conhost con color real: cmd y Windows PowerShell; sin emoji ni ▶) y ASCII (consola sin VT, --ascii). El color nunca es la única señal: la fila elegida lleva marca además de color.
- Desde 60×24 hasta pantallas grandes; nada se sale ni deja restos.
- Toda vista interactiva vive en la pantalla alternativa; el historial de la terminal solo recibe, al salir, un resumen corto cuando tenga valor (fin de la grabación). Con la entrada redirigida sigue el modo línea actual: no hay que diseñarlo.

Tarea: fijar cómo se ve, cómo se maneja y qué dice cada vista de la terminal, para que los pasos de código solo tengan que construirlo, y que el conjunto se sienta una sola app limpia e intuitiva.

Inventario cerrado (amplíalo si encuentras otra vista que hoy escriba en el historial o deje al usuario sin saber qué pasa)
1. Inicio (referencia actual; revisa la cabecera de tres líneas y el aprovechamiento del espacio).
2. Opciones: lista de ajustes, lista de selección (dispositivos, pantallas, ventanas), campo de texto con cursor, confirmación «antes → después».
3. Calibrar, con «Probar una frase» y su veredicto en vivo.
4. Reagrupar nota: elegir nota → opciones con vista previa viva → crear la copia.
5. Recomendación: tarjeta «Ahora / Recomendado» con «Aplicar».
6. Rendimiento sin grabación (equipo, motor previsto, margen antes de grabar, tendencias) y Rendimiento durante la grabación (velocidad frente al tiempo real en palabras, cola, atraso, CPU, GPU, RAM, motor efectivo y caída a CPU si la hubo). Sin dos tercios de pantalla vacíos.
7. Medir mi equipo (lo construye el paso 6 de docs/plan-mejoras-experiencia-y-rendimiento.md): progreso cancelable, tabla de resultados (velocidad, CPU, si aguanta dos fuentes) y «Aplicar el mejor».
8. Grabación a pantalla completa: arranque (carga del modelo y fuentes detectadas, con spinner), escuchando (transcripción que se desplaza sola; RePág/AvPág para revisar y Fin para volver a lo último, con aviso «N frases nuevas abajo»), frases con palabra clave y capturas marcadas, frase nueva resaltada que se apaga, pausa, aviso de fuente muda o caída, panel [o], vista de rendimiento, leyenda [?], pregunta de salida con audio pendiente, vaciado de la cola con progreso, y el resumen que queda en el historial al salir (nota, duración, frases, capturas, avisos). Desde el menú, al terminar se vuelve al Inicio con el resumen como aviso.
9. Ayuda (teclas y glosario).
10. Ventana abierta: qué ve la terminal mientras la ventana gráfica está abierta y cómo vuelve al menú.
11. Estados comunes: cargando, vacío, error, config.json ilegible, cambios sin guardar, aviso pasajero.
12. Primera ejecución en terminal: logotipo de un segundo como máximo, saltable (enlaza con los pasos 7-8 de docs/plan-mejoras-experiencia-y-rendimiento.md; aquí solo su versión de terminal).
13. `daily -h`: decide si se queda como ayuda estándar de la línea de comandos o se le da estilo; justifícalo.

Entregables (docs/terminal-especificacion.md, con imágenes en docs/terminal-especificacion/)
1. Sistema de maquetación: regiones fijas (cabecera, ruta, cuerpo, ayuda, aviso, pie), alturas por tamaño de terminal, cómo se reparte el espacio vertical, reglas de recorte y de partido de líneas (sangría, «…»).
2. Maqueta final de cada vista del inventario a 100×30 y a 60×24 en el juego «consola» (el del día a día); además, Inicio, Calibrar y Grabación en «completo» y en «ASCII».
3. Catálogo de componentes y modelo de teclas cerrado para todas las vistas, grabación incluida, sin contradicciones (qué tecla hace qué en cada vista).
4. Juegos de símbolos definitivos: tabla símbolo → completo / consola / ASCII, solo con caracteres verificados para «consola».
5. Color: qué token de la paleta lleva cada elemento (sin colores nuevos), su equivalente en 16 colores para la consola sin VT, y comprobación de contraste AA sobre fondo negro, sobre el azul #012456 de PowerShell y sobre fondo claro. Decide si en pantalla completa la app pinta su propio fondo (recomendación de partida: sí, con color real; no, en 16 colores), y justifícalo.
6. Movimiento en terminal: spinner, frase nueva que se apaga, pulso del indicador de grabación (lento, nunca más de 3 cambios por segundo) y aviso pasajero, con tiempos; y qué queda sin movimiento con «animations: reducidas/ninguna».
7. Tabla de textos: cada etiqueta, línea de ayuda, aviso y confirmación, con su clave propuesta para recorder/ayuda.py (prefijos calibrar_, reagrupar_, recomendacion_, rendimiento_, grabacion_, medir_).
8. Lista de cambios respecto al estado actual por vista, para que cada paso de código sepa qué cambia.
```

---

### Paso 2b. Color real y símbolos seguros en la consola de PowerShell y cmd

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`). La consola y el modo ASCII están en recorder/cli/consola.py (make_console, ASCII, EMOJI_SEGURO, asciify, presentar, tema_rich); el arranque en recorder/__main__.py, recorder.py y recorder/cli/app.py (arrancar). El usuario lanza `daily` desde Windows PowerShell 5.1 (función del perfil: `python ...\recorder.py $args`) en la consola clásica conhost; no hay Windows Terminal ni PowerShell 7. Verificado el 24-nov-2026: rich detecta conhost como consola antigua (legacy_windows) y todo sale en ASCII con 16 colores; activando ENABLE_VIRTUAL_TERMINAL_PROCESSING (SetConsoleMode, 0x0004) ANTES de crear la primera rich.Console (rich cachea la detección) la misma consola pasa a truecolor y la paleta se ve tal cual. Con la fuente Consolas se ven bien ─ █ ░ ‹ › ‥ ● · « »; salen como cuadro ▶ y ▁▂▃▅▆▇; ✔ ⚠ y los emoji pisan el espacio siguiente. Evidencia: docs/capturas-terminal/powershell/. Plan y juegos de símbolos: docs/plan-pulido-terminal.md (§1, §3, hallazgos 23 y 25); si ya existe docs/terminal-especificacion.md, su tabla de símbolos manda. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno: el de las herramientas automáticas la trae puesta y rompe una prueba de color) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich, ctypes y la biblioteca estándar.
5. Código, comentarios y textos en español. No añadas campos a config.json.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. No toques recorder/ui/ ni el config.json del usuario (para probar a mano, RECORDER_CONFIG apuntando a una copia). No rediseñes pantallas: otro paso lo hace.

Tarea: que en la consola de PowerShell y de cmd la terminal se vea con los colores reales de la paleta y con símbolos que esa consola sabe dibujar.

Qué hacer
1. Al arrancar en una consola de Windows, antes de crear cualquier rich.Console, activa el modo VT en la salida (y en la de errores) con SetConsoleMode, guardando el modo original. Si falla (Windows antiguo, salida redirigida), todo sigue como hoy. Al salir (normal, Ctrl+C o excepción) se restaura el modo original, se quitan los colores y el cursor queda visible: el prompt de PowerShell queda limpio.
2. Separa color y símbolos en make_console: el color según lo que admita la consola; los símbolos en tres juegos, «completo» (WT_SESSION, TERM_PROGRAM=vscode, terminales no Windows), «consola» (conhost con VT) y «ASCII» (consola sin VT, salida redirigida o `--ascii`, que sigue forzándolo). Ofrece una forma de consultar el juego activo para que las pantallas elijan sus símbolos (marca de fila, barras, tendencia, iconos de fuente, ✔/⚠).
3. Juego «consola»: solo caracteres verificados en Consolas; sin emoji (sustituidos por texto o símbolos seguros), sin ▶ (por ejemplo ›) y tendencia con █ ░ o similares seguros. Actualiza MARCA y CHISPAS de recorder/cli/pantallas.py y los iconos de la grabación para que usen el juego activo.
4. tools/capturar_terminal.py: opción para lanzar cada escenario dentro de Windows PowerShell (`powershell.exe -NoProfile -NoExit -Command ...`) además de cmd, quitando NO_COLOR en ambos.
5. Comprueba que el texto con color real se lea en el fondo negro de una consola nueva y en el azul #012456 del acceso directo de PowerShell; si algún token no llega a AA, anótalo para la especificación (no cambies la paleta en este paso).

Aceptación
- Pruebas: elección del juego de símbolos según el entorno (WT_SESSION, TERM_PROGRAM, VT disponible o no, salida redirigida, --ascii); restauración del modo de consola tras una excepción; ningún símbolo fuera de la lista segura en el juego «consola».
- Capturas con tools/capturar_terminal.py dentro de PowerShell del menú y de Opciones a 100 y 60 columnas en docs/capturas-terminal/powershell/ (en color real) y una con --ascii.
- tests/test_cli_*.py pasan (ajusta las pruebas que daban por hecho ASCII en conhost, explicando por qué). pytest y selftest pasan.

Fuera de alcance: rediseño de pantallas, paleta nueva, PowerShell 7 y Windows Terminal (no están en el equipo; el juego «completo» se prueba con variables de entorno simuladas).
```

---

### Paso 3. Base común: teclas, componentes y una pantalla por módulo

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). En una terminal real `daily menu` abre pantallas navegables (recorder/cli/pantallas.py: Inicio, Opciones, Rendimiento, Ayuda) con rich.Live en pantalla alternativa, lector de teclas común (recorder/cli/teclas.py), consola y modo ASCII (recorder/cli/consola.py), paleta por tokens (recorder/paleta.py) y textos de ayuda (recorder/ayuda.py, sección «Terminal»). Calibrar, Reagrupar nota (sintesis), Recomendación y el asistente `daily config` siguen en modo línea con recorder/cli/preguntas.py; la grabación (`daily`, recorder/cli/live.py) usa rich.Live sin pantalla alternativa. Hallazgos, evidencia y plan completo: docs/plan-pulido-terminal.md, docs/capturas-terminal/ y la especificación docs/terminal-especificacion.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto: rompe una prueba de color) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar (nada de Textual ni curses de terceros).
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada redirigida se conserva el modo línea actual. No toques recorder/ui/ ni el config.json del usuario (para probar a mano, RECORDER_CONFIG apuntando a una copia).

Tarea: dejar la base para que cada pantalla nueva sea pequeña y se pueda hacer en paralelo con las demás.

Qué hacer
1. Teclas (recorder/cli/teclas.py): Inicio, Fin, Supr, RePág y AvPág (Windows: códigos G O S I Q tras \xe0/\x00; POSIX: ESC[H, ESC[F, ESC[1~, ESC[4~, ESC[3~, ESC[5~, ESC[6~), y Espacio con nombre propio si hace falta. Pruebas de decodificación como las de tests/test_cli_teclas.py.
2. Paquete recorder/cli/pantallas/: el bucle y el marco (Terminal), la pantalla base y los componentes en módulos propios; Inicio, Opciones, Rendimiento y Ayuda en el suyo. `from recorder.cli.pantallas import Terminal` sigue valiendo. Inicio abre cada pantalla por un registro acción → clase importada al usarla, para que añadir una pantalla sea crear su módulo y una línea.
3. Componentes del §3 de docs/plan-pulido-terminal.md (o de la especificación si ya existe): lista de ajustes, campo de texto con cursor (←→, Inicio/Fin, Retroceso/Supr), interruptor, numérico con paso y rango, lista de selección como subpantalla, vista previa desplazable, confirmación «antes → después», aviso pasajero, estados vacío y error. Cada uno con pruebas de teclas guionizadas.
4. Opciones pasa a usar los componentes y corrige los hallazgos 9-11: Enter en un ajuste de lista abre la lista de selección; el campo de texto tiene cursor; GPU de whisper.cpp y Flash attention solo con carpeta de whisper.cpp; «Hilos de CPU 0» se lee «automático (4)».
5. Cabecera de una línea fuera de Inicio y «● cambios sin guardar» junto a la ruta; el pie que no cabe deja las teclas principales y «[?] Más».
6. Símbolos y fondo: los componentes y el marco usan el juego de símbolos activo (paso 2b: completo, consola o ASCII); si la especificación lo pide, la pantalla completa pinta el fondo de la paleta. La cabecera corta con «…» también en ASCII (hallazgo 27).
7. Lo que necesitan los pasos 7 y 8: que una pantalla pueda abrirse directamente desde un comando suelto (sin pasar por Inicio; Esc sale a la terminal) y que una pantalla pueda cerrarse devolviendo un aviso para la anterior (la grabación vuelve al Inicio con su resumen).

Aceptación
- tests/test_cli_pantallas.py y tests/test_cli_teclas.py pasan (ajústalos solo si cambia la estructura, explicando por qué) más las pruebas nuevas de componentes.
- A 60 columnas, en ASCII y en el juego «consola» nada se sale ni deja restos (prueba como test_ascii_y_60_columnas). Captura del menú en la consola de PowerShell con tools/capturar_terminal.py.
- pytest y selftest pasan.

Fuera de alcance: Calibrar, Reagrupar, Recomendación y la grabación (pasos 4-7).
```

---

### Paso 4. Calibrar como pantalla

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). En una terminal real `daily menu` abre pantallas navegables (paquete recorder/cli/pantallas/: bucle y marco, componentes comunes y una pantalla por módulo) con lector de teclas común (recorder/cli/teclas.py), consola y modo ASCII (recorder/cli/consola.py), paleta por tokens (recorder/paleta.py) y textos de ayuda (recorder/ayuda.py, sección «Terminal»). `daily calibrar` (recorder/cli/calibrar.py) aún pregunta en línea con recorder/cli/preguntas.py, sobre la lógica de recorder/filters/tuning.py (TuningForm, apply_tuning, test_phrase, THRESHOLD_RANGES). Hallazgos, evidencia y plan: docs/plan-pulido-terminal.md, docs/capturas-terminal/ y docs/terminal-especificacion.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo calibrar_.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada redirigida `daily calibrar` sigue en modo línea (tests/test_cli_calibrar.py intacto). Toca solo recorder/cli/pantallas/calibrar.py, el registro de pantallas y tus textos de ayuda: otros pasos trabajan en paralelo en reagrupar, recomendación y la grabación.

Tarea: Calibrar como pantalla del menú, tan rápida de usar como la ventana.

Qué hacer
1. Lista de ajustes: Vocabulario, Frases a ignorar y Correcciones (campo de texto editable, no reescrito entero; Frases a ignorar con una acción «Añadir las comunes»), los tres filtros (silencio, confianza mínima, repeticiones) como numéricos con paso y rango de THRESHOLD_RANGES y una pista de hacia dónde descartan más, y «Quitar eco del vocabulario» como interruptor. Etiquetas cortas; la explicación en la línea de ayuda (claves vocabulario, ignorar, correcciones, umbral_*, eco_vocab de ayuda.py).
2. Probar una frase: campo en la propia pantalla; el veredicto se recalcula al escribir y al cambiar cualquier ajuste, y dice si aplicó una corrección («Se queda: «…en QA» (corregido: cuba → QA)»). [e] propone una frase de ejemplo (random_sample).
3. Guardar con [g] y confirmación «antes → después»; salir con cambios avisa. Mismo guardado que hoy (apply_tuning + ConfigManager.save) y mismo aviso de reinicio, dicho una vez.
4. Con config.json ilegible: se ve y se prueba, pero no se guarda (como hoy).

Aceptación
- Pruebas guionizadas: editar un campo con cursor, mover un umbral con ←/→ dentro de su rango, veredicto que cambia al cambiar la lista negra, guardar lo mismo que el modo línea, aviso al salir con cambios.
- 60 columnas, ASCII y juego «consola» sin restos; captura en la consola de PowerShell con tools/capturar_terminal.py. pytest y selftest pasan.
```

---

### Paso 5. Reagrupar con vista previa viva

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). En una terminal real `daily menu` abre pantallas navegables (paquete recorder/cli/pantallas/: bucle y marco, componentes comunes y una pantalla por módulo) con lector de teclas común (recorder/cli/teclas.py), consola y modo ASCII (recorder/cli/consola.py), paleta por tokens (recorder/paleta.py) y textos de ayuda (recorder/ayuda.py, sección «Terminal»). `daily sintesis` («Reagrupar nota», recorder/cli/sintesis.py) aún pregunta en línea, sobre recorder/digest/ (list_originals, note_row, digest_options, preview_digest y write_digest, que solo leen el original y nunca lo sobrescriben). Hallazgos, evidencia y plan: docs/plan-pulido-terminal.md, docs/capturas-terminal/ y docs/terminal-especificacion.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo reagrupar_ (reutiliza los de la ventana que ya existen: agrupamiento, unir_lineas, hora_corta, sin_imagenes, descartar_cortas, quitar_eco).
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada redirigida `daily sintesis` sigue en modo línea (tests/test_cli_sintesis.py intacto). Toca solo recorder/cli/pantallas/reagrupar.py, el registro de pantallas y tus textos de ayuda: otros pasos trabajan en paralelo.

Tarea: Reagrupar como pantalla del menú, viendo el resultado mientras se eligen las opciones.

Qué hacer
1. Primero la nota: lista de selección con fecha, hora y tamaño, la más reciente arriba y la que se está escribiendo marcada; estado vacío si no hay notas («No hay notas todavía: se crean al grabar.»).
2. Después las opciones: agrupamiento (‹ Cada 15 min ›) e interruptores (unir frases seguidas, hora corta, quitar imágenes, quitar frases cortas, quitar eco), con los valores por defecto de digest_options. «Hora corta» desactivada con «Sin agrupar» y diciendo por qué.
3. Vista previa que se recalcula al cambiar cualquier opción (preview_digest solo lee): a la derecha desde 80 columnas, debajo si no caben; RePág/AvPág la desplazan; cifras claras («10 frases en 2 tramos · 67 palabras, 0 quitadas»).
4. «Crear la copia» con [g] o Enter en su fila: dice el nombre que tendrá, confirma y crea; nunca sobrescribe. «No es un resumen» se dice una sola vez.

Aceptación
- Pruebas guionizadas: cambiar el agrupamiento cambia la vista previa; «Sin agrupar» desactiva hora corta; crear escribe lo mismo que el modo línea con las mismas opciones; el original queda intacto (compara bytes).
- 60 columnas, ASCII y juego «consola» sin restos; captura en la consola de PowerShell con tools/capturar_terminal.py. pytest y selftest pasan.
```

---

### Paso 6. Recomendación como pantalla, con «Aplicar»

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py). En una terminal real `daily menu` abre pantallas navegables (paquete recorder/cli/pantallas/: bucle y marco, componentes comunes y una pantalla por módulo) con lector de teclas común (recorder/cli/teclas.py), consola y modo ASCII (recorder/cli/consola.py), paleta por tokens (recorder/paleta.py) y textos de ayuda (recorder/ayuda.py, sección «Terminal»). `daily recomendar` (recorder/cli/recomendar.py) imprime en texto plano el equipo detectado, la configuración recomendada y el motivo, sobre recorder/config/hardware.py (cached_hardware, describe_hardware) y recorder/config/schema.py (recommend_config, describe_recommendation, apply_recommendation); `--aplicar` la guarda. Hallazgos, evidencia y plan: docs/plan-pulido-terminal.md, docs/capturas-terminal/ y docs/terminal-especificacion.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo recomendacion_.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada redirigida `daily recomendar` imprime como hoy (tests/test_cli_app.py intacto). Toca solo recorder/cli/pantallas/recomendacion.py, el registro de pantallas y tus textos de ayuda: otros pasos trabajan en paralelo.

Tarea: que la recomendación se entienda de un vistazo y se pueda aplicar ahí mismo.

Qué hacer
1. Spinner mientras se detecta el equipo (cached_hardware puede tardar ~1 s).
2. Tarjeta: «Tu equipo» en una línea; tabla «Ahora / Recomendado / igual o cambia» para calidad, hilos y dónde se transcribe; «Por qué» en dos o tres viñetas llanas; la confianza dicha en palabras («Medido en un equipo como el tuyo»), sin «[medida]», «int8», «haz» ni nombres de campos de config.
3. «Aplicar lo recomendado» con confirmación «antes → después» y el mismo guardado que `--aplicar`; si ya coincide, «Ya usas lo recomendado»; con config.json ilegible no se aplica y se dice por qué.

Aceptación
- Pruebas con perfiles de equipo fijos: filas «igual/cambia» correctas, aplicar guarda lo mismo que `daily recomendar --aplicar`, caso «ya coincide».
- 60 columnas, ASCII y juego «consola» sin restos; captura en la consola de PowerShell con tools/capturar_terminal.py. pytest y selftest pasan.
```

---

### Paso 6b. Rendimiento rediseñado (menú y vista en vivo reutilizable)

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/, que ya tiene un panel de rendimiento en recorder/ui/rendimiento.py) tiene modo terminal con rich (recorder/cli/, comando `daily`). En una terminal real `daily menu` abre pantallas navegables (paquete recorder/cli/pantallas/: bucle y marco, componentes comunes, juego de símbolos activo y una pantalla por módulo). La pantalla Rendimiento actual solo pinta dos barras (CPU y GPU del equipo) y deja dos tercios de la pantalla vacíos; durante la grabación (recorder/cli/live.py) las cifras solo salen en una línea del pie. Las métricas están en recorder/metricas.py (Muestreador, Metricas, MotorEfectivo: motor efectivo y caída a CPU, velocidad por fragmento y media, cola, atraso, CPU del proceso y del sistema, GPU, RAM). Hallazgos, evidencia y plan: docs/plan-pulido-terminal.md (hallazgo 24), docs/capturas-terminal/desde-el-menu/rendimiento/ y la especificación docs/terminal-especificacion.md (vistas «Rendimiento» y «Medir mi equipo»). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo rendimiento_.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Toca solo recorder/cli/pantallas/rendimiento.py, el registro de pantallas y tus textos: otros pasos trabajan en paralelo en Calibrar, Reagrupar, Recomendación y la grabación.

Tarea: que Rendimiento diga de un vistazo si el equipo da para grabar y cómo va una grabación, aprovechando la pantalla.

Qué hacer
1. Sin grabación (desde el menú), según la especificación: equipo (núcleos P/E, RAM, GPU integrada o dedicada), motor que se usaría y por qué (caída a CPU incluida), cifras vivas de CPU, GPU y RAM con tendencia de los últimos ~2 min, y el margen dicho en palabras («Hay margen para grabar» / «El equipo va cargado: cierra algo o baja la calidad»). Primer dato en cuanto haya muestra, sin «__» vacíos. Si existe «Medir mi equipo», su acceso desde aquí; si no, no se muestra.
2. Vista en vivo reutilizable: una función pura que, dadas unas Metricas y sus historias, devuelva las líneas para un ancho y un alto (velocidad frente al tiempo real y si va al día o se atrasa, cola y atraso, CPU del proceso y del sistema, GPU, RAM, último fragmento, motor efectivo y caída). La pantalla del menú y la grabación (paso 7) la usan igual.
3. Símbolos del juego activo (sin ▁▂▃ en «consola»), colores de la paleta y nada que dependa solo del color.

Aceptación
- Pruebas de la función pura con métricas fijas: textos de margen, «va al día / se atrasa», caída a CPU, n/d de GPU, a 100 y 60 columnas y en los tres juegos de símbolos.
- Captura en la consola de PowerShell con tools/capturar_terminal.py. pytest y selftest pasan.
```

---

### Paso 7. Grabación a pantalla completa

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`). La grabación (`daily`, recorder/cli/live.py, clase PantallaEnVivo, sobre recorder/session.py) imprime hoy la cabecera y las frases en el historial de la terminal, mezcladas con lo anterior, y mantiene un pie vivo con rich.Live sin pantalla alternativa: estado, medidores, motor y teclas; [o] abre un panel de opciones que solo se maneja con números. El usuario la usa en Windows PowerShell 5.1 (conhost) y le resulta confusa: pasa a pantalla completa. Lector de teclas común en recorder/cli/teclas.py; marco, componentes, juego de símbolos activo y estilo del menú en el paquete recorder/cli/pantallas/; vista de rendimiento reutilizable en recorder/cli/pantallas/rendimiento.py; consola en recorder/cli/consola.py; textos en recorder/ayuda.py (sección «Terminal»: tecla_*, cierre_*). Hallazgos (1, 14, 22, 26), evidencia y plan: docs/plan-pulido-terminal.md, docs/capturas-terminal/grabar/, docs/capturas-terminal/desde-el-menu/grabar/ y la especificación docs/terminal-especificacion.md (vista «Grabación»). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto: rompe una prueba de color de tests/test_cli_live.py) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo grabacion_.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva (el teclado guionizado de tests/test_cli_live.py).
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Toca solo recorder/cli/live.py, sus pruebas y tus textos: otros pasos trabajan en paralelo en las pantallas del menú. No reproduzcas audio por los altavoces sin comprobar antes que no suena nada más ni hay una llamada en curso.

Tarea: que la grabación sea una pantalla limpia y controlada, como el resto, sin perder nada de lo que ya hace (la nota en disco sigue siendo el registro completo).

Qué hacer (según la vista «Grabación» de la especificación)
1. Pantalla completa (pantalla alternativa) con regiones fijas: cabecera (nota, calidad y motor, estado ● Escuchando / Pausa / Terminando, tiempo transcurrido), cuerpo con la transcripción, aviso, línea de ayuda y pie de teclas.
2. Transcripción: se desplaza sola con lo último a la vista; RePág/AvPág (e Inicio) para revisar y Fin para volver a lo último, con «N frases nuevas abajo» mientras se revisa; palabras clave y capturas marcadas; la frase nueva resaltada se apaga en ~1,5 s (respeta «animations»). En memoria, como la ventana, solo las últimas ~2000 líneas.
3. Arranque en la propia pantalla (spinner mientras carga el modelo y se abren las fuentes; fuentes detectadas en una línea que se parte con sangría), sin escribir en el historial.
4. Panel [o]: fila elegida con la marca del juego activo y ↑/↓ (los números siguen siendo atajos), Enter elige, Esc vuelve; línea de ayuda de la fila (salida_audio, microfono, que_capturar, capturas_clave); índice en lista vertical. ←/→ no aplican dispositivos en vivo.
5. [m] abre la vista de rendimiento en vivo (la función de recorder/cli/pantallas/rendimiento.py) y Esc vuelve; [?] muestra la leyenda de teclas (tecla_*). Pie con el mismo estilo de botones que el menú, recortado con criterio a 60 columnas.
6. Salida: la pregunta con audio pendiente (Esc sigue grabando) y el vaciado de la cola con progreso, dentro de la pantalla. Al salir de la pantalla alternativa se imprime en el historial solo el resumen (nota, duración, frases, capturas, avisos). Deja preparado que, abierta desde el menú, la grabación devuelva ese resumen como aviso para el Inicio (la integración con el menú la hace el paso 8).
7. `daily --historial` y la salida redirigida conservan el modo actual (frases en el historial con pie vivo).
8. Coste: repintar solo cuando algo cambia o en el tic (máximo ~5 por segundo); pintar solo las líneas visibles; nada bloquea los hilos de audio ni de transcripción.
9. Textos que no se entienden: «(despierto)», «[Loopback]», «¿no aparece?…» (solo en las secciones de dispositivos y más corto).

Aceptación
- Pruebas guionizadas con la sesión de mentira de tests/test_session.py: autodesplazamiento y revisión con RePág/Fin («N frases nuevas»), panel con flechas y números, [m] y [?], que ←/→ no reabren el audio, salida con pendientes (Esc sigue), resumen impreso al salir y `--historial` con el comportamiento anterior.
- tests/test_cli_live.py pasa (ajústalo solo donde cambie la forma, explicando por qué). 60 columnas, ASCII y juego «consola» sin restos.
- Prueba a mano en la consola de PowerShell: el prompt queda limpio al salir, también con Ctrl+C. Antes de grabar con audio de prueba, comprueba que no suena nada más ni hay una llamada en curso.
```

---

### Paso 8. Cada comando abre su pantalla; grabar y la ventana vuelven al menú

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`; subcomandos con un contrato mínimo en recorder/cli/app.py: NOMBRE, AYUDA, agregar_argumentos, ejecutar). `daily menu` abre pantallas navegables (paquete recorder/cli/pantallas/) entre las que ya están Opciones, Calibrar, Reagrupar y Recomendación; los comandos sueltos (`daily config`, `daily calibrar`, `daily sintesis`, `daily recomendar`) aún preguntan en línea con recorder/cli/preguntas.py, que es lo que usan los scripts y tests/test_cli_*.py. Hallazgos y plan: docs/plan-pulido-terminal.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español. No añadas campos a config.json.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva.
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Con la entrada o la salida redirigidas, o con argumentos de script (`--ver`, `--editor`, `--recomendado`, `--probar`, `--aplicar`, la nota y `--si`), todo sigue exactamente como hoy.

Tarea: que no haya dos interfaces para lo mismo en una terminal real.

Qué hacer
1. En una terminal real y sin argumentos de script, `daily config`, `daily calibrar`, `daily sintesis` y `daily recomendar` abren directamente su pantalla (Opciones, Calibrar, Reagrupar, Recomendación) dentro del mismo marco; Esc en ella sale a la terminal (no al Inicio).
2. Desde el menú ya no se sale de la pantalla alternativa para ellos: se abren como pantallas. Desaparecen el «[una tecla] volver al menú» y la intro duplicada (hallazgos 20 y 21).
3. Grabar desde el menú abre la pantalla de grabación (paso 7) y, al terminar, vuelve al Inicio con el resumen como aviso, en vez de dejar el prompt (hallazgo 22). `daily` sin argumentos abre la grabación a pantalla completa y al salir deja el resumen en el historial.
4. Abrir la ventana desde el menú: la terminal muestra «La ventana está abierta; ciérrala para volver aquí» y vuelve al Inicio al cerrarla (hallazgo 28).
5. La ayuda de `daily -h` y el docstring de recorder/cli/app.py lo cuentan (incluido `--historial`).

Aceptación
- Pruebas: cada comando elige pantalla con TTY y modo línea sin ella (como test_menu_elige_las_pantallas_en_una_terminal); los argumentos de script nunca abren pantallas; grabar y la ventana vuelven al Inicio con su aviso.
- Recorrido a mano en la consola de PowerShell (función `daily` del perfil, con RECORDER_CONFIG apuntando a una copia): del menú a cada opción y de vuelta, sin que nada aparezca en el historial salvo el resumen de la grabación.
- tests/test_cli_*.py pasan. pytest y selftest pasan.
```

---

### Paso 9. Verificación con evidencia antes/después

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams. Su modo terminal (`daily`, recorder/cli/) se ha pulido por pasos (docs/plan-pulido-terminal.md): correcciones, especificación visual (docs/terminal-especificacion.md), componentes comunes y pantallas para Calibrar, Reagrupar, Recomendación, la grabación y los comandos sueltos. La evidencia del estado anterior está en docs/capturas-terminal/ y se regenera con tools/capturar_terminal.py (consola clásica real, abre ventanas durante unos 3 minutos) y tools/capturar_terminal_svg.py (terminal moderna en SVG). El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea el recorrido de verificación y después ejecútalo.
2. No hagas commits ni push. Corrige solo lo trivial (y dilo); lo demás se anota.
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, documentación ni commits propuestos.
4. Antes de grabar con audio de prueba comprueba que no suena nada más ni hay una llamada en curso. No toques el config.json del usuario: los scripts de captura usan uno sintético.
5. Informa los fallos con su salida real; no los suavices.

Tarea: comprobar que todas las pantallas de terminal quedaron limpias, controladas y coherentes.

Qué hacer
1. Guarda la evidencia anterior en docs/capturas-terminal/antes/ y regenera con los dos scripts (actualiza sus escenarios a los flujos nuevos: teclas en vez de números, y entrar desde el menú a cada opción como en docs/capturas-terminal/desde-el-menu/), en cmd y dentro de Windows PowerShell. Compara pantalla por pantalla contra los hallazgos 1-28 de docs/plan-pulido-terminal.md §2 y marca cada uno como resuelto, parcial o pendiente.
2. A mano en la consola del día a día: Windows PowerShell 5.1 con la función `daily` del perfil (RECORDER_CONFIG apuntando a una copia), con el fondo negro de una consola nueva y con el azul #012456 del acceso directo de PowerShell: color real, símbolos sin cuadros ni solapes, prompt limpio al salir de cada vista, también con Ctrl+C (la inyección no equivale al teclado). Además: Ctrl+C en una pregunta de modo línea, cmd, `--ascii`, 60 columnas, tema claro y oscuro, Windows Terminal y PowerShell 7 si están instalados, y Linux si hay una distribución en WSL (si no, dilo).
3. Recorrido de uso real: abrir el menú, grabar unos minutos (con audio de prueba, comprobando antes que no suena nada más ni hay una llamada en curso), revisar la transcripción con RePág, abrir [m] y [o], salir y comprobar que se vuelve al menú con el resumen y que en el historial de PowerShell no queda nada más que ese resumen.
4. Busca en el diff completo menciones a asistentes, agentes o herramientas de IA.
5. Informe en docs/verificacion-pulido-terminal.md: qué pasó, qué falló (con salida), capturas antes/después y pendientes.
```

---

## 6. Fuera de este plan

* **Grabar en Linux**: necesita otro backend de audio (PulseAudio/PipeWire); sigue fuera, como en el plan anterior.
* Ratón, explorador de carpetas, editor multilínea y vista previa con Markdown renderizado: no compensan en terminal (§1, decisiones). La pantalla completa de la grabación **sí** entra (decisión 1, paso 7).
* **PowerShell 7 y Windows Terminal**: no están instalados en el equipo de desarrollo; el juego de símbolos «completo» se prueba con variables de entorno simuladas y queda por verificar a mano donde los haya.
* **La ventana Tkinter**: tiene su propio recorrido de capturas en `docs/capturas-ui/`.
