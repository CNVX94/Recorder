"""Los textos de ayuda de Recorder, sin tkinter ni rich: los tooltips de la ventana (ui/tooltip.py)
y las líneas de ayuda de la terminal (cli/menu.py) salen de aquí.

Cada clave da (título corto, explicación). Reglas de redacción: tuteo, lenguaje llano, una o dos
frases de hasta LARGO_MAXIMO caracteres que digan qué hace, cuándo conviene tocarlo y qué pasa al
cambiarlo; si un control puede estar desactivado, por qué. La jerga se evita o se explica en el
GLOSARIO. Las claves no se repiten entre secciones (tests/test_ayuda.py lo comprueba).
"""

from typing import Dict, Tuple

LARGO_MAXIMO = 180  # caracteres de cada explicación
LARGO_TITULO = 40

Textos = Dict[str, Tuple[str, str]]

# Controles que solo existen en la ventana y sus diálogos.
VENTANA: Textos = {
    # Ventana principal
    "estado": (
        "Estado",
        "Qué hace Recorder ahora: ● escuchando, ⏸ en pausa o ⏳ terminando lo pendiente antes de cerrar.",
    ),
    "medidores": (
        "Medidores de audio",
        "Volumen que llega de 🔊 (lo que suena en tu PC) y de 🎤 (tu micrófono). "
        "Si una barra no se mueve cuando alguien habla, haz clic aquí para reconectar el audio.",
    ),
    "nota_hoy": (
        "Nota de hoy",
        "El archivo donde se guarda la transcripción de hoy, con sus capturas. "
        "Para guardarla en otra carpeta, cámbiala en ⚙ Opciones.",
    ),
    "visor": (
        "Transcripción",
        "Las frases según se transcriben, con su hora. 🎤 marca lo que dijiste tú y en color van "
        "las que tienen palabra clave. Aquí ves las últimas; la nota lo guarda todo.",
    ),
    "pausar": (
        "Pausar / Continuar",
        "Deja de escuchar audio nuevo sin cerrar; lo pendiente se sigue transcribiendo. "
        "Se desactiva al cerrar mientras se termina lo pendiente.",
    ),
    "captura": (
        "Captura",
        "Guarda ahora una imagen de la pantalla o ventana elegida en ⚙ Opciones y la enlaza en la nota en este punto.",
    ),
    "opciones": (
        "Opciones",
        "Carpetas, audio, capturas, calidad y tema. Ábrelo si no se oye a alguien o si quieres "
        "guardar las notas en otro sitio.",
    ),
    "calibrar": (
        "Calibrar",
        "Enseña a Recorder tus términos y qué frases inventadas descartar. "
        "Úsalo si ves palabras mal escritas o frases que nadie dijo.",
    ),
    "reagrupar": (
        "Reagrupar",
        "Crea una copia ordenada de una nota, agrupada en tramos de tiempo. No resume y nunca toca el original.",
    ),
    "abrir_nota": (
        "Abrir nota",
        "Abre la nota de hoy con el programa que usa tu PC para los .md, para leerla o copiar algo mientras se escribe.",
    ),
    "mas": (
        "Más",
        "Opciones, Calibrar, Reagrupar nota, el panel de rendimiento, el tema y la ayuda. "
        "Cada opción muestra su atajo de teclado si lo tiene.",
    ),
    "rendimiento": (
        "Rendimiento",
        "Muestra u oculta el panel con el motor, la velocidad y lo que gasta Recorder en los "
        "últimos 2 minutos. Plegado no se redibuja.",
    ),
    "tema_alternar": (
        "Cambiar tema",
        "Pasa del tema oscuro al claro o al revés y lo guarda. Para seguir el modo de Windows, "
        "elige «Sistema» en Más → Tema.",
    ),
    "ayuda": (
        "Ayuda",
        "Lista los atajos de teclado de la ventana. Además, cada control explica qué hace al "
        "pasar el ratón o al llegar a él con Tab.",
    ),
    # Panel de rendimiento
    "rend_motor": (
        "Motor efectivo",
        "Con qué se transcribe de verdad: programa, procesador o tarjeta gráfica, calidad y haz. "
        "«Caída a CPU» quiere decir que la tarjeta gráfica falló.",
    ),
    "rend_velocidad": (
        "Velocidad",
        "Cuántas veces más rápido que el habla se transcribe, con los últimos fragmentos. "
        "Por debajo de 1× se acumula atraso y sale en rojo: baja la calidad.",
    ),
    "rend_cpu": (
        "CPU",
        "Procesador que usa Recorder (con whisper.cpp si lo usa); entre paréntesis, el del equipo "
        "entero, como en el Administrador de tareas.",
    ),
    "rend_gpu": (
        "GPU",
        "Tarjeta gráfica que usa Recorder y, entre paréntesis, la del equipo entero. «n/d» si "
        "Windows no da el dato.",
    ),
    "rend_ram": (
        "RAM",
        "Memoria que ocupa Recorder con el modelo cargado (y whisper.cpp si lo usa). Sube al "
        "cargar el modelo y después se mantiene.",
    ),
    # ⚙ Opciones
    "examinar": (
        "Elegir carpeta",
        "Abre el explorador de Windows para elegir la carpeta en vez de escribir la ruta.",
    ),
    "recomendado": (
        "Usar recomendado",
        "Pone la calidad y los ajustes que mejor van con tu equipo. Está desactivado los primeros "
        "segundos, mientras se detecta el equipo.",
    ),
    "guardar_opciones": (
        "Guardar",
        "Guarda y aplica los cambios: carpetas, audio y tema cambian al momento; la calidad, "
        "al volver a abrir Recorder.",
    ),
    "cancelar": (
        "Cancelar",
        "Cierra esta ventana sin guardar nada de lo que cambiaste en ella.",
    ),
    # 🎯 Calibrar
    "probar_reglas": (
        "Probar reglas",
        "Pasa la frase escrita a la izquierda por los filtros tal como están ahora, sin guardar, "
        "y te dice si se queda o se descarta.",
    ),
    "guardar_calibracion": (
        "Guardar calibración",
        "Guarda vocabulario, frases y umbrales, y la grabación en curso los usa sin reiniciar. "
        "Si abriste esto desde ⚙ Opciones, guarda también Opciones.",
    ),
    # 📑 Reagrupar
    "nota_origen": (
        "Nota origen",
        "Elige la nota que quieres reagrupar. Solo se lee: nunca se modifica, mueve ni renombra. "
        "Las copias ya reagrupadas no salen en la lista.",
    ),
    "agrupamiento": (
        "Agrupamiento",
        "Junta las frases en bloques de tiempo, cada uno con su hora de título (por ejemplo, "
        "09:30 - 09:45). «Sin agrupar» solo aplica la limpieza.",
    ),
    "unir_lineas": (
        "Unir líneas",
        "Une en un párrafo las frases seguidas de la misma fuente (🔊 tu PC o 🎤 tu micrófono) "
        "para leerlas de corrido.",
    ),
    "hora_corta": (
        "Hora corta",
        "Pone solo hora y minutos (09:30) al empezar cada párrafo, no la hora exacta de cada frase. "
        "Se desactiva con «Sin agrupar»: ahí la hora es lo único que ordena.",
    ),
    "sin_imagenes": (
        "Quitar imágenes",
        "Deja la copia en texto puro, sin enlaces a las capturas. Útil para pegarla en un correo o en un chat.",
    ),
    "descartar_cortas": (
        "Descartar frases cortas",
        "Quita las frases muy cortas, como «sí», «ok» o «vale», que casi siempre son relleno.",
    ),
    "quitar_eco": (
        "Quitar eco",
        "Borra renglones como «Términos.» que solo repiten tu vocabulario de Calibrar y que nadie dijo.",
    ),
    "vista_previa": (
        "Vista previa",
        "Así quedará la copia con las opciones marcadas; cambia al momento. Las cifras de al lado resumen el resultado.",
    ),
    "ampliar": (
        "Ampliar / Reducir",
        "Agranda la vista previa para leer más líneas, o la devuelve a su tamaño.",
    ),
    "archivo_salida": (
        "Archivo que se creará",
        "Nombre de la copia, en la misma carpeta que la nota. Si ya existe, se numera: nunca se sobrescribe nada.",
    ),
    "generar": (
        "Generar copia",
        "Crea el archivo reagrupado y deja el original intacto. Se desactiva si no hay ninguna nota elegida en la lista.",
    ),
}

