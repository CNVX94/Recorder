# Síntesis de notas (reagrupar)

Cómo Recorder convierte una transcripción cruda en una nota manejable, y por qué nunca toca el
archivo original.

> **Desde el 25-SEP-2026 se llama «reagrupar», no «síntesis».** Una copia `…_sintesis-1h.md` de una
> daily de 2 h 39 min tenía los mismos 829 enunciados palabra por palabra (16 925 palabras frente a
> 16 915 del original: 0 % de reducción) y se leyó como si fuera un resumen. No lo es ni lo
> pretende: ordena, agrupa y limpia. Ahora el nombre lo dice (`…_reagrupada-1h.md`), la cabecera
> lo dice con las cifras (`17 007 palabras en el original, 16 914 aquí (1 % menos)`) y el botón es
> **📑 Reagrupar**. Un resumen de verdad (decisiones, tareas, fechas) es otro proyecto: ver la
> sección 8. El resto de este documento conserva el término «síntesis» donde describe la historia.

---

## 1. El problema

Una transcripción en vivo es correcta pero inmanejable. Una reunión real de este proyecto produjo:

| Medida | Valor |
| :--- | ---: |
| Tamaño del archivo | 102 KB |
| Líneas de transcripción | 908 |
| Capturas incrustadas | 195 |
| Líneas de menos de cuatro palabras | 80 |

Esas 80 líneas cortas son relleno de conversación: *"Sí, sí, sí."*, *"A ver."*, *"MBC."*. Cada una
ocupa su propia línea con su marca de tiempo al segundo. El contenido está, pero leerlo cuesta más
que haber estado en la reunión.

---

## 2. La regla que ordena todo el módulo

> **El original es inmutable. Toda síntesis es un archivo nuevo.**

No es una convención, es una restricción del código. El módulo abre el original solo en lectura, y
la escritura comprueba que el destino no coincida con el origen antes de tocar el disco. Hay una
prueba que calcula el hash del original, genera tres síntesis distintas y verifica que el hash no
cambió.

La razón es que **agrupar pierde información y no se puede deshacer**. Una nota agrupada por hora ya
no contiene las marcas al segundo, así que no hay manera de volver a partirla por minutos. Si el
original fuera editable, la primera síntesis destruiría para siempre la posibilidad de hacer otra
distinta.

De ahí salen dos comportamientos concretos:

* Cada síntesis guarda en su cabecera de qué original salió, cuándo se generó y con qué opciones.
* El módulo **se niega a derivar desde otra síntesis**. Si lo intentas, el error te dice el nombre
  del original al que debes volver.

---

## 3. Nombres de archivo

La síntesis se escribe junto al original, con un sufijo que describe la transformación:

```
daily_2026-09-08_10-20.md                       <- original, intocable
daily_2026-09-08_10-20_reagrupada.md            <- solo limpieza, sin agrupar
daily_2026-09-08_10-20_reagrupada-15min.md      <- tramos de 15 minutos
daily_2026-09-08_10-20_reagrupada-1h.md         <- tramos de una hora
daily_2026-09-08_10-20_reagrupada-1h (2).md     <- segunda versión, la anterior se conserva
```

Los archivos con el sufijo antiguo `_sintesis` se siguen reconociendo como derivados: no aparecen
en la lista de originales y no se puede derivar de ellos.

Van en la misma carpeta a propósito. Las capturas se referencian con rutas relativas
(`capturas/…png`); moverlas a una subcarpeta rompería todas esas rutas.

El sufijo nombra el agrupamiento, que es la decisión principal. Si el archivo ya existe **no se
sobrescribe**: se numera. Así puedes generar dos versiones con la misma agrupación y distinta
limpieza sin perder ninguna.

La palabra `_reagrupada` (o la antigua `_sintesis`) en el nombre es además lo que hace que el
selector no ofrezca derivar desde una copia.

---

## 4. Qué hace cada transformación

