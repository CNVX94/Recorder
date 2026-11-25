# Verificación del pulido de la terminal

Noviembre de 2026. Paso 9 de `docs/plan-pulido-terminal.md`: comprobar con evidencia antes/después que las
pantallas de `daily` quedaron limpias, controladas y coherentes. Partida: los pasos 1-8 y «Medir mi equipo» hechos.

## 1. Cómo se verificó

| Qué | Cómo |
| :--- | :--- |
| Antes | Copia de la evidencia anterior al pulido en `docs/capturas-terminal/antes/` (menú numerado, comandos con preguntas en línea, `desde-el-menu/`, `powershell/menu/`, SVG). |
| Después, cmd | `python tools/capturar_terminal.py --cmd docs/capturas-terminal/despues/cmd`: consola clásica real, config sintético, teclas inyectadas con `WriteConsoleInputW`, texto del búfer y PNG de la ventana. |
| Después, Windows PowerShell 5.1 | Igual con `--powershell` (`powershell.exe -NoProfile -NoExit`), en `docs/capturas-terminal/despues/powershell/`, también con el azul #012456 del acceso directo (`inicio-azul`, `inicio-ascii-azul`). |
| Terminal moderna | `python tools/capturar_terminal_svg.py docs/capturas-terminal/despues/svg` (truecolor, SVG). |
| Pruebas | `python -m pytest` y `python recorder.py --selftest` (ver §5). |
| Diff | Búsqueda en el diff desde `81729f8` de menciones a asistentes o IA y de valores fijos (§4). |

Las capturas usan un config.json y unas notas sintéticos y temporales; el prompt muestra la raíz del
repositorio, no la copia de trabajo. En `antes/` y en algunas capturas antiguas aparecen nombres reales de
dispositivos de audio y del equipo (ya lo advertía el plan).

Cambios en las herramientas de captura: los escenarios usan flechas y Enter en lugar de números; se añadieron
`menu` (recorrido completo), `sintesis-linea` (Ctrl+C en una pregunta de modo línea), `sintesis-90/100`,
`inicio-claro`, `inicio-azul`, `ayuda-menu`, `ventana` (la cierra con WM_CLOSE), `grabar-menu`, `grabar-60`,
`historial`; `--help` y `--lista`; el prompt de la copia de trabajo se sustituye por la raíz del repositorio.
`tools/capturar_terminal_svg.py` estaba roto desde el rediseño del paquete `pantallas` (`AttributeError`) y se
repuso con el recorrido del menú.

## 2. Hallazgos 1-28

Resuelto = visto en una captura de este paso o cubierto por una prueba; parcial = mejorado con algo que queda;
pendiente = no se pudo comprobar o sigue igual.