# Opciones y pantallas que solo existen en la terminal (`daily`).
TERMINAL: Textos = {
    # `daily menu`: «menu_» + la acción de cada opción
    "menu_grabar": (
        "Grabar",
        "Empieza a transcribir la reunión aquí, en la terminal, y la guarda en la nota de hoy. "
        "Las teclas para pausar, capturar o salir se ven al pie.",
    ),
    "menu_config": (
        "Opciones",
        "Cambia carpetas, audio, capturas, calidad y tema, paso a paso. Antes de guardar te "
        "enseña qué cambió; una grabación ya abierta sigue con lo anterior.",
    ),
    "menu_calibrar": (
        "Calibrar",
        "Enseña a Recorder tus términos y qué frases inventadas descartar, y pruébalo con frases. "
        "Úsalo si ves palabras mal escritas o frases que nadie dijo.",
    ),
    "menu_sintesis": (
        "Reagrupar nota",
        "Crea una copia de una nota ordenada por hora y agrupada en tramos, sin relleno. "
        "No resume y nunca toca el original.",
    ),
    "menu_recomendar": (
        "Recomendación del equipo",
        "Detecta tu procesador, memoria y tarjeta gráfica y te dice qué calidad conviene. "
        "Solo informa: para aplicarla, ve a Opciones → Calidad.",
    ),
    "menu_ventana": (
        "Abrir la ventana",
        "Abre Recorder con ventana y botones en vez de en la terminal: mismos ajustes y misma nota.",
    ),
    "menu_salir": (
        "Salir",
        "Cierra este menú y vuelve a la terminal.",
    ),
    # Grabación (`daily`): «tecla_» + la tecla del pie
    "tecla_p": (
        "Pausar / seguir",
        "Deja de escuchar audio nuevo sin cerrar; lo pendiente se sigue transcribiendo. Pulsa p otra vez para seguir.",
    ),
    "tecla_c": (
        "Captura",
        "Guarda ahora una imagen de la pantalla o ventana elegida y la enlaza en la nota en este punto.",
    ),
    "tecla_r": (
        "Reconectar",
        "Vuelve a abrir el audio con los dispositivos elegidos. Úsalo si una fuente marca ⛔ o dejó de oírse.",
    ),
    "tecla_a": (
        "Abrir la nota",
        "Abre la nota de hoy con el programa que usa tu PC para los .md, para leerla mientras se escribe.",
    ),
    "tecla_o": (
        "Opciones",
        "Cambia audio, micrófono y capturas sin parar la grabación. Elige con el número; Esc vuelve sin cambiar nada.",
    ),
    "tecla_q": (
        "Salir",
        "Termina la grabación. Si queda audio sin transcribir, te pregunta si esperar o salir "
        "perdiéndolo. Ctrl+C hace lo mismo.",
    ),
    # Al salir con audio pendiente: «cierre_» + la tecla
    "cierre_e": (
        "Esperar",
        "Termina de transcribir lo pendiente sin escuchar audio nuevo y sale sola al acabar.",
    ),
    "cierre_s": (
        "Salir perdiéndolos",
        "Sale ya. Lo que faltaba por transcribir no llega a la nota.",
    ),
    "cierre_c": (
        "Cancelar",
        "No sale: la grabación sigue como estaba.",
    ),
    "pie_motor": (
        "Motor y velocidad",
        "Con qué se transcribe y cuántas veces más rápido que el habla va. Por debajo de 1× no da "
        "abasto y se acumula atraso: baja la calidad.",
    ),
    # `daily config`: «config_» + cada sección
    "config_carpetas": (
        "Carpetas y palabras clave",
        "Dónde se guardan las notas y las capturas, y qué palabras disparan una captura.",
    ),
    "config_audio": (
        "Audio",
        "Qué salida escuchar 🔊 y si transcribir también tu micrófono 🎤. Entra aquí si en la grabación no se oye a alguien.",
    ),
    "config_capturas": (
        "Capturas",
        "Qué pantalla o ventana se fotografía y con qué calidad se guardan las capturas por palabra clave.",
    ),
    "config_calidad": (
        "Calidad y motor",
        "Cuánta calidad usar según tu equipo, cuántos núcleos del procesador y, si tienes "
        "tarjeta gráfica AMD o Intel, el programa whisper.cpp que la aprovecha.",
    ),
    "config_apariencia": (
        "Apariencia",
        "Tema claro, oscuro o el de Windows, para la ventana y para los colores de esta terminal.",
    ),
    "config_todo": (
        "Todo, paso a paso",
        "Recorre todas las secciones seguidas. Enter conserva cada valor, así que pasas rápido por lo que no quieras tocar.",
    ),
    "guardar_salir": (
        "Guardar y salir",
        "Guarda lo que cambiaste y sale. Una grabación ya abierta sigue con lo anterior hasta que "
        "la vuelvas a abrir.",
    ),
    "salir_sin_guardar": (
        "Salir sin guardar",
        "Sale y descarta todo lo que cambiaste en esta pantalla.",
    ),
}

