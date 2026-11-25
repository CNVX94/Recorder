# Plan de pulido: pantallas de terminal

Noviembre de 2026. Sigue al paso 5 de `docs/plan-mejoras-experiencia-y-rendimiento.md` (terminal
interactiva, commit «Agrega menú navegable por teclado en la terminal»). Objetivo: que **todas** las
pantallas de `daily` sean limpias, controladas y con el mismo estilo que el menú nuevo. Plan por
pasos con un prompt autocontenido para cada uno: se copia tal cual en una sesión nueva abierta en
este repositorio.

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

### Estado por pantalla

| Pantalla | Cómo es hoy | Evidencia | Consecuencia para el plan |
| :--- | :--- | :--- | :--- |
| Menú (`daily menu`, `cli/pantallas.py`) | Pantallas navegables: cabecera viva, ruta, lista con ▶, ayuda de lo elegido, pie de botones. | `menu/`, `svg/menu-*.svg` | Es la referencia. Tiene tres fallos propios (§2). |
| Calibrar (`cli/calibrar.py`) | Menú numerado de 8 opciones que se reimprime entero tras cada acción; preguntas en línea; prueba de frases con `frase>`. | `calibrar/`, `calibrar-60/`, `svg/calibrar*.svg` | Pasar a pantalla con lista de ajustes y prueba en vivo. |
| Reagrupar nota (`cli/sintesis.py`) | Elegir nota por número, 6 preguntas seguidas a ciegas, vista previa de 10 líneas al final y confirmar. | `sintesis/`, `sintesis-60/`, `svg/sintesis.svg` | Pasar a pantalla con interruptores y vista previa que cambia al momento. |
| Recomendación (`cli/recomendar.py`) | Tres líneas de texto plano sin color; el motivo es un párrafo de 6 líneas; no se puede aplicar desde ahí. | `recomendar/`, `svg/recomendar.svg` | Pantalla tipo tarjeta «ahora / recomendado» con «Aplicar». |
| Asistente `daily config` (`cli/configurar.py`) | Secciones por número y preguntas en línea; tras confirmar el guardado de una sección, sale. | `config/`, `config-ver/`, `svg/config.svg` | En terminal real, `daily config` abre la pantalla Opciones; el asistente queda para entrada redirigida. |
| Grabación (`daily`, `cli/live.py`) | `rich.Live` sin pantalla alternativa (bien: el historial se puede copiar). El panel [o] solo acepta números. | `grabar/`, `svg/grabar.svg` | Mantener el formato; panel navegable con flechas, [?] y teclas coherentes. |
| Paso del menú a un comando | Sale de la pantalla alternativa, imprime la ayuda del menú, el comando repite su propia intro, y vuelve «pulsando una tecla». | `menu/02_*`, `menu/03_*` | Desaparece cuando cada comando tenga su pantalla. |

### Decisiones tomadas por defecto (cámbialas antes de lanzar el paso que afecta)

1. **La grabación sigue sin pantalla alternativa**: las frases se quedan en el historial de la terminal.
2. **El modo línea no se toca**: con la entrada redirigida (scripts, pruebas) cada comando funciona como hoy. Es el contrato de `tests/test_cli_*.py`.
3. **←/→ nunca aplica un dispositivo de audio en vivo**: reabriría el audio a cada paso en plena reunión. Se elige con Enter.
4. **Sin ratón, marcos dibujados ni ventanas modales**: frágiles en conhost y caros a 60 columnas.
5. **Una pantalla por módulo** (paso 3) para que Calibrar, Reagrupar, Recomendación y grabación puedan hacerse en paralelo.

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
| 2 | Especificación visual y de textos | diseño | — | `docs/terminal-especificacion.md` | 1 |
| 3 | Base común: teclas nuevas, componentes y una pantalla por módulo | código | 1, 2 | `cli/teclas.py`, `cli/pantallas.py` → `cli/pantallas/` | — |
| 4 | Calibrar como pantalla | código | 3 | nuevo `cli/pantallas/calibrar.py` | 5, 6, 7 |
| 5 | Reagrupar con vista previa viva | código | 3 | nuevo `cli/pantallas/reagrupar.py` | 4, 6, 7 |
| 6 | Recomendación como pantalla, con «Aplicar» | código | 3 | nuevo `cli/pantallas/recomendacion.py` | 4, 5, 7 |
| 7 | Grabación: panel [o] navegable, [?] y teclas coherentes | código | 3 | `cli/live.py` | 4, 5, 6 |
| 8 | Cada comando abre su pantalla en una terminal real | código | 4, 5, 6 | `cli/app.py`, `cli/configurar.py`, `cli/calibrar.py`, `cli/sintesis.py`, `cli/recomendar.py` | — |
| 9 | Verificación con evidencia antes/después | código | todos | `docs/capturas-terminal/`, `docs/verificacion-pulido-terminal.md` | — |

