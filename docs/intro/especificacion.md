# Introducción de Recorder: especificación

Acompaña al [storyboard](README.md). Aquí está el porqué y el cómo; **los valores viven en
[`recorder/assets/intro/intro.json`](../../recorder/assets/intro/intro.json)** (el contrato). El
código lee de ahí cada tiempo, medida, token de color y clave de texto: no hay nada que copiar a
mano de este documento. Si una cifra de aquí y el contrato discrepan, manda el contrato.

## 1. Qué se puede usar

Se reproduce en Tkinter, así que el diseño solo usa:

| Recurso | Dónde se usa |
| :--- | :--- |
| Secuencia de fotogramas PNG con transparencia | Revelado del logotipo |
| Texto de Canvas | Rótulo, títulos, subtítulos, botón, pista |
| Rectángulos y líneas de Canvas, cambiando coordenadas | Barras, líneas, portátil, nota, captura, botón |
| Fundido de color: mezcla entre el color del fondo y el del token (`animacion.mezclar`) | Toda aparición y desaparición de texto y formas |
| Transparencia de la ventana (`-alpha`) | Solo la entrada y la salida de la ventana |

No hay vídeo, ni escalado o giro de imágenes en vivo, ni transparencia por elemento: un «fundido»
de un texto o una forma es siempre su color yendo hacia el del fondo, y por eso todo se dibuja
directamente sobre el fondo liso de la ventana (`lienzo.color`).

`generar_vistas.py` es un reproductor de referencia que se ciñe a esa lista: lo que dibuja a
partir del contrato es lo que debe verse en la app.

## 2. Lienzo y piezas

Ventana sin bordes, centrada, de `lienzo.ancho` × `lienzo.alto` unidades de diseño (se escalan con
la pantalla como el resto de ventanas). Todo color es un token de `recorder/paleta.py`, así que la
introducción sigue al tema activo (claro, oscuro o sistema) sin variantes propias.

| Pieza | En el contrato | Color (token) |
| :--- | :--- | :--- |
| Fondo | `lienzo` | `fondo` |
| Logotipo | `logotipo`: lado en pantalla, centro inicial y final | fotogramas (ver §6) |
| Rótulo «Recorder» | `tipografia.rotulo`, `disposicion.rotulo` | `texto` |
| Título | `tipografia.titulo`, `disposicion.titulo` | `texto` |
| Subtítulo | `tipografia.subtitulo`, `disposicion.subtitulo` | `texto_tenue` |
| Barras de audio | `ilustracion.onda` | `mic` |
| Líneas transcritas | `ilustracion.lineas` | `texto_tenue`; la palabra clave, `acento` |
| Portátil (pantalla y base) | `ilustracion.equipo` | `borde` |
| Nota | `ilustracion.nota` | marca `acento`, título `texto`, párrafos `texto_tenue` |
| Miniatura de captura | `ilustracion.captura` | `superficie`, `borde`, franja `seleccion` |
| Botón «Saltar» | `boton.secundario` | `superficie`, `texto`, `borde` |
| Botón «Comenzar» | `boton.principal` | `acento`, `texto_sobre_acento` |
| Anillo de foco del botón | `boton.anillo_foco` | `foco` |
| Pista de teclas | `tipografia.pista`, `disposicion.pista` | `texto_tenue` |

Tipografía: `tipografia.familias` por orden de preferencia (Segoe UI Variable; si no está, Segoe
UI). Los títulos caben en una línea en el ancho de su columna; `generar_vistas.py` falla si alguno
deja de caber.

Los textos se nombran por clave (`intro.graba.titulo`…). El texto exacto de cada clave está en
`recorder/ayuda.py` (`INTRO`).

## 3. Movimiento

### Duraciones con nombre (`duraciones_ms`)