# Ajustes y símbolos que comparten la ventana y la terminal.
COMUN: Textos = {
    "carpeta_notas": (
        "Carpeta de notas",
        "Dónde se guarda la nota .md de cada daily. Si la cambias en plena grabación, la nota de "
        "hoy se mueve allí con sus enlaces a capturas.",
    ),
    "carpeta_capturas": (
        "Carpeta de capturas",
        "Dónde se guardan las imágenes que enlaza la nota. Si la cambias, las capturas nuevas van a la carpeta nueva.",
    ),
    "palabras_clave": (
        "Palabras clave",
        "Palabras separadas por coma que, al oírse, guardan una captura y resaltan la frase. "
        "Por ejemplo: bloqueo, error, demo.",
    ),
    "salida_audio": (
        "Salida a capturar 🔊",
        "El altavoz o los auriculares por los que oyes la reunión: de ahí sale la voz de los demás. "
        "Cámbialo si 🔊 no se mueve cuando alguien habla.",
    ),
    "microfono": (
        "Micrófono 🎤",
        "El micrófono con el que hablas en la reunión; elige el mismo que usa Teams. "
        "Si 🎤 no se mueve cuando hablas, prueba otro.",
    ),
    "transcribir_mic": (
        "Transcribir mi micrófono",
        "Actívalo para que tu voz también quede en la nota, marcada con 🎤. Apágalo si solo te "
        "interesa lo que dicen los demás.",
    ),
    "que_capturar": (
        "Qué capturar 📸",
        "La pantalla o la ventana que se fotografía en cada captura. Elegir la ventana de la "
        "reunión evita que salga el resto de tu escritorio.",
    ),
    "releer_ventanas": (
        "Releer ventanas",
        "Vuelve a buscar las ventanas abiertas. Úsalo si abriste Teams o la presentación después de abrir las opciones.",
    ),
    "capturas_clave": (
        "Capturas por palabra clave",
        "Calidad de la imagen que se guarda al oír una palabra clave, o apagarlas. Más calidad "
        "ocupa más disco; la imagen es la del momento en que se dijo.",
    ),
    "calidad": (
        "Calidad de transcripción",
        "Más calidad acierta más palabras pero pide más equipo. Si el texto va muy atrasado, "
        "baja un nivel. Se aplica al volver a abrir Recorder.",
    ),
    "hilos": (
        "Hilos de CPU",
        "Cuántos núcleos del procesador usa la transcripción; 0 usa el valor de fábrica (4). "
        "Más va más rápido pero deja menos CPU a Teams.",
    ),
    "whispercpp": (
        "Carpeta de whisper.cpp",
        "Solo si tienes tarjeta gráfica AMD o Intel: la carpeta del programa whisper.cpp, que la "
        "usa para transcribir más rápido. Déjala vacía si no lo tienes.",
    ),
    "estado_whispercpp": (
        "Estado de whisper.cpp",
        "Dice si la carpeta de whisper.cpp tiene lo necesario para usar la tarjeta gráfica y, si falta algo, qué es.",
    ),
    "gpu": (
        "GPU de whisper.cpp",
        "Qué tarjeta gráfica usa whisper.cpp si tienes varias; «Automática» elige la más potente. "
        "Solo cuenta si pusiste la carpeta de whisper.cpp.",
    ),
    "flash": (
        "Flash attention",
        "Un modo de cálculo de whisper.cpp que suele ir más rápido en la tarjeta gráfica. "
        "Desactívalo si ves fallos al transcribir. Solo cuenta con whisper.cpp.",
    ),
    "tema": (
        "Tema",
        "Colores claros, oscuros o los de Windows («Sistema»). Se aplica al guardar, a la ventana "
        "y a los colores de la terminal.",
    ),
    "vocabulario": (
        "Vocabulario de contexto",
        "Nombres y siglas de tu equipo (proyectos, personas) para que se escriban bien. Ponlos "
        "como lista, sin rótulos como «Términos:», que se colarían en el texto.",
    ),
    "eco_vocab": (
        "Filtro de eco del vocabulario",
        "Quita los renglones que solo repiten tu vocabulario, algo que la transcripción inventa a "
        "veces en los silencios. Conviene dejarlo activado.",
    ),
    "ignorar": (
        "Frases a ignorar",
        "Frases que la transcripción inventa en los silencios, como «Suscríbete». Si alguna sale "
        "en tus notas, añádela aquí, separadas por coma.",
    ),
    "comunes": (
        "Añadir comunes",
        "Agrega a la lista las frases inventadas más típicas («gracias por ver», «suscríbete»…). No borra las que ya tienes.",
    ),
    "correcciones": (
        "Correcciones",
        "Arregla palabras que siempre se oyen mal: «oído_mal=escrito_bien», separadas por «;». "
        "Por ejemplo: cuba=QA; ayayas=IIS.",
    ),
    "umbrales": (
        "Umbrales del filtro",
        "Tres reglas que descartan frases dudosas: silencio, confianza y bucles. Tócalas solo si "
        "ves frases inventadas o se pierden frases reales.",
    ),
    "umbral_silencio": (
        "Filtro de silencio",
        "Descarta lo que probablemente era solo ruido. Bájalo si salen frases inventadas en "
        "silencios; súbelo si se pierden frases dichas en voz baja.",
    ),
    "umbral_confianza": (
        "Confianza mínima",
        "Descarta frases de las que la transcripción no está segura. Súbelo (más cerca de 0) si "
        "salen frases sin sentido; bájalo si se pierden frases reales.",
    ),
    "umbral_bucles": (
        "Anti-bucles",
        "Descarta frases que repiten lo mismo una y otra vez. Bájalo si ves repeticiones en "
        "bucle; súbelo si se pierden frases largas que sí se dijeron.",
    ),
    "sandbox": (
        "Probar frases",
        "Escribe una frase y mira si los filtros la dejarían o la descartarían, con lo que hay "
        "escrito ahora y sin guardar.",
    ),
    "frase_ejemplo": (
        "Frase de ejemplo",
        "Inventa una frase con tu vocabulario, correcciones y frases a ignorar para ver cómo la tratan los filtros.",
    ),
    # Símbolos de la cabecera, los medidores y la nota
    "cola": (
        "Pendientes",
        "Trozos de audio ya grabados que esperan su turno para pasar a texto. Si el número crece "
        "sin parar, tu equipo no da abasto: baja la calidad.",
    ),
    "atraso": (
        "⏳ Atraso",
        "Cuánto va el texto por detrás de lo que se oye. Unos segundos es normal; desde 2 min la "
        "nota lo marca. Si pasa a menudo, baja la calidad.",
    ),
    "fallos": (
        "⚠ con fallo",
        "Trozos de audio que no se pudieron transcribir o capturas que no se guardaron. Uno suelto "
        "no importa; si siguen subiendo, cierra y vuelve a abrir.",
    ),
    "cafe": (
        "☕ Equipo despierto",
        "Recorder pide a Windows que no se suspenda mientras graba o queda algo por transcribir. "
        "Se quita solo en silencios largos sin nada pendiente.",
    ),
    "reintento": (
        "⛔ reintento N",
        "Esa fuente de audio se cortó y Recorder intenta reabrirla sola (N intentos). Si no "
        "vuelve, revisa que el dispositivo siga conectado y reconecta.",
    ),
    "mudo": (
        "🔇 Sin audio",
        "Esa fuente lleva 10 minutos sin voz mientras la otra suena. Si alguien habló por ahí, "
        "quizá es otro dispositivo: cámbialo en las opciones.",
    ),
}