* Si dos pasos van en paralelo, cada uno en su propia copia de trabajo (worktree) y se integran uno tras otro.
* Los pasos 4-7 añaden textos a la sección «Terminal» de `recorder/ayuda.py`, cada uno con su prefijo (`calibrar_`, `reagrupar_`, `recomendacion_`, `grabacion_`), para que integrar sea trivial.
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

### Paso 2. Especificación visual y de textos (perfil diseño)

```text
Contexto del proyecto
Recorder es una app que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Tiene modo terminal con rich (comando `daily`): un menú de pantallas navegables por teclado (recorder/cli/pantallas.py: cabecera viva, ruta «Inicio › Opciones», lista con ▶, línea de ayuda de lo elegido, pie de botones «[Enter] Abrir · [Esc] Salir…»), y comandos que aún funcionan pregunta a pregunta: Calibrar (filtros de frases inventadas y vocabulario, con prueba de frases), Reagrupar nota (copia ordenada por hora y tramos, no resume), Recomendación (qué calidad conviene al equipo) y el asistente de configuración. La grabación (`daily`) imprime las frases en el historial y deja un pie vivo con estado, medidores y teclas. Estado actual con capturas: docs/capturas-terminal/ (svg/galeria.png es la vista general en una terminal moderna; las carpetas por escenario son la consola clásica de Windows, en ASCII y 16 colores). Hallazgos, sistema común propuesto y maquetas de partida: docs/plan-pulido-terminal.md §2 y §3. Ventana de escritorio equivalente, para la coherencia: docs/capturas-ui/oscuro-100-calibrar.png, -reagrupar.png, -opciones.png. Paleta por tokens en recorder/paleta.py (texto, tenue, acento, mic, error, ok, borde, elegido), con contraste AA en tema claro y oscuro. Textos de ayuda en recorder/ayuda.py (tuteo, lenguaje llano, una o dos frases de hasta 180 caracteres).

Reglas de trabajo
1. Primero planea (qué pantallas, en qué orden, preguntas abiertas), después produce los entregables.
2. No hagas commits ni push. Propón un mensaje de commit en español («Agrega…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en los entregables, nombres de archivo ni el commit propuesto.
4. No escribas código de la aplicación. Usa el flujo /design para la propuesta visual si está disponible; si no, entrega maquetas en texto monoespaciado.
5. Termina con: entregables y rutas, decisiones tomadas y preguntas abiertas.

Restricciones técnicas: solo lo que rich pinta en una terminal (texto, colores de la paleta, negrita, reglas); nada de ratón, marcos dibujados ni ventanas modales; debe funcionar desde 60 columnas y en ASCII sin emoji (conhost); la grabación no usa pantalla alternativa.

Tarea: fijar cómo se ve y qué dice cada pantalla de terminal, para que los pasos de código solo tengan que construirlo.

Entregables (docs/terminal-especificacion.md)
1. Maquetas finales de Calibrar (con la prueba de frases), Reagrupar (lista de notas y opciones con vista previa), Recomendación, el pie y el panel [o] de la grabación, la confirmación «antes → después», los estados vacío y error, y el aviso de cambios sin guardar. Cada una a 100 y a 60 columnas, y una en ASCII.
2. El catálogo de componentes y el modelo de teclas de §3, cerrados: qué tecla hace qué en cada pantalla, sin contradicciones.
3. Tabla de textos: cada etiqueta, línea de ayuda, aviso y confirmación, con su clave propuesta para recorder/ayuda.py (prefijos calibrar_, reagrupar_, recomendacion_, grabacion_).
4. Qué color de la paleta lleva cada elemento (sin colores nuevos).
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

Aceptación
- tests/test_cli_pantallas.py y tests/test_cli_teclas.py pasan (ajústalos solo si cambia la estructura, explicando por qué) más las pruebas nuevas de componentes.
- A 60 columnas y en ASCII nada se sale ni deja restos (prueba como test_ascii_y_60_columnas).
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
- 60 columnas y ASCII sin restos. pytest y selftest pasan.
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
- 60 columnas y ASCII sin restos. pytest y selftest pasan.
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
- 60 columnas y ASCII sin restos. pytest y selftest pasan.
```

---

### Paso 7. Grabación: panel [o] navegable, [?] y teclas coherentes