| Nombre | Para qué | Valor |
| :--- | :--- | :-: |
| `total` | Toda la introducción | 7 500 ms |
| `entrada_rotulo` | Fundido de entrada de «Recorder» | 400 ms |
| `cruce_escena` | Salida del texto anterior al cambiar de escena; salida del rótulo | 250 ms |
| `fundido_texto` | Entrada de un título o subtítulo | 300 ms |
| `escalonado_texto` | Retraso del subtítulo respecto al título | 120 ms |
| `desplazamiento_logo` | El logotipo va del centro a la izquierda | 450 ms |
| `fundido_forma` | Entrada o salida de una forma; cambio de color de las líneas | 300 ms |
| `onda_periodo` | Un latido completo de una barra | 800 ms |
| `onda_a_texto` | Una barra se convierte en tramo de línea | 450 ms |
| `escalonado_trazo` | Retraso entre una barra y la siguiente al convertirse | 20 ms |
| `escalonado_linea` | Retraso entre filas al cambiar de color | 150 ms |
| `reordenar_nota` | Las líneas se recolocan como nota | 400 ms |
| `boton_cambio` | «Saltar» pasa a «Comenzar» | 300 ms |

La entrada y la salida de la ventana no tienen duración propia: son las de siempre
(`animacion.ENTRADA_MS` y `animacion.SALIDA_MS`).

### Curvas (`curvas`)

| Nombre | Comportamiento | Se usa en |
| :--- | :--- | :--- |
| `ease_out` | Arranca rápido y frena al final. Es la de `recorder/ui/animacion.py` | Fundidos, giro del logotipo |
| `ease_in_out` | Arranca y frena suave | Lo que cambia de sitio: logotipo, barras, nota |
| `lineal` | Velocidad constante | Reservada; hoy no se usa |

El revelado del logotipo trae sus curvas ya horneadas en los fotogramas
(`docs/intro/blender/ritmo.py`): giro con ease-out; micrófono y punto con ease-out con rebote.

### Pasos de cada escena (`escenas[].pasos`)

Cada paso dice elemento, acción, cuándo empieza dentro de su escena, qué duración con nombre usa y
con qué curva. Las acciones:

| Acción | Qué hace |
| :--- | :--- |
| `reproducir` | Muestra los fotogramas del logotipo a `logotipo.fps`; al acabar se queda en el último |
| `desplazar` | Mueve el logotipo de `centro_inicial` a `centro_final` |
| `fundido_entrada` / `fundido_salida` | El color va del fondo al token, o al revés |
| `fundido_cruzado` | En dos tiempos sobre el mismo sitio: el texto anterior se va (`cruce_escena`) y después entra el nuevo (`fundido_texto`). Nunca hay dos textos a la vez |
| `convertir_en_lineas` | Cada barra pasa de su rectángulo vertical a su tramo de línea, con `escalonado_trazo` entre una y la siguiente |
| `teñir` | Las líneas pasan del color de la onda al suyo, con `escalonado_linea` entre filas |
| `reordenar_en_nota` | Cada tramo va de su sitio en las líneas a su sitio en la nota, y a su color de nota |
| `pasar_a_principal` | El botón mezcla sus colores de secundario a principal; el rótulo cambia a mitad del recorrido |

El latido de las barras, mientras son barras: la altura de la barra *i* va de `alto_min` a
`alto_max × envolvente[i]` siguiendo un seno de periodo `onda_periodo`, desfasado `desfase_rad`
por barra.

Si un tic llega tarde, la animación salta adelante (el avance sale del reloj, como en
`animacion.animar`): la introducción dura lo mismo en un equipo lento.

### Movimiento reducido (`movimiento`)

Lo decide `animations` de `config.json`:

| Valor | Qué se ve |
| :--- | :--- |
| `completas` | Lo descrito arriba |
| `reducidas` | **Solo fundidos**, cada uno con el techo de `animacion.CORTO_MS`. El logotipo es `logotipo.estatico`, colocado en `centro_final` desde el principio (no hay revelado ni desplazamiento, y el rótulo «Recorder» no sale). Las barras se muestran quietas a media altura; cada cambio de escena lleva la ilustración a su estado final por fundido (barras → líneas → nota), sin recorrido y sin escalonado. Los tiempos de inicio de cada escena no cambian |
| `ninguna` | No hay introducción animada |

## 4. Accesibilidad