| # | Estado | Evidencia / nota |
| :-: | :-: | :--- |
| 1 | Resuelto (código y pruebas) | La confirmación de salida es «[e] esperar y salir · [s] salir sin esperar · [Esc] seguir grabando» (`live.py`, `TECLAS_CIERRE`). No visto en vivo: ver §6. |
| 2 | Resuelto | `despues/cmd/calibrar/`: vocabulario y frases a ignorar se editan con cursor. |
| 3 | Resuelto | `calibrar-pantalla-100/09_aviso-sin-guardar` y Esc dos veces. |
| 4 | Resuelto | Pantalla única, sin reimpresión; a 60 columnas `calibrar-60/01_calibrar`. |
| 5 | Resuelto | Vista previa viva: `sintesis-100/02_vista-previa`, `sintesis-90`, `sintesis-60`. |
| 6 | Resuelto en la pantalla; parcial en `recomendar --aplicar` | La pantalla `recomendar/01_recomendacion` es una tarjeta «Ahora / Recomendado» con «Aplicar». El modo de script (`--aplicar`) conserva «[medida]», «int8», «whispercpp_device» (es el contrato de los scripts). |
| 7 | Resuelto | `daily config` abre Opciones (`config/01_opciones`); el asistente queda para entrada redirigida. |
| 8 | Resuelto (pruebas) | El aviso sale en `base-100/08_aviso-sin-guardar`. |
| 9 | Resuelto | Enter abre la lista (`base-100/06_lista-de-seleccion`). |
| 10 | Resuelto | Cursor movible (`base-100/04_texto-con-cursor`). |
| 11 | Resuelto | «Carpeta de whisper.cpp (vacío)» oculta GPU y flash; «Hilos de CPU automático (4)». |
| 12 | Resuelto | «Filtro de silencio / Confianza mínima / Filtro de repeticiones» con su ayuda llana. |
| 13 | Resuelto | `calibrar-pantalla-100/05_*`: «corregido: cuba → QA». |
| 14 | Resuelto | El panel [o] de la grabación tiene fila elegida, línea de ayuda, índice 1-4 directo y [?] (visto en una captura real que se descartó por llevar audio ajeno, ver §6). |
| 15 | Resuelto | Cifras claras («7 frases en 2 tramos · 67 palabras, 0 quitadas»); a 60 columnas la tabla pasa a forma estrecha. |
| 16 | Resuelto | `inicio-ascii/*`: sin espacio inicial, ficha con sangría, «...» como elisión. |
| 17 | Parcial | El asistente de línea mantiene «Precisión del cálculo» y «Dónde se transcribe» (`configurar.py`). Solo se ve con entrada redirigida. |
| 18 | Resuelto | `digest/writer.py` lleva tildes. |
| 19 | Resuelto | `descartar_cortas` y `reagrupar_cortas` avisan de lo mismo («Sí, va.»). |
| 20 | Resuelto | Ya no hay «volver al menú» con cualquier tecla: `menu/03_de-vuelta-en-inicio`. |
| 21 | Resuelto | `menu/*` y `historial-limpio`: nada queda en el historial al volver. |
| 22 | Parcial (sin verificar en vivo) | Ver §6: la grabación real no se pudo repetir con el equipo en silencio. El código y las pruebas cubren la vuelta al Inicio con el resumen. |
| 23 | Resuelto | Color real (VT) en cmd y en PowerShell: `despues/*/menu/*.png`. |
| 24 | Resuelto | `menu/07_rendimiento`, `base-100/11_rendimiento`: equipo, memoria, margen y tendencia. |
| 25 | Resuelto | Sin cuadros ni solapes en conhost con color real (`powershell/menu/05_recomendacion.png`). |
| 26 | Resuelto | Arranque «Preparando…» y resumen final «grabación terminada» con su pantalla (visto en la captura de grabación descartada). |
| 27 | Resuelto | `inicio-ascii/01_inicio`: «C:\Users\DESAR...\Local…», «bloq...». |
| 28 | Resuelto | `ventana/02_ventana-abierta` y `03_tras-cerrar`: «Ventana cerrada: has vuelto al menú.» |

## 3. Fallos y diferencias encontrados