```text
Contexto del proyecto
Recorder es una app en Python 3.14 que transcribe en vivo las dailies de Teams y escribe una nota Markdown. Además de la ventana Tkinter (recorder/ui/) tiene modo terminal con rich (recorder/cli/, comando `daily`). La grabación (`daily`, recorder/cli/live.py, clase PantallaEnVivo) imprime las frases en el historial de la terminal y mantiene un pie vivo con rich.Live (sin pantalla alternativa, a propósito: el historial se puede copiar): estado, medidores, motor y teclas; [o] abre un panel de opciones que hoy se maneja solo con números. Lector de teclas común en recorder/cli/teclas.py; componentes y estilo del menú en el paquete recorder/cli/pantallas/; consola y modo ASCII en recorder/cli/consola.py; textos en recorder/ayuda.py (sección «Terminal»: tecla_*, cierre_*). Hallazgos, evidencia y plan: docs/plan-pulido-terminal.md, docs/capturas-terminal/grabar/ y docs/terminal-especificacion.md. El repositorio tiene índice CodeGraph (.codegraph/): usa las herramientas codegraph_* (context, search, callers, impact, explore) antes de abrir archivos; si no responde, `codegraph init -i`. Pruebas: `python -m pytest` (quita NO_COLOR del entorno si está puesto: rompe una prueba de color de tests/test_cli_live.py) y `python recorder.py --selftest`. Shell: PowerShell 5.1.

Reglas de trabajo
1. Primero planea: explora con codegraph, escribe un plan breve (archivos, cambios, riesgos, cómo verificarás) y después ejecútalo. Solo detente a preguntar si aparece una decisión que cambie el alcance.
2. No hagas commits ni push. Deja los cambios en el árbol de trabajo y propón un mensaje de commit en español, en el estilo de los commits del repo («Agrega…», «Corrige…», «Permite…»).
3. No menciones asistentes, agentes, modelos ni herramientas de IA en código, comentarios, documentación ni en el commit propuesto; sin líneas de coautoría.
4. Sin dependencias nuevas: rich y la biblioteca estándar.
5. Código, comentarios y textos en español, tuteo y lenguaje llano. No añadas campos a config.json. Textos de ayuda nuevos solo en la sección «Terminal» de recorder/ayuda.py, con el prefijo grabacion_.
6. `python -m pytest` y `python recorder.py --selftest` deben pasar; añade pruebas para la lógica nueva (el teclado guionizado de tests/test_cli_live.py).
7. Termina con: archivos cambiados, cómo se verificó, qué queda pendiente o sin verificar, y el commit sugerido.
8. Toca solo recorder/cli/live.py, sus pruebas y tus textos: otros pasos trabajan en paralelo en las pantallas del menú. No reproduzcas audio por los altavoces sin comprobar antes que no suena nada más ni hay una llamada en curso.

Tarea: que la grabación se maneje igual que el resto de pantallas sin perder lo que ya hace bien.

Qué hacer
1. Panel [o]: fila elegida con ▶ y ↑/↓ (los números siguen siendo atajos), Enter elige, Esc vuelve; línea de ayuda de la fila (salida_audio, microfono, que_capturar, capturas_clave); el índice en una lista vertical, no en una línea partida. ←/→ no aplican dispositivos en vivo.
2. [?] muestra en el pie la leyenda de teclas con su explicación corta (tecla_*), y Esc la cierra.
3. Pie con el mismo estilo de botones que el menú («[p] Pausar · [c] Captura · … · [?] Teclas · [q] Salir»), recortado con criterio si no cabe en 60 columnas.
4. Textos que no se entienden en ASCII: «(despierto)», «[Loopback]» en la línea de fuentes; la línea de fuentes y la ruta final con sangría al partirse; «¿no aparece?…» solo en las secciones de dispositivos y más corto.

Aceptación
- Pruebas guionizadas del panel con flechas y con números, de [?] y de que ←/→ no reabren el audio (la sesión de mentira de tests/test_session.py cuenta los reinicios).
- tests/test_cli_live.py pasa. 60 columnas y ASCII sin restos.
```

---

### Paso 8. Cada comando abre su pantalla en una terminal real

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
2. Desde el menú ya no se sale de la pantalla alternativa para ellos: se abren como pantallas. Desaparecen el «[una tecla] volver al menú» y la intro duplicada (hallazgo 20).
3. La ayuda de `daily -h` y el docstring de recorder/cli/app.py lo cuentan.

Aceptación
- Pruebas: cada comando elige pantalla con TTY y modo línea sin ella (como test_menu_elige_las_pantallas_en_una_terminal); los argumentos de script nunca abren pantallas.
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
1. Guarda la evidencia anterior en docs/capturas-terminal/antes/ y regenera con los dos scripts (actualiza sus escenarios a los flujos nuevos: teclas en vez de números). Compara pantalla por pantalla contra los hallazgos de docs/plan-pulido-terminal.md §2 y marca cada uno como resuelto, parcial o pendiente.
2. A mano: Ctrl+C en cada pantalla y en una pregunta de modo línea (la inyección no equivale al teclado), Windows Terminal si está instalado, conhost, 60 columnas, tema claro y oscuro, y Linux si hay una distribución en WSL (si no, dilo).
3. Busca en el diff completo menciones a asistentes, agentes o herramientas de IA.
4. Informe en docs/verificacion-pulido-terminal.md: qué pasó, qué falló (con salida), capturas antes/después y pendientes.
```

---

## 6. Fuera de este plan

* **Grabar en Linux**: necesita otro backend de audio (PulseAudio/PipeWire); sigue fuera, como en el plan anterior.
* **Pantalla alternativa en la grabación**, ratón, marcos dibujados, explorador de carpetas, editor multilínea y vista previa con Markdown renderizado: no compensan en terminal (§1, decisiones).
* **La ventana Tkinter**: tiene su propio recorrido de capturas en `docs/capturas-ui/`.
