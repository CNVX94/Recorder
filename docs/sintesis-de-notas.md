# Síntesis de notas

Cómo Recorder convierte una transcripción cruda en una nota manejable, y por qué nunca toca el
archivo original.

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
daily_2026-09-08_10-20.md                     <- original, intocable
daily_2026-09-08_10-20_sintesis.md            <- solo limpieza, sin agrupar
daily_2026-09-08_10-20_sintesis-15min.md      <- tramos de 15 minutos
daily_2026-09-08_10-20_sintesis-1h.md         <- tramos de una hora
daily_2026-09-08_10-20_sintesis-1h (2).md     <- segunda versión, la anterior se conserva
```

Van en la misma carpeta a propósito. Las capturas se referencian con rutas relativas
(`capturas/…png`); moverlas a una subcarpeta rompería todas esas rutas.

El sufijo nombra el agrupamiento, que es la decisión principal. Si el archivo ya existe **no se
sobrescribe**: se numera. Así puedes generar dos versiones con la misma agrupación y distinta
limpieza sin perder ninguna.

La palabra `_sintesis` en el nombre es además lo que hace que el selector no ofrezca derivar desde
una síntesis.

---

## 4. Qué hace cada transformación

| Transformación | Qué hace | Detalle que importa |
| :--- | :--- | :--- |
| **Agrupar** | Junta las entradas en tramos de reloj: 5, 15, 30 o 60 minutos. Cada tramo recibe una cabecera `## 10:00 - 10:30`. | Al agrupar, las marcas por línea desaparecen. Es lo que reduce el ruido de números. |
| **Unir** | Fusiona líneas seguidas del mismo hablante en un párrafo. | Solo une si el hueco entre ellas es menor de 45 segundos y el párrafo no pasa de 600 caracteres. |
| **Descartar cortas** | Elimina las líneas de menos de cuatro palabras. | Nunca descarta una línea que lleve captura ni un marcador de pausa. |
| **Quitar capturas** | Elimina las imágenes incrustadas. | Solo afecta a las referencias; el texto queda igual. |

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

---

## 7. La interfaz

El botón **📑 Síntesis** de la cabecera abre el diálogo. Su diseño se trabajó en un canvas aparte:
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
* La casilla de quitar marcas de tiempo **se desactiva sola** cuando eliges «Sin agrupar»: ahí la
  marca es lo único que ordena las líneas.