| Requisito | Cómo se cumple |
| :--- | :--- |
| Se puede saltar desde el primer fotograma | El botón «Saltar» y la pista de teclas se dibujan antes de empezar el revelado y no se mueven ni se funden nunca |
| Esc, Enter, Espacio y clic saltan | Saltar y terminar son lo mismo: fundido de salida y ventana principal. Enter y Espacio activan el botón, diga «Saltar» o «Comenzar» |
| Foco visible | El botón tiene el foco desde el principio, con anillo en el token `foco` |
| Nada destella más de 3 veces por segundo | No hay destellos: ningún elemento se enciende y apaga. Lo único cíclico son las barras, que cambian de altura (no de brillo) a 1,25 ciclos por segundo durante medio segundo. El punto de grabación se enciende una vez y se queda |
| Contraste AA en los textos | Todos los pares texto/fondo usados están en `paleta.PARES` y los mide `tests/test_paleta.py`: `texto` y `texto_tenue` sobre `fondo`, `texto` sobre `superficie` (botón «Saltar»), `texto_sobre_acento` sobre `acento` (botón «Comenzar»). El borde del botón y el anillo de foco, 3:1 |
| El color no es la única señal | El botón cambia de rótulo además de color |
| Movimiento reducido | §3 |
| Tiempo de lectura | El mensaje de cada escena es su título (de 3 a 6 palabras), que está en pantalla al menos 1,2 s. El subtítulo es apoyo, de 8 palabras como mucho. Quien no llegue a leerlo puede repetir la introducción desde el menú «Más» → «Ver introducción» |

## 5. Terminal

Un logotipo de `terminal.duracion_ms` (0,9 s) en el primer `daily`, saltable con cualquier tecla.
Nueve líneas (dos de ellas en blanco, de respiro) y 57 columnas como mucho: cabe en una consola de
60.

**Tres juegos de símbolos**, uno por archivo (`terminal.juegos`); se elige con el juego activo de
`recorder/cli/consola.py`:

| Juego | Archivo | Caracteres del dibujo |
| :--- | :--- | :--- |
| completo | `terminal/completo.txt` | `█ ▄ ▀ ●` |
| consola | `terminal/consola.txt` | `█ ─ ●`: solo los verificados en la consola clásica con Consolas (`docs/plan-pulido-terminal.md` §1). Sin emoji, sin `▶`, sin medios bloques |
| ASCII | `terminal/ascii.txt` | `# \| \ / _ - *` |

Los archivos llevan marcado de rich **por papeles** (`[capsula]`, `[soporte]`, `[punto]`,
`[nombre]`, `[lema]`) y el hueco `{lema}` para el texto `intro.terminal.lema`. El contrato dice con
qué estilo de la consola se pinta cada papel en cada paso (`terminal.pasos`):

| Paso | Empieza | Qué cambia |
| :-: | :-: | :--- |
| 1 | 0 ms | Micrófono (`mic`) y soporte (`acento`); el punto, apagado (`tenue`); nombre y lema ocultos (se imprimen como espacios) |
| 2 | 250 ms | Aparecen «Recorder» (`bold acento`) y el lema (`tenue`) |
| 3 | 500 ms | El punto se enciende (`bold error`); se queda así hasta los 900 ms |

Son tres repintados en 0,9 s y solo el último cambia un carácter: nada destella. Con movimiento
reducido, o si la salida no es una terminal interactiva, se imprime una sola vez el paso 3. Al
terminar queda impreso el paso 3 y el cursor en la línea siguiente.

**Contraste** de cada estilo usado, con el tema oscuro, sobre los dos fondos de consola
(`python docs\intro\generar_vistas.py --contraste`):

| Estilo | Negro | Azul de PowerShell |
| :--- | :-: | :-: |
| `acento` | 16,5:1 | 11,9:1 |
| `error` | 9,1:1 | 6,5:1 |
| `mic` | 10,0:1 | 7,2:1 |
| `tenue` | 9,4:1 | 6,8:1 |

Todos pasan AA (4,5:1) en los dos. En ASCII sin color el dibujo se sigue leyendo: la forma no
depende del color.

Las vistas de `img/terminal-*.png` son una simulación con las fuentes Consolas y Cascadia Mono, no
capturas de una consola: **queda por comprobar en la consola real** al integrarlo.

## 6. Logotipo 3D y assets