| Transformación | Qué hace | Detalle que importa |
| :--- | :--- | :--- |
| **Ordenar** | Pone las entradas en orden de hora (siempre, antes que nada). | La nota se escribe en orden de *transcripción*: con cola, una frase de las 17:53:06 quedaba después de la pausa de las 17:53:25. La ordenación es estable y respeta la medianoche. |
| **Agrupar** | Junta las entradas en tramos de reloj: 5, 15, 30 o 60 minutos. Cada tramo recibe una cabecera `## 10:00 - 10:30`. | Cada párrafo conserva su hora corta `[10:07]` (o `**10:07:31**` si se desmarca la casilla): sin ella, un tramo de una hora no dice cuándo se dijo nada. Un tramo con solo marcadores (pausas, avisos) no se crea: sus marcadores van al tramo anterior. |
| **Unir** | Fusiona líneas seguidas del mismo hablante en un párrafo. | Solo une si el hueco entre ellas es menor de 45 segundos y el párrafo no pasa de 600 caracteres. |
| **Descartar cortas** | Elimina las líneas de menos de cuatro palabras. Activada por defecto. | Nunca descarta una línea que lleve captura ni un marcador. |
| **Quitar ecos** | Quita el eco del vocabulario (`Términos.`, listas de nombres del `vocab`) con el mismo filtro que el transcriptor. Activada por defecto. | Sirve para notas grabadas antes de que existiera el filtro. Nunca descarta una línea con captura. |
| **Quitar referencias de imagen (texto puro)** | Elimina las imágenes y todo su rastro: la línea `📸 \`clave\` → ![](…)`, el `· tardía` y las entradas de captura manual. **Activada por defecto** desde el 25-SEP-2026. | El texto hablado queda igual. Se aplica antes de descartar: una línea corta o de eco que solo se salvaba por llevar captura ya no se salva. |

Los marcadores que se conservan son los que escribe la app: `⏸`/`▶` (pausa), `⏳`/`✔` (atraso de la
transcripción y vuelta al día) y `⚠` (fuente caída o muda, fragmento lento).

### Sobre "quitar números"

El módulo normaliza **el andamiaje de marcas de tiempo**, no el contenido. Los números del texto
transcrito (puertos, versiones, kilos, números de pedido) no se tocan nunca. En un daily técnico
esos números suelen ser justo la información que hay que conservar, así que borrarlos sería destruir
el motivo de grabar la reunión.

### Por qué unir tiene límite de tiempo

La primera versión unía todas las líneas seguidas del mismo hablante dentro del tramo. Con datos
reales el resultado fue un solo párrafo de media hora, con las 195 capturas apiladas al final,
desancladas del momento en que se tomaron. Era menos legible que el original.

El límite de 45 segundos hace que "seguidas" signifique *el mismo turno de habla*, no *el mismo
tramo de reloj*. Y una línea con captura nunca se funde con su vecina, de modo que cada imagen queda
pegada al texto que la disparó.

---

## 5. Estructura del módulo

```
recorder/digest/
├── parser.py      # Markdown -> estructura. Solo lectura, nunca escribe.
├── transforms.py  # Funciones puras sobre las entradas. No tocan el disco.
└── writer.py      # Genera el Markdown y escribe el clon, con las salvaguardas.
```

Sigue la misma regla que el resto del proyecto: las políticas son funciones puras, así que se
prueban sin audio, sin archivos y sin interfaz. La suite cubre el parseo del formato real, cada
transformación por separado, y las dos salvaguardas críticas.

---

## 6. Resultado sobre datos reales

Partiendo de la misma nota de 102 KB y 1119 líneas de Markdown:

| Configuración | Líneas | Legibilidad |
| :--- | ---: | :--- |
| Original | 1119 | Un fragmento por línea, con marca al segundo |
| Tramos de 30 min | 695 | Párrafos por turno de habla, cabecera por media hora |
| Tramos de 30 min, sin relleno bajo cuatro palabras | 675 | Igual, sin muletillas |
| Tramos de 60 min, sin relleno ni capturas | 207 | Solo el hilo de la conversación |

El original sigue intacto en los cuatro casos. Puedes borrar cualquier síntesis y regenerarla, o
generar una distinta, siempre partiendo de él.

Ojo con leer esas cifras como reducción: bajan **líneas de Markdown**, no palabras. Sobre la daily
del 25-SEP-2026 (829 enunciados), tramos de 60 min + unir + descartar cortas + quitar ecos dejan
444 párrafos, todos con su `[HH:MM]`, sin tramos vacíos y en orden de hora, pero el 99 % de las
palabras (16 914 de 17 007). Medido en local sobre la nota real; la nota no está en el repositorio.

---

## 7. La interfaz

