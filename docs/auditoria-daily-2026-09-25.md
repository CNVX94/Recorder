# Auditoría de la daily del 25-SEP-2026 y lo que se cambió

Una daily real de 2 h 39 min (829 renglones, ~17 000 palabras) se auditó contra una nota escrita a
mano. La base es buena: 40 de 41 enunciados de una muestra sistemática conservan el sentido, 33 de
41 salen sin error de palabra, y cifras y fechas salieron exactas. Este documento recoge los cinco
defectos que aparecieron, **qué se midió, qué se cambió y qué no se pudo verificar**. La nota
original tiene datos de un cliente y **no está en el repositorio**: todo lo que se cita de ella son
recuentos, y las pruebas usan textos sintéticos con la misma forma.

Lo importante primero:

* **Capturas perdidas:** no se pudo establecer la causa. La nota del 25-SEP y la del 22-SEP enlazan
  212 y 269 capturas que no existen en ningún sitio del disco. Desde ahora el enlace solo se
  escribe si el archivo existe, y mover la carpeta de notas reescribe los enlaces.
* **Capturas tardías:** llegaban 11-31 s tarde y, tras un atasco, 54 min tarde. Se implementó el buffer
  circular de `docs/captura-diferida.md`. En la reunión de prueba, 5 de 6 capturas quedaron a
  ±0,2 s de la palabra; la sexta, a 9 s, porque a ese fragmento le faltaba audio.
* **"Términos" que nadie dijo:** es eco del vocabulario. El mecanismo se reprodujo con Whisper, pero
  el rótulo concreto no. Hay un filtro nuevo, y el vocabulario se reescribió sin rótulos.
* **Micrófono mudo:** el micrófono configurado está vivo, pero en silencio solo recoge ruido. Ahora
  la nota dice qué dispositivo usa cada fuente y avisa si una lleva 10 min sin dar fragmentos
  mientras la otra sí.
* **La "síntesis" no resumía:** ahora se llama *reagrupada*, la cabecera lo dice con cifras y los
  párrafos conservan su hora.

> **Dónde quedó cada cambio tras la integración** (la auditoría se hizo sobre la ventana de antes;
> después el núcleo pasó a `recorder/session.py` y apareció el modo terminal `daily`):
>
> * Lo que era lógica de la ventana vive en `RecorderSession`: la línea `> Fuentes:` al arrancar (y un
>   aviso en el visor), el aviso de fuente muda (`SourceMuted`, con `🔇` en `status.meter_text`), el
>   buffer de capturas (arranque, rearranque desde Opciones y vaciado al cerrar) y la señal de
>   «hay reunión» por fragmentos. La ventana y la terminal solo pintan; las dos muestran lo mismo.
> * Los diálogos usan los módulos puros: `captures` en `config/options.py` (`SettingsForm.captures`),
>   el eco en el sandbox en `filters/tuning.py` (`test_phrase`), y las casillas de «Reagrupar» con sus
>   valores por defecto en `digest/preview.py` (`digest_options`).
> * La terminal tiene paridad: `daily config` pregunta la calidad de las capturas, `daily calibrar`
>   marca el eco y avisa de los rótulos, y `daily sintesis` propone lo mismo que la ventana (texto
>   puro, sin ecos) con banderas `--con-imagenes`, `--sin-cortas`, `--con-ecos`.
> * Las pruebas de la ventana pasaron a la sesión (`tests/test_session.py`: `TestFuentes`,
>   `TestFuenteMuda`, `TestBufferDeCapturas`) y hay pruebas de paridad en `tests/test_cli_live.py`,
>   `tests/test_cli_configurar.py`, `tests/test_cli_calibrar.py` y `tests/test_cli_sintesis.py`.
>
> **Lo que la evaluación de la rama corrigió después** (14-OCT-2026): el filtro de eco se llevaba
> frases reales («Términos del contrato firmados ayer», «Ana y Luis», «QA e IIS») y quitaba rótulos
> que no estaban en el vocabulario; ahora solo actúa a partir del `vocab` configurado, con reglas
> mucho más estrictas para descartar un renglón entero, y se puede apagar (`echo_filter`, sección D de
> `docs/anti-hallucination-tuning.md`). La calidad `normal` del buffer pasa a JPEG 85 sin submuestreo
> de color (el primer buffer era JPEG 70 4:2:0, peor que el PNG de siempre; `high` sigue siendo PNG) y
> `light` reduce con LANCZOS. El buffer no guarda nada hasta el primer audio, borra lo más viejo que
> 15 min también sin reunión y avisa en la nota y el visor de su primer fallo. «Descartar líneas
> cortas» ya no viene marcado (se llevaba decisiones como «Sí, va.»). El aviso de fuente sin audio es
> neutro («sin audio de micrófono desde hace 10 min (¿silenciado?)»), continuar tras una pausa no
> reinicia el reloj de la reunión y desactivar el micrófono con el aviso puesto no anuncia una vuelta.
> Cifras de disco y CPU medidas de nuevo en `docs/captura-diferida.md`.