| Dato | Valor |
| :--- | :--- |
| Fotogramas | 36, a 24 fps (1,5 s) |
| Tamaño | 480 × 480 px, fondo transparente |
| Formato | PNG de paleta (256 entradas) con transparencia |
| Variantes | Una sola para los dos temas: la baldosa oscura del icono hace de fondo propio y contrasta con `fondo` en claro y en oscuro |
| Reserva | `logo_estatico.png`: el último fotograma. Es también el logotipo de «movimiento reducido» |
| Peso | 1 798 KB en total (presupuesto: 3 MB) |

El lado en pantalla es `logotipo.lado` unidades de diseño; los fotogramas tienen el doble de
píxeles (`logotipo.lado_px`), así que se reducen al cargar y aguantan hasta el 200 % de escala sin
ampliar. Reducir una vez al cargar, no en cada fotograma.

Los colores del modelo son los tokens del tema oscuro, igual que el icono: baldosa `fondo`,
soporte `acento`, cápsula `mic`, rejilla `fondo`, punto `error`. La geometría es la de
`packaging/generar_icono.py`, y la cámara es ortográfica y frontal para que el último fotograma
coincida con el icono.

### Cómo se regenera

Hace falta Blender 5.2 (probado con 5.2.1 LTS) y Python con Pillow. Desde la raíz del repositorio:

```powershell
$bruto = "$env:TEMP\recorder-intro-bruto"
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P docs\intro\blender\escena_logotipo.py -- $bruto
python docs\intro\blender\preparar_assets.py $bruto
python docs\intro\generar_vistas.py
```

| Archivo | Qué hace |
| :--- | :--- |
| `docs/intro/blender/ritmo.py` | Fotogramas, fps y tramos del revelado, con sus curvas |
| `docs/intro/blender/escena_logotipo.py` | Construye la escena desde cero en Blender (no abre ni modifica ningún otro archivo), la guarda y renderiza los 36 fotogramas en bruto (~6 MB) |
| `docs/intro/blender/logotipo_recorder.blend` | La escena guardada (191 KB; por debajo de los 5 MB, se queda en el repositorio) |
| `docs/intro/blender/preparar_assets.py` | Reduce cada fotograma a PNG de paleta, escribe el estático y comprueba el presupuesto y que la secuencia coincide con el contrato |
| `docs/intro/generar_vistas.py` | Miniaturas, tira del logotipo, terminal y vistas animadas de `docs/intro/img/` |

## 7. Para quien lo integre

* Si falta `recorder/assets/intro/` o alguno de sus fotogramas, la introducción se omite sin error.
* Saltar a mitad cancela todo lo pendiente y va directo al fundido de salida.
* La ventana principal no debe verse hasta que acabe ese fundido.
* Los textos viven en `recorder/ayuda.py` (`INTRO`), con las claves del contrato, que ya no los
  lleva; `generar_vistas.py` los toma de ahí.
* Duración real a medir en la app: 7,5 s más `animacion.ENTRADA_MS` y `animacion.SALIDA_MS`.

### Cómo quedó integrada

| Pieza | Dónde |
| :--- | :--- |
| Contrato, guion (`Guion.estado(t)`), cuándo sale y `intro_seen` | `recorder/intro.py` (sin tkinter ni rich) |
| Ventana: Toplevel sin bordes con un Canvas, un tic por reloj | `recorder/ui/intro.py` |
| Logotipo de terminal: tres repintados con el cursor | `recorder/cli/intro.py` |
| Primera vez | `intro_seen` (ventana) e `intro_terminal_seen` (terminal) en `config.json`; un config.json anterior carga como «no vista» y la intro sale una vez |
| Bajo demanda | «Más» → «Ver introducción» |
| Omitirla | `--sin-intro` (también en `Recorder.exe`); con `animations: ninguna` no hay |

* La sesión (audio y modelo) arranca en el constructor de la ventana principal, antes de la
  introducción: la introducción es una ventana más del mismo bucle de Tk, con la principal retirada
  hasta que acaba. No retrasa la grabación y PortAudio sigue en el hilo principal.
* Los 36 fotogramas se reducen al abrir (~0,5 s con 100 % de escala); con «reducidas» solo se carga
  el estático.