El botón **📑 Reagrupar** de la cabecera abre el diálogo. Su diseño se trabajó en un canvas aparte:
<https://claude.ai/code/artifact/3d2261c1-ceae-4b97-b9b1-0af9c3731678>

Decisiones que conviene conocer:

* **La nota origen se elige en una lista**, no en un desplegable, para poder ver fecha, hora y
  tamaño de un vistazo. La nota que la aplicación está escribiendo en ese momento se marca como
  «en curso». Una insignia «🔒 SOLO LECTURA» acompaña a la sección.
* **El agrupamiento es la decisión principal** y va en su propia caja, con una pista debajo que
  explica qué produce cada opción.
* **La vista previa se recalcula al tocar cualquier opción** y colorea los encabezados, la
  procedencia y las referencias a imágenes. El botón «Ampliar» la agranda para revisar más texto.
* **El aviso de pérdida va justo antes del nombre del archivo de salida**, que es lo último que se
  lee antes de pulsar Generar.
* La casilla de la hora corta **se desactiva sola** cuando eliges «Sin agrupar»: ahí la marca
  completa es lo único que ordena las líneas.
* Desde el 25-SEP-2026 «Descartar líneas de menos de 4 palabras», «Quitar el eco del vocabulario» y
  «Quitar referencias de imagen (texto puro)» vienen **marcadas por defecto**: la copia por defecto
  es texto limpio para leer o pegar en otro sitio; las imágenes siguen en la nota original. La
  casilla de marcas pasó a significar «hora corta `[HH:MM]` por párrafo» en lugar de quitarlas.
  Las cifras de la vista previa dicen cuántas palabras habladas quedan (`24 → 22 palabras`), las
  mismas que la cabecera de la copia.

### La misma cosa en la terminal: `daily sintesis`

La ventana y el comando comparten la lógica y los valores por defecto (`digest/preview.py`):
`daily sintesis` lista las notas originales, pregunta el agrupamiento y las mismas casillas, en el
mismo orden y con las mismas respuestas por defecto (Enter deja lo que la ventana trae marcado), y
enseña las cifras y el principio de la vista previa antes de confirmar. Para scripts, con la nota y
`--si` no pregunta nada y produce exactamente lo que produciría la ventana con sus casillas por
defecto; las banderas invierten una casilla cada una:

```
daily sintesis nota.md --cada 60 --si               # tramos de una hora; texto puro, sin cortas, sin ecos
daily sintesis nota.md --si --con-imagenes          # conserva las referencias de imagen
daily sintesis nota.md --si --con-cortas --con-ecos # conserva las líneas cortas y el eco del vocabulario
daily sintesis nota.md --si --con-horas --sin-unir  # HH:MM:SS por línea y sin unir párrafos
```

El eco se reconoce con el `vocab` del `config.json` en uso, como en la ventana. Las copias con el
sufijo antiguo `_sintesis` siguen sin listarse y sin servir de origen.

---

## 8. Un resumen de verdad: propuesta, no implementada

Reagrupar nunca va a responder «¿qué se decidió?». Eso exige leer y abstraer, y hay dos caminos
compatibles con `docs/stt-nube-y-privacidad.md` (el contenido es interno: nada de APIs públicas):

1. **Extracción local por reglas (barata, primero).** Una función pura que marque como
   *candidatos* los párrafos con fechas y plazos («el viernes», «para mañana», «15 de octubre»),
   compromisos («hay que», «queda», «me encargo», «pendiente») y decisiones («quedamos en», «se
   decidió»), cada uno con su `[HH:MM]` y enlace a su captura. No resume: señala dónde mirar, con
   precisión medible contra una nota escrita a mano.
2. **Modelo de lenguaje local**, solo si el paso 1 se queda corto: un modelo pequeño cuantizado
   (3-4 B parámetros) con `llama.cpp` en esta misma CPU, tramo a tramo. **Sin medir**: habría que
   comprobar primero velocidad y calidad en el i7-1255U con una transcripción sintética; una daily
   de 2 h 39 min son unas 17 000 palabras.

Queda descartado mandar la transcripción a un modelo en la nube por el mismo motivo por el que se
descartó mandar el audio. La vía con menos exposición sigue siendo la transcripción nativa de Teams
(con su resumen dentro del inquilino de Microsoft 365), si TI la habilita.