# La jerga que aparece en etiquetas, avisos y documentación, en palabras llanas.
GLOSARIO: Textos = {
    "alucinaciones": (
        "Alucinaciones",
        "Frases que la transcripción inventa cuando hay silencio o ruido, como «Gracias por ver». "
        "Calibrar sirve para descartarlas.",
    ),
    "haz": (
        "Haz de búsqueda (beam)",
        "Cuántas alternativas compara la transcripción antes de elegir cada frase. Más acierta un "
        "poco más pero va más lento. Lo fija la calidad.",
    ),
    "vad": (
        "VAD",
        "Detector de voz: separa los trozos con habla de los silencios para no transcribir ruido.",
    ),
    "whisper": (
        "Whisper",
        "El modelo que convierte la voz en texto. Funciona en tu equipo: el audio no sale a internet.",
    ),
    "vulkan": (
        "Vulkan",
        "La forma en que whisper.cpp usa tarjetas gráficas AMD o Intel. Viene con el controlador "
        "de la tarjeta; no hay que instalar nada aparte.",
    ),
    "flash_attention": (
        "Flash attention",
        "Una forma de calcular más rápida y con menos memoria en la tarjeta gráfica. Solo la usa whisper.cpp.",
    ),
    "loopback": (
        "Loopback",
        "Grabar lo que suena por tus altavoces o auriculares como si fuera un micrófono. Así "
        "Recorder oye la reunión sin cables ni programas extra.",
    ),
    "int8": (
        "int8",
        "Una forma de guardar el modelo con números más pequeños: ocupa menos y va más rápido en "
        "el procesador, con muy poca pérdida de calidad.",
    ),
    "hilos_cpu": (
        "Hilos",
        "Tareas que el procesador hace a la vez; cada núcleo atiende una o dos. Más hilos para "
        "transcribir dejan menos para los demás programas.",
    ),
    "tiempo_real": (
        "Tiempo real (×)",
        "Velocidad de la transcripción comparada con el habla: 2× tarda la mitad de lo que dura el "
        "audio; por debajo de 1× se acumula atraso.",
    ),
    "markdown": (
        "Markdown (.md)",
        "Texto plano con marcas sencillas (# para títulos, enlaces a imágenes). Se abre con "
        "cualquier editor y se ve con formato en Obsidian o VS Code.",
    ),
}

SECCIONES: Dict[str, Textos] = {"Ventana": VENTANA, "Terminal": TERMINAL, "Común": COMUN, "Glosario": GLOSARIO}
_TODOS: Textos = {clave: valor for seccion in SECCIONES.values() for clave, valor in seccion.items()}


def entrada(clave: str) -> Tuple[str, str]:
    """(título, explicación) de `clave`. Una clave que no existe es un error de programación: KeyError."""
    return _TODOS[clave]


def linea(clave: str) -> str:
    """La línea de ayuda de una opción, para la terminal: la explicación sola (el título ya se ve)."""
    return entrada(clave)[1]