---

## 1. Defectos, causa y cambio

| Defecto | Evidencia | Causa | Cambio |
| :--- | :--- | :--- | :--- |
| Nombres propios y siglas mal escritos | El nombre del cliente (una sigla) salió bien 0 de 18 veces, con 15 grafías distintas; también *nipple* por NIP, *IAJs* por IIS, *Cloudfire*, *botoken*… | Casi ninguno estaba en `vocab`. | `vocab` reescrito sin rótulos y con los términos que faltaban (en `config.json`, que no se sube). 19 reemplazos nuevos, solo de variantes inequívocas. **Verificado sobre la nota real:** normalizan 16 de 19 apariciones del nombre del cliente. |
| Renglones "Términos", "Nombres del equipo", nombres que no estaban en la junta | 15 renglones con "Términos", 2 con "Nombres del equipo", 3 con "Luis/Marta/Ana" | Eco del `initial_prompt` (ver sección 2) | `filters/echo.py`; `vocab` sin rótulos; "más información www" en la lista negra |
| Capturas enlazadas que no existen | 212 enlaces (25-SEP) y 269 (22-SEP), 0 archivos | **Desconocida** (sección 3) | Enlace solo si el archivo existe; `move_notes` reescribe los enlaces (`rebase_links`) |
| Capturas por la muletilla "este" | 60 de 212 capturas, 126 apariciones | "este" en `keywords` | `MULETILLAS` en `filters/keywords.py`: "este" se ignora aunque esté configurada |
| Capturas tardías; atasco de 54 min | Retraso de 11-31 s; en un renglón pasó de 25 s a 53 min 49 s | `take_screenshot` capturaba al terminar de transcribir; el atasco, **sin verificar** (sección 4) | Buffer circular (`actions/capture_buffer.py`); sonda `responsive()` antes de `PrintWindow`; marcadores de atraso y de paso lento |
| Ningún renglón 🎤 en 2 h 39 min | `mic: true` y el usuario habló | **Probable:** el micrófono configurado no es por el que habla el usuario (sección 5) | Línea `> Fuentes:` al arrancar; aviso de fuente muda (`mute_source`, desde `RecorderSession`), medidor 🔇 en la ventana y en el pie de la terminal |
| La síntesis no sintetiza | 16 925 palabras contra 16 915; tramo vacío `## 20:00 - 21:00`; una frase de 17:53:06 tras la pausa de 17:53:25 | Solo reagrupa; los marcadores creaban tramos; la nota está en orden de transcripción | Nombre `reagrupada`, cabecera honesta, `[HH:MM]` por párrafo, orden por hora, sin tramos de solo marcadores, "descartar cortas" y "quitar ecos" por defecto |

Reemplazos que **no** se añadieron, por ambiguos: *Cloud*, *Clau*, *Klaus* y *Claudio* por Claude;
*lápiz*, *apps* y *la pi* por API; *AXO*; *Cine*, *Sin Lab* y *decimla* por el nombre del cliente;
y *UPS* por UPC (UPS también es una paquetería). Todas son palabras reales, o pueden serlo: el
reemplazo rompería frases correctas. Se dejan al `vocab`.

---

## 2. Eco del vocabulario: qué se midió