1. **Tema claro: títulos invisibles (corregido).** Con `theme: claro` y color real, todo texto sin color propio (títulos en
   negrita como «Recorder», «Inicio», «Próxima grabación», «Equipo») salía en el blanco de la consola sobre el fondo
   claro de la paleta (#eff1f5). Medido en `despues/cmd/inicio-claro-sin-corregir/01_inicio.png`: el título tiene un
   mínimo de suma RGB de 722 (casi blanco). Causa: el estilo `fondo` solo definía el fondo. Corrección: ahora lleva
   también el color de texto del tema (`recorder/cli/consola.py`). Tras la corrección, `despues/cmd/inicio-claro/`
   (el título pasa a #3c3f55). Prueba nueva: `test_el_fondo_propio_lleva_el_color_de_texto_del_tema`.
2. **Descripción de «Grabar» en el menú numerado (corregido).** Decía «Al terminar vuelves a este menú» y no es
   cierto con entrada redirigida (el proceso termina). Ahora usa `menu_grabar_linea`; prueba ampliada en
   `tests/test_cli_menu.py`.
3. **`tools/capturar_terminal.py --help` (corregido)** se tomaba como carpeta de salida.
4. **`tools/capturar_terminal_svg.py` roto (corregido):** `AttributeError: module 'recorder.cli.pantallas' has no
   attribute 'configurar'`.
5. **Ctrl+C inyectado en una pregunta de modo línea** (`sintesis-linea/02_tras-ctrl-c.txt`): tras el evento la pantalla
   sigue en «Número (3):» y no vuelve el prompt. El evento inyectado no equivale al del teclado: queda sin verificar (§6).
6. **Audio ajeno en la grabación real.** La primera captura de `grabar` transcribió una canción que sonaba en el
   equipo («Altavoces (Realtek(R) Audio)»), aunque el medidor del dispositivo predeterminado marcaba silencio justo antes:
   el medidor no vigilaba ese punto de salida. Se paró la tanda y se borraron esas capturas (llevaban la letra); no se
   repitió la grabación real.
7. **Ayuda cortada a mitad de frase** en «Hilos de CPU» con el aviso de núcleos mezclados («…0 usa el valor de…»,
   `ajustes-100/02_hilos-con-aviso.txt`): cumple la regla de «…» de la especificación pero pierde la frase útil. Pendiente.
8. **Diferencias con la especificación (no corregidas, decisión de diseño):**
   * La nota de hoy inexistente sale «aún no hay (se crea al grabar)» (`pantallas/base.py:57`); la especificación (`inicio_sin_nota`) dice «aún no hay».
     Además el texto está escrito en el código y no en `recorder/ayuda.py`.
   * Reagrupar pasa a dos columnas desde 80 columnas (`reagrupar.py`, `ANCHO_DOS_COLUMNAS = 80`); la especificación
     (§1.2, punto 5) dice 96. A 90 columnas la vista previa ya va a la derecha y se lee bien (`sintesis-90`). Conviene
     cambiar la especificación, no el código: 80 es el ancho de la consola por defecto.

## 4. Búsqueda en el diff completo (desde `81729f8`)

* Menciones a asistentes, agentes o IA: ninguna. «asistente» aparece solo como el asistente de configuración de `daily config`.
* Colores fuera de la paleta: ninguno en `recorder/` (los hex solo están en pruebas, para comprobar la paleta).
* Rutas o datos de este equipo: ninguno (solo rutas de ejemplo ficticias en pruebas).
* Textos visibles fuera de `recorder/ayuda.py` (pendiente, no trivial de mover): `pantallas/opciones.py` («No se guarda…», «Guardado en…»),
  `pantallas/terminal.py` («No se pudo detectar el entorno…», «Tema cambiado solo…», «Tema … guardado…», prefijos de aviso),
  `pantallas/inicio.py` («(solo Windows)», «no se puede aquí»), `pantallas/base.py` («aún no hay…»),
  `live.py` («(Ctrl+C también sale)», «Grabación terminada», «se perdieron…», «Quedan … sin transcribir», «releer ventanas»,
  «no se pudo abrir la nota»). Los del menú de línea (`calibrar.py`, `configurar.py`) son anteriores y fijados por `tests/test_cli_*.py`.

## 5. Pruebas

Tras las correcciones: `python -m pytest` 1048 passed, 1 skipped, 624 subtests passed; `python recorder.py --selftest` ok.

## 6. Sin verificar

* **Recorrido de uso real con grabación** (menú → grabar → RePág → [m] → [o] → salir → vuelta al Inicio con el resumen → historial de
  PowerShell): no se hizo con audio real (ver el fallo 6). Hacerlo a mano con el equipo en silencio.
* **Ctrl+C con el teclado físico** (en la grabación, en una pregunta de modo línea, en cada pantalla): sin verificar.
* **Windows Terminal y PowerShell 7:** no están instalados. **Linux/WSL:** solo hay `docker-desktop`, ninguna distribución.
* **Pantallas sobre el azul #012456 del acceso directo de PowerShell:** el azul se imitó (OSC 4 y `color 53`), pero la pantalla
  alternativa se pinta sobre el fondo por defecto del búfer (negro, píxel 12,12,12 en `inicio-ascii-azul/01_inicio.png`); solo el
  prompt posterior se ve sobre el azul (1,36,86). Falta comprobar a mano en el acceso directo real, sobre todo con `--ascii` (16 colores).
* **Tema claro y oscuro en PowerShell/cmd:** verificado en cmd y PowerShell con los capturadores; `[t]` en vivo no se ejercitó.
* **Prueba manual con la función `daily` del perfil**: se usó `powershell.exe -NoProfile` con las mismas variables, no el perfil real.