**Hipótesis:** el `vocab` se pasa como `initial_prompt`, es decir, como el texto que se acaba de
decir. Ante audio pobre, Whisper continúa ese texto: repite sus rótulos o recita su lista. La
evidencia circunstancial es fuerte. Las secuencias "Nombres del equipo" y "Ana, Luis, Marta" (en
ese orden) solo existen en el `vocab` de `config.example.json`, y "Términos:" en el del usuario. Los
renglones se concentran entre 18:12 y 18:24, mientras el usuario llenaba una hoja de cálculo en
silencio.

**Experimento** (`faster-whisper` 1.2.1, `small` int8, beam 5, la misma llamada que el worker; 12 s por
señal, 3 semillas, 4 prompts: el del usuario con rótulos, el de ejemplo, uno nuevo sin rótulos y
ninguno):

| Señal | Con VAD (como la app) | Sin VAD |
| :--- | :--- | :--- |
| Silencio digital | 0 segmentos | 0 segmentos |
| Ruido blanco a −40 dBFS | 0 | "¡Suscríbete!", "Subtítulos por la comunidad de Amara.org" |
| Tecleo | 0 | Con el vocab nuevo: **"…, PWA, QA, IIS, QA, IIS, TPR, TP-Link, P8, NIP, PE, SKU, UPS, Mesa, …"**, la lista del prompt recitada, en 2 de 3 semillas |
| Murmullo (ruido filtrado con envolvente) | 0 | Amara.org, Suscríbete |

Conclusión honesta:

* **Reproducido:** Whisper recita el vocabulario sobre ruido. Todos estos segmentos traían
  `no_speech_prob` ≥ 0,69, así que el filtro de calidad (umbral 0,6) ya los habría descartado.
* **No reproducido:** el rótulo "Términos" en sí. Con VAD, estas señales sintéticas ni siquiera llegan
  al modelo; los ecos reales salieron de audio que el VAD tomó por voz y que pasó el filtro de
  calidad. Por eso hace falta un filtro de texto.

**El filtro sobre la nota real** (con el vocabulario del usuario más el de ejemplo, porque la sesión
mostró ecos de los dos) cambia 19 de 829 renglones: descarta 10 (los "Términos.", "Términos, ¿sabes?"
×3, "Nombres del equipo.", "Luis, Marta.", "Luis. Luis.") y quita el rótulo inicial en 9
("Términos crearon tres endpoints nuevos" → "Crearon tres endpoints nuevos"). Tras el filtro no
queda ningún renglón con "términos". En la revisión manual de los 19 no apareció ningún falso
positivo. Límite conocido: un eco pegado *antes* de una frase real con nombres ("Ana, Luis, Marta.
Pues sí, si quieres…") no se quita.

**Vocabulario nuevo:** 133 tokens frente a 91 (el límite de Whisper es 223). Sobre los 6 primeros
fragmentos de la muestra sintética (unos 2 min de audio limpio), el WER bruto sale 16,3 % con el
nuevo, 17,0 % con el anterior y 18,4 % sin vocabulario. Es una muestra pequeña y la alineación con el
guion es aproximada: **no es una medida de calidad**, solo muestra que el vocabulario nuevo no
degrada el audio limpio.

---

## 3. Capturas que no existen: lo que se sabe

* La nota del 25-SEP en la bóveda de Obsidian se **creó** a las 20:24:01 y su **última escritura** fue
  a las 20:03:44: es una copia hecha después de la reunión. El `.md` original no aparece en ningún
  sitio del disco `C:`: se buscó en todo el disco y en la papelera. Tampoco aparece ninguna de sus
  212 capturas.
* Los enlaces dicen `Capturas/…` con mayúscula. `md_ref` conserva las mayúsculas de `caps_dir`, y ni
  el `config.json` actual (`…\capturas`) ni el código producen esa ruta. La sesión corrió, por tanto,
  con **otra configuración**. Los ecos de "Nombres del equipo" y de "Ana, Luis, Marta" apuntan a lo
  mismo: ese texto es el vocabulario de `config.example.json`.
* La nota del 22-SEP (10:14) tiene 269 enlaces `Capturas/…` y ninguno existe. Las 9 capturas que sí
  hay de ese día en `Dailies\capturas` son de otra sesión, la de las 11:22, que enlaza en minúscula.

No se pudo reconstruir dónde se escribieron. Lo que el código sí puede evitar:

1. **Enlace sin archivo:** el worker comprueba `is_file()` antes de escribir el enlace; si no existe,
   anota `⚠ captura no guardada` (probado).
2. **Mover la nota sin sus capturas:** `NotesSession.move_notes` movía el `.md` y dejaba rotos todos
   los enlaces relativos. Ahora los reescribe para la nueva carpeta (probado).
3. **Copiar la nota a mano** a otra carpeta sigue rompiendo los enlaces, y ningún código lo evita.
   Recomendación: que Recorder escriba directamente donde se va a leer la nota, con las capturas en
   una carpeta que no se versione.

---

## 4. Capturas tardías y el atasco de 54 min

El plan de `docs/captura-diferida.md` quedó implementado entero (su sección de estado detalla cada
paso).

**El atasco.** Las horas de los nombres de archivo se fijan al *empezar* a capturar. La captura del
renglón de las 18:08:28 empezó a las 18:08:53 (25 s de atraso); la del renglón de las 18:08:44, a las
19:02:33. Entre medias hubo **un único paso**: esa captura o la transcripción de un fragmento de 20 s
como mucho. La captura de voz siguió, porque las horas de los renglones son continuas, así que no
fue una suspensión. La nota del 22-SEP, con 269 capturas, no tiene ningún salto (atraso estable de
~20 s). Causas descartadas:

* **Reintentos por temperatura** (`rendimiento.md`, hecho 7): sobre ruido sintético llegaron como
  mucho a T=0,4, unos 8 s por fragmento de 12 s.
* **`_load_cpu_fallback`:** solo actúa con Vulkan, y la sesión corría en CPU.

La explicación más probable, **sin verificar**, es que `PrintWindow` se quedara esperando a una
ventana colgada: manda `WM_PRINT` y espera sin límite. Cambios:

* Con el buffer, el hilo de transcripción ya no captura, salvo en el plan B.
* Antes de `PrintWindow`, `responsive()` comprueba que la ventana atiende un mensaje en 1 s; si no,
  se recorta lo visible en su rectángulo.
* La enumeración de ventanas usa `InternalGetWindowText`, que no manda mensajes a otros procesos.
* La nota anota el atraso (`> ⏳ transcripción atrasada N min desde …`, al pasar de 2 min y cada vez
  que se duplica, y `> ✔ … al día`) y cualquier paso que pase de 1 min (`> ⚠ fragmento lento: …`,
  `⚠ la captura tardó …`). Si vuelve a pasar, la nota dirá qué paso fue.

**Reunión de prueba** (9,7 min de voz sintética es-MX con 15 palabras clave marcadas al segundo
mediante *bookmarks* SSML y 30 s de silencio, reproducida por los auriculares y capturada por
loopback con la app real; objetivo de captura: una ventana con un reloj con décimas):

| Criterio | Resultado |
| :--- | :--- |
| Cero renglones "Términos" | **Sí**: 0 en 26 renglones |
| Todas las capturas existen | **Sí**: 6 de 6 en disco, enlace relativo; `.buffer` vacío al cerrar |
| Sello a ±5 s de la palabra | **5 de 6** a ±0,2 s (imagen a ±2,1 s; el reloj capturado lo confirma). La sexta, a −9,2 s: a su fragmento le faltaban unos 10 s de audio (una frase entera del guion no se transcribió) |
| Renglones 🎤 cuando habla el usuario | **No verificado**: nadie habló. El micrófono sí dio 4 renglones 🎤 con la voz sintética que se filtraba de los auriculares, así que la ruta funciona |
| El nombre del cliente sale normalizado | **Sí**: 5 veces bien escrito, 0 variantes |

La prueba **no fue limpia**. Había otro audio sonando en el equipo (el loopback transcribió una
conversación ajena) y, a mitad, un diagnóstico compitió por la CPU. Solo 6 de las 15 palabras clave
llegaron al texto; las demás se perdieron con el audio mezclado o entrecortado. Tres mediciones
controladas descartan que la pérdida venga de estos cambios:

* **El mismo audio leído del archivo:** los 11 segmentos pasan todos los filtros, con los tres
  vocabularios.
* **Frames de loopback recibidos frente a esperados en 30 s:** 1,001 solo captura, 0,999 con el
  buffer, 0,995 con el worker y 0,991 con todo. El peor hueco fue de 0,18 s.
* **Nivel de la salida a volumen normal:** RMS mediana de 3046, con el 97 % de los frames por encima
  del umbral de 150.

Una segunda pasada se detuvo a los 1,5 min al detectar otra vez audio ajeno, y sus notas se borraron.

---

## 5. Micrófono mudo

* `mic_dev` es "Micrófono externo (Realtek(R) Audio)", que además es el predeterminado de Windows.
  Medido en silencio: RMS mediana de 98 (unos −50 dBFS). Solo 13 de 187 frames pasan el umbral de 150,
  y así nunca se completa un fragmento. En la reunión de prueba ese mismo micrófono sí captó la voz
  que se filtraba de los auriculares: el dispositivo funciona.
* **Probable, sin verificar:** durante la daily el usuario hablaba por otro micrófono, el que usa
  Teams. El equipo tiene además "Varios micrófonos (Intel)" y una interfaz USB.
* **Tampoco explicado:** que la voz del usuario apareciera sin 🎤, es decir, en la salida. Teams no
  devuelve la voz propia. Candidatos, sin verificar: "Escuchar este dispositivo" activado en
  Windows, o el micrófono de otro participante captando al usuario.
* Antes, una fuente muda no daba ningún aviso. Ahora la nota apunta al arrancar qué dispositivo
  resolvió cada fuente. Si una lleva 10 min (`MUTE_WARN_SEC`) sin dar fragmentos mientras la otra sí,
  el medidor muestra 🔇 y la nota lo dice. Cuenta fragmentos y no nivel: con el nivel, el ruido de
  este micrófono lo habría hecho pasar por vivo. Por el mismo motivo, retener el equipo despierto y
  el buffer usan ahora el último fragmento y no el último frame con nivel.

---

## 6. Qué no se pudo verificar y por qué

* **La causa de las capturas perdidas**, y dónde se escribió la nota original: no quedan rastros en
  el disco.
* **La causa del atasco de 54 min.** El hueco está acotado a un paso, pero no hay registro de cuál fue.
  Los nuevos marcadores lo dirán si se repite.
* **El eco "Términos" en sí:** se reprodujo el mecanismo (Whisper recitando la lista del prompt), no el
  rótulo, porque haría falta el audio real, que Recorder no guarda.
* **Renglones 🎤 con la voz del usuario:** requiere que el usuario hable en la prueba.
* **Que las capturas abran desde Obsidian:** se comprobó que el archivo existe en la ruta relativa
  del enlace, que es lo que Obsidian resuelve, pero no se abrió en Obsidian.
* **Una reunión de prueba limpia de 10 min:** la única completa se hizo con audio ajeno de fondo. Hay
  que repetirla con el equipo sin otro audio, sin una llamada en curso y hablando por el micrófono.
* **El coste de CPU del buffer conviviendo con Whisper:** no se midió aparte. `captura-diferida.md`
  lo midió aislado (3,2-4,9 % de un núcleo).

---

## 7. Fuentes

* Nota auditada y nota manual del usuario (locales, fuera del repositorio).
* `faster-whisper` 1.2.1: `Segment.temperature`, `no_speech_prob`, `avg_logprob`; truncado del prompt a
  223 tokens en `transcribe.py`.
* Win32: `PrintWindow` y `WM_PRINT` (<https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-printwindow>);
  `SendMessageTimeoutW` con `SMTO_ABORTIFHUNG`
  (<https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw>);
  `InternalGetWindowText` (<https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-internalgetwindowtext>).
* Aviso de OpenAI sobre la «alucinación de palabras clave» con vocabularios largos como contexto:
  resumido en `docs/stt-nube-y-privacidad.md`, sección 5.
