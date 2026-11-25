"""Los textos de ayuda de Recorder, sin tkinter ni rich: los tooltips de la ventana (ui/tooltip.py)
y las líneas de ayuda de la terminal (cli/menu.py, cli/pantallas.py) salen de aquí.

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
        "Quita las frases de menos de 4 palabras, como «sí» u «ok». Ojo: también se van respuestas "
        "con contenido, como «Sí, va.».",
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
        "Empieza a transcribir la reunión a pantalla completa y la guarda en la nota de hoy. "
        "Al terminar vuelves a este menú.",
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
        "Puedes aplicarla ahí mismo.",
    ),
    "menu_ventana": (
        "Abrir la ventana",
        "Abre Recorder con ventana y botones: mismos ajustes y misma nota. "
        "Mientras esté abierta, esta terminal espera.",
    ),
    "menu_salir": (
        "Salir",
        "Cierra este menú y vuelve a la terminal.",
    ),
    "menu_rendimiento": (
        "Rendimiento",
        "Con qué motor se transcribiría y cuánto procesador y tarjeta gráfica usa ahora el equipo, "
        "con su tendencia. Sirve para ver si hay margen antes de grabar.",
    ),
    # Rendimiento (pantalla del menú y vista en vivo de la grabación): «rendimiento_» + cada dato
    "rendimiento_margen_ok": ("Hay margen para grabar", "El equipo va desahogado: puedes grabar con la calidad elegida."),
    "rendimiento_margen_justo": ("El equipo va justo", "Ya está ocupado: cierra lo que no uses antes de grabar."),
    "rendimiento_margen_no": ("El equipo va cargado", "Cierra algo o baja la calidad: así la transcripción se atrasaría."),
    "rendimiento_midiendo": ("Midiendo", "La primera cifra llega en un par de segundos."),
    "rendimiento_motor": ("Se transcribiría con", "Con qué se transcribiría una grabación que empezara ahora."),
    "rendimiento_ahora": ("Ahora, en todo el equipo", "Lo que usan todos los programas juntos, como en el Administrador de tareas."),
    "rendimiento_tendencia": ("últimos 2 min", "Cada columna es una muestra; más alta, más uso."),
    "rendimiento_cpu": ("Procesador", "Cuánto procesador se usa. Recorder necesita margen para no atrasarse."),
    "rendimiento_gpu": ("Tarjeta gráfica", "Cuánta tarjeta gráfica se usa. Solo importa si se transcribe con ella."),
    "rendimiento_ram": ("Memoria", "Cuánta memoria hay ocupada. Con poca libre, Windows va más lento."),
    "rendimiento_ram_de": ("{usada} de {total} GB", "La memoria ocupada y la que tiene el equipo."),
    "rendimiento_de_total": ("de {total} GB", "La memoria que tiene el equipo."),
    "rendimiento_pico": ("pico {n} %", "Lo más alto de los últimos 2 minutos."),
    "rendimiento_nd": ("n/d", "Windows no da este dato en este equipo."),
    "rendimiento_equipo": ("Equipo", "El equipo detectado."),
    "rendimiento_medir": ("Medir mi equipo", "Prueba de 2 o 3 minutos que dice qué calidad aguanta tu equipo de verdad."),
    "rendimiento_al_dia": ("Va al día", "Transcribe {factor} veces más rápido de lo que se habla."),
    "rendimiento_va_justo": (
        "Va justo", "Transcribe casi a la velocidad del habla: si la reunión se alarga, se atrasará.",
    ),
    "rendimiento_se_atrasa": (
        "Se atrasa", "Transcribe más lento de lo que se habla. Baja la calidad en Opciones para la próxima grabación.",
    ),
    "rendimiento_cargando": ("Cargando el modelo", "La velocidad se sabrá con la primera frase."),
    "rendimiento_velocidad": (
        "Velocidad", "Cuántas veces más rápido que el habla se transcribe. Por debajo de 1× se acumula atraso.",
    ),
    "rendimiento_tiempo_real": ("1× = al ritmo del habla", "La marca desde la que la transcripción deja de atrasarse."),
    "rendimiento_ultimo": ("último trozo: {s} s", "Lo que tardó en transcribirse el último trozo de audio."),
    "rendimiento_cola": (
        "En cola", "Trozos de audio que esperan su turno. Si crece sin parar, el equipo no da abasto.",
    ),
    "rendimiento_cola_valor": ("{n} trozos · {s} s de audio", "Lo que falta por transcribir."),
    "rendimiento_cola_uno": ("1 trozo · {s} s de audio", "Lo que falta por transcribir."),
    "rendimiento_cola_vacia": ("nada pendiente", "Todo lo oído ya está en la nota."),
    "rendimiento_recorder": ("Recorder", "Lo que usa Recorder (con whisper.cpp si lo usa)."),
    "rendimiento_todo": ("equipo", "Lo que usa el equipo entero."),
    "rendimiento_motor_efectivo": (
        "Motor", "Con qué se transcribe de verdad: programa, procesador o tarjeta gráfica, y calidad.",
    ),
    "rendimiento_caida": (
        "Caída al procesador", "Se transcribe con el procesador porque la tarjeta gráfica falló ({motivo}).",
    ),
    "menu_ayuda": (
        "Ayuda",
        "Las teclas de este menú y de la grabación, y la jerga de Recorder en palabras llanas.",
    ),
    # Inicio: la ficha de lo que usará la próxima grabación («inicio_» + cada dato)
    "inicio_proxima": ("Próxima grabación", "Lo que usará la próxima grabación. Se cambia en Opciones."),
    "inicio_nota": ("Nota de hoy", "El archivo donde se guardará la transcripción de hoy."),
    "inicio_carpeta": ("Carpeta", "La carpeta de notas."),
    "inicio_calidad": ("Calidad", "La calidad de transcripción elegida."),
    "inicio_motor": ("Se usará", "Con qué se transcribirá: el procesador o la tarjeta gráfica."),
    "inicio_escucha": ("Escucha", "La salida de audio de la que se transcribe a los demás."),
    "inicio_micro": ("Micrófono", "El micrófono que se transcribe, o «apagado»."),
    "inicio_capturas": ("Capturas", "Qué se fotografía y con qué palabras clave."),
    "inicio_equipo": ("Equipo", "El equipo detectado."),
    "inicio_predeterminado": ("predeterminado", "El que Windows tiene como principal."),
    "inicio_apagado": ("apagado", "No se transcribe."),
    "inicio_todas_pantallas": ("todas las pantallas", "Se captura todo el escritorio."),
    "inicio_pantalla": ("pantalla {n}", "Se captura solo esa pantalla."),
    "inicio_al_oir": ("al oír {palabras}", "Las palabras clave que disparan una captura."),
    "inicio_sin_capturas": ("sin capturas automáticas", "Solo la captura manual con la tecla c."),
    # La ventana gráfica abierta desde el menú
    "ventana_abierta": (
        "La ventana de Recorder está abierta",
        "Ciérrala para volver a este menú. Mientras esté abierta, esta terminal no atiende el teclado.",
    ),
    "ventana_cerrada": ("Ventana cerrada", "Ventana cerrada: has vuelto al menú."),
    "ventana_no_abre": ("No se pudo abrir la ventana", "No se pudo abrir la ventana: {motivo}."),
    "solo_windows": (
        "Solo en Windows",
        "Necesita la captura de audio de Windows (WASAPI): en Linux y macOS todavía no se puede grabar "
        "ni abrir la ventana.",
    ),
    "opciones_recomendada": (
        "Usar la recomendada",
        "Pone la calidad, los hilos y, con whisper.cpp, flash attention que mejor van con tu equipo. "
        "No toca carpetas ni dispositivos; guarda con g.",
    ),
    "opciones_editar": (
        "Editar un texto",
        "Escribe o corrige el valor: ←→ mueven el cursor, Enter lo acepta y Esc lo deja como estaba.",
    ),
    "opciones_lista": (
        "Elegir de la lista",
        "Elige con ↑↓ y Enter, o con el número. Esc vuelve sin cambiar nada.",
    ),
    "opciones_carpetas": (
        "Carpetas",
        "Dónde se guardan las notas y las capturas, y qué palabras disparan una captura.",
    ),
    "opciones_audio": ("Audio", "Qué salida se escucha y si se transcribe también tu micrófono."),
    "opciones_capturas": ("Capturas", "Qué pantalla o ventana se fotografía y con qué calidad."),
    "opciones_calidad": ("Calidad", "Cuánta calidad usar según tu equipo y con qué se transcribe."),
    "opciones_apariencia": ("Apariencia", "El tema de colores de la ventana y de esta terminal."),
    "opciones_hilos_auto": ("automático ({n})", "Con 0, Recorder usa el valor de fábrica ({n} hilos)."),
    "opciones_hilos_error": ("Hilos de CPU", "Escribe un número entre 0 y {max}."),
    "opciones_no_detectado": (
        "(no detectado ahora)",
        "Lo guardado ya no aparece en este equipo; sigue elegido hasta que escojas otro.",
    ),
    # Comunes a todas las pantallas de la terminal: «terminal_» + el aviso o el estado
    "terminal_sin_guardar": (
        "Cambios sin guardar",
        "Hay cambios sin guardar: g los guarda; Esc otra vez sale sin guardarlos.",
    ),
    "terminal_marca_cambios": (
        "cambios sin guardar",
        "Se ve a la derecha de la ruta mientras haya algo cambiado y no guardado.",
    ),
    "terminal_sin_cambios": ("Sin cambios", "No hay nada que guardar."),
    "terminal_se_guardara": ("Se guardará", "Se guardará en {archivo}."),
    "terminal_confirmar": (
        "Guardar los cambios",
        "Revisa lo que cambia: Enter lo guarda y Esc te deja seguir editando.",
    ),
    "terminal_no_se_guarda": (
        "No se puede guardar",
        "config.json no se puede leer: puedes mirar y probar, pero no se guarda nada hasta que lo arregles.",
    ),
    "terminal_pequena": (
        "Ventana demasiado pequeña",
        "Agranda la ventana de la terminal: Recorder necesita al menos {columnas} columnas y {lineas} líneas.",
    ),
    "terminal_cargando": ("Detectando", "Detectando dispositivos, pantallas y equipo."),
    "terminal_detectando_equipo": ("Detectando el equipo", "Detectando el equipo."),
    "terminal_error_entorno": (
        "No se pudo detectar",
        "No se pudieron leer los dispositivos de este equipo. Esc vuelve; prueba otra vez o usa la ventana.",
    ),
    "terminal_mas_arriba": ("{n} más arriba", "Hay filas por encima de las que se ven: sube con ↑ o RePág."),
    "terminal_mas_abajo": ("{n} más abajo", "Hay filas por debajo de las que se ven: baja con ↓ o AvPág."),
    "terminal_si": ("sí", "Interruptor activado. Espacio, Enter o ←→ lo cambian."),
    "terminal_no": ("no", "Interruptor apagado. Espacio, Enter o ←→ lo cambian."),
    "terminal_vacio": ("(vacío)", "Este ajuste no tiene valor. Enter para escribirlo."),
    "terminal_actual": ("(actual)", "Lo que está guardado ahora."),
    "terminal_sin_opciones": ("Sin opciones", "No hay nada que elegir aquí. Esc vuelve."),
    # Recomendación del equipo: «recomendacion_» + la pieza
    "recomendacion_equipo": ("Tu equipo", "Lo que se detecta en este equipo."),
    "recomendacion_ahora": ("Ahora", "Lo que tienes guardado."),
    "recomendacion_recomendado": ("Recomendado", "Lo que mejor va con este equipo."),
    "recomendacion_calidad": ("Calidad", "El nivel de calidad de la transcripción."),
    "recomendacion_donde": ("Dónde se transcribe", "En el procesador o en la tarjeta gráfica."),
    "recomendacion_hilos": ("Hilos", "Cuántos núcleos del procesador usa la transcripción."),
    "recomendacion_procesador": ("Procesador", "Se transcribe con el procesador (CPU)."),
    "recomendacion_grafica": ("Tarjeta gráfica", "Se transcribe con la tarjeta gráfica (GPU)."),
    "recomendacion_igual": ("igual", "Ya lo tienes así."),
    "recomendacion_cambia": ("cambia", "Cambiaría al aplicar lo recomendado."),
    "recomendacion_porque": ("Por qué", "Los motivos de la recomendación, en dos o tres frases llanas."),
    "recomendacion_fiable_medido": ("Fiabilidad", "Medido en un equipo como el tuyo."),
    "recomendacion_fiable_estimado": ("Fiabilidad", "Estimado a partir de equipos parecidos al tuyo."),
    "recomendacion_fiable_aprox": (
        "Fiabilidad",
        "Aproximado: no hay medidas de un equipo así. Mide el tuyo en Rendimiento.",
    ),
    "recomendacion_aplicar": (
        "Aplicar lo recomendado",
        "Guarda la calidad, los hilos y dónde se transcribe que mejor van con tu equipo. "
        "Antes te enseña qué cambia.",
    ),
    "recomendacion_ya": ("Ya usas lo recomendado", "No hay nada que cambiar."),
    "recomendacion_aplicada": ("Aplicado", "Aplicado. Vale desde la próxima grabación."),
    "recomendacion_sin_detectar": (
        "Sin detectar",
        "No se pudo detectar: {que}. La recomendación no lo tiene en cuenta.",
    ),
    "recomendacion_no_aplica": ("No se aplica", "No se aplica: {motivo}."),
    # Botones del pie de las pantallas: «pie_» + la palabra
    "pie_mover": ("Mover", "Sube y baja por las filas con ↑ ↓ (o j k)."),
    "pie_abrir": ("Abrir", "Abre lo elegido."),
    "pie_salir": ("Salir", "Sale de este menú."),
    "pie_volver": ("Volver", "Vuelve a la pantalla anterior."),
    "pie_ayuda": ("Ayuda", "Enseña las teclas y la jerga de Recorder."),
    "pie_mas": ("Más", "Hay más teclas de las que caben en esta línea: ? las enseña todas."),
    "pie_tema": ("Tema", "Cambia entre el tema claro y el oscuro, y lo guarda."),
    "pie_cambiar": ("Cambiar", "Cambia el valor de la fila elegida con ← →."),
    "pie_editar": ("Editar", "Escribe el valor de la fila elegida."),
    "pie_elegir": ("Elegir", "Elige lo marcado."),
    "pie_elegir_de_la_lista": ("Elegir de la lista", "Abre la lista de valores posibles."),
    "pie_usar": ("Usar", "Pone lo recomendado para este equipo."),
    "pie_guardar": ("Guardar", "Guarda los cambios, después de enseñarte qué cambia."),
    "pie_cursor": ("Cursor", "Mueve el cursor del texto con ← →, Inicio y Fin."),
    "pie_aceptar": ("Aceptar", "Acepta el valor escrito."),
    "pie_cancelar": ("Cancelar", "Deja el valor como estaba."),
    "pie_seguir_editando": ("Seguir editando", "Vuelve a la lista sin guardar para seguir cambiando cosas."),
    "pie_volver_sin_cambiar": ("Volver sin cambiar", "Vuelve a la lista sin cambiar nada."),
    "pie_abrir_directo": ("Abrir directo", "Abre la opción con su número."),
    "pie_directo": ("Directo", "Elige la fila con su número."),
    "pie_desplazar": ("Desplazar", "Sube y baja el texto con ↑ ↓."),
    "pie_pagina": ("Página", "Avanza o retrocede una página con RePág y AvPág."),
    "pie_vista_previa": ("Vista previa", "Desplaza la vista previa con RePág y AvPág."),
    # Calibrar (pantalla de `daily menu`): «calibrar_» + el rótulo, el estado o el aviso
    "calibrar_terminos": ("Tus términos", "Lo que Recorder debe saber escribir bien."),
    "calibrar_vocabulario": (
        "Vocabulario",
        "Nombres y siglas de tu equipo para que se escriban bien. Como lista, sin rótulos como «Términos:», que se colarían en el texto.",
    ),
    "calibrar_correcciones": (
        "Correcciones",
        "Arregla palabras que siempre se oyen mal: «oído_mal=escrito_bien», separadas por «;». Por ejemplo: cuba=QA; ayayas=IIS.",
    ),
    "calibrar_inventadas": ("Frases inventadas", "Lo que la transcripción se inventa en los silencios."),
    "calibrar_ignorar": (
        "Frases a ignorar",
        "Frases que la transcripción inventa en los silencios, como «Suscríbete». Si alguna sale en tus notas, añádela aquí, separadas por coma.",
    ),
    "calibrar_comunes": (
        "Añadir las comunes",
        "Agrega las frases inventadas más típicas («gracias por ver», «suscríbete»…). No borra las que ya tienes.",
    ),
    "calibrar_comunes_hecho": ("Frases comunes", "Añadidas {n} frases comunes; ahora hay {total}."),
    "calibrar_comunes_ya": ("Frases comunes", "Ya estaban todas."),
    "calibrar_eco": (
        "Quitar eco del vocabulario",
        "Quita los renglones que solo repiten tu vocabulario, algo que la transcripción inventa a veces en los silencios. Conviene dejarlo en «sí».",
    ),
    "calibrar_filtros": (
        "Filtros de frases dudosas",
        "Tres reglas que descartan frases dudosas. Tócalas solo si ves frases inventadas o se pierden frases reales.",
    ),
    "calibrar_silencio": (
        "Filtro de silencio",
        "Descarta lo que probablemente era solo ruido. Bájalo si salen frases inventadas en silencios; súbelo si se pierden frases dichas en voz baja.",
    ),
    "calibrar_confianza": (
        "Confianza mínima",
        "Descarta frases de las que la transcripción no está segura. Súbelo si salen frases sin sentido; bájalo si se pierden frases reales.",
    ),
    "calibrar_repeticiones": (
        "Filtro de repeticiones",
        "Descarta frases que repiten lo mismo una y otra vez. Bájalo si ves repeticiones en bucle; súbelo si se pierden frases largas que sí se dijeron.",
    ),
    "calibrar_descarta_mas": ("descarta más", "Hacia ese lado el filtro descarta más frases."),
    "calibrar_descarta_menos": ("descarta menos", "Hacia ese lado el filtro deja pasar más frases."),
    "calibrar_fuera_de_rango": ("Fuera de rango", "Escribe un número entre {min} y {max}."),
    "calibrar_probar": (
        "Probar una frase",
        "Escribe una frase y mira al momento si se quedaría o se descartaría con lo que hay ahora, sin guardar. e propone un ejemplo.",
    ),
    "calibrar_probar_vacio": ("Probar una frase", "Enter para escribir una frase · e para probar con un ejemplo."),
    "calibrar_se_queda": ("Se queda", "Se queda: «{frase}»."),
    "calibrar_corregido": ("corregido", "(corregido: {de} → {a})."),
    "calibrar_con_captura": ("con captura", "y guardaría una captura ({palabras})."),
    "calibrar_descarta_ignorar": ("Se descarta", "Se descarta: contiene «{frase}» (Frases a ignorar)."),
    "calibrar_descarta_eco": ("Se descarta", "Se descarta: solo repite tu vocabulario (Quitar eco del vocabulario)."),
    "calibrar_guardado": ("Calibración guardada", "Calibración guardada. Vale desde la próxima grabación."),
    "calibrar_pie_ajustar": ("Ajustar", "Cambia el valor de la fila elegida con ← →."),
    "calibrar_pie_teclear": ("Teclear", "Escribe el valor de la fila elegida, o la frase que quieres probar."),
    "calibrar_pie_ejemplo": ("Ejemplo", "Propone una frase de ejemplo con tu vocabulario y la prueba."),
    # Las teclas de las pantallas, para la Ayuda: «atajo_» + qué hacen. El título es la tecla.
    "ayuda_teclas": ("Teclas de las pantallas", "Valen en Inicio, Opciones, Calibrar, Reagrupar, Recomendación y Rendimiento."),
    "atajo_mover": ("↑ ↓  j k", "moverse por la lista."),
    "atajo_extremos": ("Inicio  Fin", "ir a la primera o a la última fila."),
    "atajo_pagina": ("RePág  AvPág", "avanzar o retroceder una página en listas largas y vistas previas."),
    "atajo_abrir": ("Enter", "abrir, editar o confirmar lo elegido."),
    "atajo_cambiar": ("← →  Espacio", "cambiar el valor de un ajuste; Espacio alterna un sí o un no."),
    "atajo_volver": ("Esc  q", "volver a la pantalla anterior; en Inicio, salir."),
    "atajo_numeros": ("1-9  0", "abrir una opción de Inicio o elegir en una lista numerada."),
    "atajo_guardar": ("g", "guardar los cambios (antes enseña qué cambia)."),
    "atajo_tema": ("t", "tema claro u oscuro (se guarda)."),
    "atajo_ayuda": ("?", "esta ayuda."),
    "atajo_ctrl_c": ("Ctrl+C", "salir de Recorder sin guardar."),
    "ayuda_teclas_grabacion": ("Teclas de la grabación (daily)", "Las de la grabación en pantalla completa."),
    "ayuda_glosario": ("Glosario", "La jerga de Recorder en palabras llanas."),
    "opciones_guardar": (
        "Guardar",
        "Enseña qué cambió y lo guarda en config.json al confirmar con Enter. Una grabación ya "
        "abierta sigue con lo anterior hasta que la vuelvas a abrir.",
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
        "Cambia audio, micrófono y capturas sin parar la grabación. Elige con ↑↓ y Enter o con el número; "
        "Esc vuelve sin cambiar nada.",
    ),
    "tecla_q": (
        "Salir",
        "Termina la grabación. Si queda audio sin transcribir, te pregunta si esperar o salir sin "
        "esperar. Ctrl+C hace lo mismo.",
    ),
    "tecla_m": (
        "Rendimiento",
        "Muestra la velocidad, la cola y lo que gasta Recorder ahora. Esc vuelve a la transcripción.",
    ),
    "tecla_ayuda": ("Teclas", "Muestra esta lista de teclas. Esc vuelve a la transcripción."),
    "tecla_revisar": (
        "Revisar",
        "RePág, AvPág y ↑↓ recorren lo ya transcrito; Inicio va al principio y Fin vuelve a lo último.",
    ),
    # Al salir con audio pendiente: «cierre_» + la tecla, en minúsculas
    "cierre_e": (
        "Esperar y salir",
        "Termina de transcribir lo pendiente sin escuchar audio nuevo y sale sola al acabar.",
    ),
    "cierre_s": (
        "Salir sin esperar",
        "Sale ya. Lo que faltaba por transcribir no llega a la nota.",
    ),
    "cierre_esc": (
        "Seguir grabando",
        "No sale: la grabación sigue como estaba. Mientras se pregunta, las demás teclas no hacen nada.",
    ),
    "pie_motor": (
        "Motor y velocidad",
        "Con qué se transcribe y cuántas veces más rápido que el habla va. Por debajo de 1× no da "
        "abasto y se acumula atraso: baja la calidad.",
    ),
    # Grabación a pantalla completa (`daily`): «grabacion_» + la pieza. Donde el texto lleva {huecos} o se
    # compone con otros, la pantalla lo da con `.format` y sin el punto final.
    "grabacion_nombre": ("Grabación", "La grabación de la reunión en curso."),
    "grabacion_preparando": ("Preparando", "Se carga el modelo y se abre el audio. Tarda unos segundos."),
    "grabacion_cargando_modelo": ("Cargando el modelo", "Se carga el modelo de transcripción en el equipo."),
    "grabacion_abriendo_audio": ("Abriendo el audio", "Se abren la salida de audio y el micrófono."),
    "grabacion_fuente_salida": ("Salida de audio", "Lo que suena en tu PC, de donde sale la voz de los demás."),
    "grabacion_fuente_micro": ("Micrófono", "Tu micrófono, si está activado."),
    "grabacion_fuente_capturas": ("Capturas", "{que}, al oír {palabras}."),
    "grabacion_cap_todas": ("todas las pantallas", "Se fotografían todas las pantallas."),
    "grabacion_cap_pantalla": ("pantalla {n}", "Se fotografía solo esa pantalla."),
    "grabacion_cap_ventana": ("ventana «{titulo}»", "Se fotografía solo esa ventana."),
    "grabacion_cap_apagadas": ("sin capturas", "Las capturas automáticas están apagadas."),
    "grabacion_escuchando": ("Escuchando", "Se transcribe lo que suena en tu PC y, si está activado, tu micrófono."),
    "grabacion_pausa": ("En pausa", "No se escucha audio nuevo; lo pendiente se sigue transcribiendo."),
    "grabacion_terminando": ("Terminando", "Ya no se escucha: se transcribe lo pendiente y se sale sola."),
    "grabacion_en_cola": ("en cola {n}", "Trozos de audio que esperan su turno para pasar a texto."),
    "grabacion_con_fallo": ("{n} con fallo", "Trozos que no se pudieron transcribir o capturas que no se guardaron."),
    "grabacion_nombre_pc": ("PC", "Lo que suena en tu PC: la voz de los demás."),
    "grabacion_nombre_mic": ("Mic", "Tu micrófono: lo que dices tú."),
    "grabacion_sin_audio": ("sin audio", "Esa fuente lleva un rato sin voz."),
    "grabacion_reintento": ("reintento {n}", "Esa fuente se cortó y Recorder intenta abrirla otra vez."),
    "grabacion_empieza": ("Empieza la grabación", "Empieza la grabación · {fuentes}."),
    "grabacion_captura": ("captura: {palabras}", "Se guardó una captura al oír esa palabra clave."),
    "grabacion_captura_manual": ("captura manual", "Guardaste una captura con c."),
    "grabacion_linea_pausa": ("pausa", "pausa: no se escucha audio nuevo."),
    "grabacion_linea_sigue": ("sigue", "sigue la grabación."),
    "grabacion_nuevas": ("{n} frases nuevas abajo", "Fin vuelve a lo último."),
    "grabacion_nueva_una": ("1 frase nueva abajo", "Fin vuelve a lo último."),
    "grabacion_muda": (
        "{fuente} sin audio",
        "{fuente} lleva {min} min sin audio mientras la otra fuente suena. Si alguien habló por ahí, pulsa o y elige otro dispositivo.",
    ),
    "grabacion_caida": (
        "{fuente} se cortó",
        "{fuente} se cortó: reintento {n}. Si no vuelve, pulsa r o revisa que siga conectado.",
    ),
    "grabacion_vuelve": ("{fuente} ha vuelto", "{fuente} ha vuelto: se sigue transcribiendo."),
    "grabacion_esc": ("Para salir, q", "Para terminar la grabación pulsa q. Esc solo cierra paneles."),
    "grabacion_opciones": ("Opciones de la grabación", "Lo que se puede cambiar sin parar de grabar. Se aplica al elegir."),
    "grabacion_op_salida": ("Salida de audio", "El altavoz o los auriculares por los que oyes la reunión."),
    "grabacion_op_micro": ("Micrófono", "El micrófono con el que hablas, o «apagado» para no transcribirte."),
    "grabacion_op_captura": ("Qué capturar", "La pantalla o la ventana que se fotografía en cada captura."),
    "grabacion_op_calidad": ("Calidad de capturas", "Calidad de la imagen que se guarda al oír una palabra clave."),
    "grabacion_mic_apagado": ("apagado", "apagado: no se transcribe el micrófono."),
    "grabacion_dispositivo_nuevo": (
        "¿No aparece?", "¿No aparece? Si lo conectaste después de empezar, sal con q y vuelve a entrar.",
    ),
    "grabacion_aplicado": ("Cambiado", "{ajuste}: {valor}."),
    "grabacion_teclas": ("Teclas de la grabación", "Lo que hace cada tecla mientras grabas."),
    "grabacion_rendimiento": ("Rendimiento", "La velocidad y lo que gasta Recorder, dentro de la grabación."),
    "grabacion_salir": ("Salir de la grabación", "Quedan {resumen} sin transcribir."),
    "grabacion_vaciando": ("Terminando lo pendiente", "{hechos} de {total} trozos · unos {tiempo}."),
    "grabacion_resumen": ("Grabación terminada", "Lo que queda en el historial de la terminal al salir."),
    "grabacion_resumen_nota": ("Nota", "El archivo donde quedó la transcripción."),
    "grabacion_resumen_duracion": ("Duración", "{duracion} · {frases} · {capturas}."),
    "grabacion_resumen_avisos": ("Avisos", "{n}: {lista}."),
    "grabacion_perdido": ("Sin transcribir", "Se perdieron {resumen} sin transcribir."),
    "grabacion_nota_no_abre": ("No se pudo abrir la nota", "No se pudo abrir la nota: {motivo}."),
    "grabacion_fin_aviso": (
        "Grabación terminada", "Grabación terminada: {duracion} · {frases} · {capturas} · {nota}.",
    ),
    "grabacion_dur_s": ("{n} s", "Segundos de grabación."),
    "grabacion_dur_min": ("{n} min", "Minutos de grabación."),
    "grabacion_dur_h": ("{h} h {m:02d} min", "Horas y minutos de grabación."),
    "grabacion_una_frase": ("1 frase", "Una frase transcrita."),
    "grabacion_n_frases": ("{n} frases", "Frases transcritas."),
    "grabacion_una_captura": ("1 captura", "Una captura guardada."),
    "grabacion_n_capturas": ("{n} capturas", "Capturas guardadas."),
    # Los botones del pie de la grabación: «grabacion_pie_» + la palabra
    "grabacion_pie_pausar": ("Pausar", "Deja de escuchar audio nuevo."),
    "grabacion_pie_seguir": ("Seguir", "Vuelve a escuchar."),
    "grabacion_pie_captura": ("Captura", "Guarda ahora una captura."),
    "grabacion_pie_nota": ("Nota", "Abre la nota de hoy."),
    "grabacion_pie_opciones": ("Opciones", "Abre el panel de opciones."),
    "grabacion_pie_rendimiento": ("Rendimiento", "Muestra la velocidad y lo que gasta Recorder."),
    "grabacion_pie_teclas": ("Teclas", "Muestra la lista de teclas."),
    "grabacion_pie_revisar": ("Revisar", "Recorre lo ya transcrito."),
    "grabacion_pie_ultimo": ("Lo último", "Vuelve a seguir la última frase."),
    "grabacion_pie_cerrar": ("Cerrar", "Cierra el panel."),
    "grabacion_pie_releer": ("Releer ventanas", "Vuelve a buscar las ventanas abiertas."),
    "grabacion_pie_a_la_transcripcion": ("Volver a la transcripción", "Cierra esta vista."),
    # Reagrupar nota (pantalla del menú): «reagrupar_» + lo que explica
    "reagrupar_elegir": (
        "Elige la nota",
        "Elige la nota que quieres reagrupar. Solo se lee: el original nunca se modifica, mueve ni renombra.",
    ),
    "reagrupar_col_nota": ("Nota", "El archivo original."),
    "reagrupar_col_fecha": ("Fecha", "Día del último cambio."),
    "reagrupar_col_hora": ("Hora", "Hora del último cambio."),
    "reagrupar_col_tamano": ("Tamaño", "Tamaño del archivo."),
    "reagrupar_en_curso": (
        "escribiéndose",
        "Esta nota se está escribiendo ahora: la copia llevará lo que haya hasta este momento.",
    ),
    "reagrupar_vacio": ("No hay notas todavía", "No hay notas todavía: se crean al grabar."),
    "reagrupar_agrupar": (
        "Agrupar",
        "Junta las frases en tramos de tiempo, cada uno con su hora de título (por ejemplo, 09:30 - 09:45). "
        "«Sin agrupar» solo aplica la limpieza.",
    ),
    "reagrupar_unir": (
        "Unir frases seguidas",
        "Une en un párrafo las frases seguidas de la misma fuente (los demás o tu micrófono) para leerlas de corrido.",
    ),
    "reagrupar_hora_corta": (
        "Hora corta",
        "Pone solo hora y minutos (09:30) al empezar cada párrafo, no la hora exacta de cada frase.",
    ),
    "reagrupar_hora_corta_no": (
        "Hora corta",
        "Hora corta no se puede con «Sin agrupar»: ahí la hora exacta es lo único que ordena las frases.",
    ),
    "reagrupar_sin_imagenes": (
        "Quitar imágenes",
        "Deja la copia en texto puro, sin enlaces a las capturas. Útil para pegarla en un correo o en un chat.",
    ),
    "reagrupar_cortas": (
        "Quitar frases cortas",
        "Quita las frases de menos de 4 palabras, como «sí» u «ok». Ojo: también se van respuestas con contenido, como «Sí, va.».",
    ),
    "reagrupar_eco": (
        "Quitar eco",
        "Borra renglones como «Términos.» que solo repiten tu vocabulario de Calibrar y que nadie dijo.",
    ),
    "reagrupar_previa": (
        "Vista previa",
        "{frases} frases en {tramos} tramos · {palabras} palabras, {quitadas} quitadas.",
    ),
    "reagrupar_previa_sin_tramos": (
        "Vista previa",
        "{frases} frases · {palabras} palabras, {quitadas} quitadas.",
    ),
    "reagrupar_crear": (
        "Crear la copia",
        "Crea el archivo reagrupado junto a la nota y deja el original intacto. Antes te dice cómo se llamará.",
    ),
    "reagrupar_confirmar": (
        "Crear la copia",
        "Es la misma transcripción, ordenada y agrupada: no es un resumen. El original no se toca; "
        "si el nombre ya existe, se numera.",
    ),
    "reagrupar_se_creara": ("Se creará", "El nombre de la copia."),
    "reagrupar_en": ("en", "La carpeta de la copia: la misma que la nota."),
    "reagrupar_seguir": ("Seguir ajustando", "Vuelve a las opciones sin crear nada."),
    "reagrupar_creada": ("Copia creada", "Creada {nombre}. El original sigue intacto."),
    "reagrupar_error": ("No se pudo crear", "No se pudo crear la copia: {motivo}."),
    "reagrupar_derivada": (
        "Es una copia reagrupada",
        "Esa nota ya es una copia reagrupada: elige la original.",
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
    # Ajuste del rendimiento al equipo (ajustes manuales y «Medir mi equipo», de la ventana y de la terminal)
    "permitir_igpu": (
        "Permitir GPU integrada",
        "Deja que Recorder use la tarjeta gráfica integrada. Comparte memoria y potencia con el procesador y "
        "con Teams: mídela antes de fiarte.",
    ),
    "prioridad": (
        "Prioridad del proceso",
        "«Por debajo de lo normal» cede el procesador a Teams si hace falta, a costa de atrasarse más. "
        "Vale desde la próxima grabación.",
    ),
    "prioridad_normal": ("Normal", "La prioridad de siempre."),
    "prioridad_inferior": ("Por debajo de lo normal", "Teams y los demás programas pasan primero; Recorder usa lo que sobre."),
    "hilos_hibrida": (
        "Núcleos rápidos y lentos",
        "Tu procesador mezcla {p} núcleos rápidos y {e} lentos: pasar de los rápidos no siempre acelera. "
        "«Medir mi equipo» lo comprueba.",
    ),
    "medir_abrir": ("Medir mi equipo", "Prueba de 2 o 3 minutos que dice qué calidad aguanta tu equipo de verdad."),
    "medir_intro": (
        "Qué aguanta tu equipo",
        "Prueba unas cuantas configuraciones con una muestra de voz corta y dice cuál usar. No cambia nada hasta que lo confirmes.",
    ),
    "medir_preparando": ("Preparando la prueba", "Detecta el equipo y crea una muestra de voz corta; no suena por los altavoces."),
    "medir_empezar": ("Empezar", "Empieza la prueba, de 2 o 3 minutos. No cambia nada hasta que apliques el mejor."),
    "medir_progreso": ("Midiendo {i} de {n}", "La prueba que se está midiendo ahora."),
    "medir_queda": ("queda {tiempo} aprox.", "Lo que falta para terminar todas las pruebas."),
    "medir_tiempo": ("{m} min {s} s", "Minutos y segundos."),
    "medir_tiempo_s": ("{s} s", "Segundos."),
    "medir_consejo": ("Mientras se mide", "No uses el equipo para cosas pesadas mientras se mide: falsearía el resultado."),
    "medir_col_prueba": ("Prueba", "Calidad y con qué se transcribe."),
    "medir_col_velocidad": ("Velocidad", "Veces más rápido que el habla."),
    "medir_col_velocidad_corta": ("Vel.", "Veces más rápido que el habla."),
    "medir_col_cpu": ("Procesador", "Procesador usado durante la prueba."),
    "medir_col_cpu_corta": ("CPU", "Procesador usado durante la prueba."),
    "medir_col_dos": ("¿Dos fuentes?", "Los demás y tu micrófono a la vez: hace falta ir a 2,0× o más."),
    "medir_en_espera": ("en espera", "Aún no ha empezado."),
    "medir_midiendo": ("midiendo…", "Se está midiendo ahora."),
    "medir_si": ("sí", "Aguanta los demás y tu micrófono a la vez."),
    "medir_no_justo": ("no: va justo", "Sirve con una sola fuente; con dos se atrasaría."),
    "medir_no_atrasa": ("no: se atrasa", "Va más lento que el habla: no sirve para grabar."),
    "medir_mejor": ("la mejor", "La de más calidad entre las que aguantan dos fuentes."),
    "medir_ninguna": (
        "Ninguna aguanta dos fuentes",
        "Usa la más rápida y apaga el micrófono, o cierra otros programas y mide otra vez.",
    ),
    "medir_aplicar": (
        "Aplicar el mejor", "Guarda la calidad, los hilos y dónde se transcribe de la mejor prueba. Antes te enseña qué cambia.",
    ),
    "medir_aplicar_rapida": (
        "Aplicar la más rápida", "Ninguna aguanta dos fuentes: guarda la más rápida. Antes te enseña qué cambia.",
    ),
    "medir_cancelar": ("Cancelar", "Para la medición y descarta lo medido. No cambia nada."),
    "medir_cancelada": ("Medición cancelada", "Medición cancelada. No se cambió nada."),
    "medir_aplicado": ("Aplicado", "Aplicado. Vale desde la próxima grabación."),
    "medir_otra_vez": ("Medir otra vez", "Repite las pruebas, por ejemplo tras cerrar otros programas."),
    "medir_ya": ("Ya usas la mejor", "Tu configuración ya es la de la mejor prueba."),
    "medir_ocupado": (
        "El equipo está ocupado",
        "Va al {n} % de procesador: la medición saldría peor de lo real. Cierra programas y mide otra vez.",
    ),
    "medir_igual": ("Medir de todos modos", "Mide con el equipo ocupado: los resultados serán menos fiables."),
    "medir_cerrar": ("Cerrar", "Cierra esta ventana sin cambiar nada. Lo medido queda guardado para la recomendación del equipo."),
    "medir_error": ("No se pudo medir", "Pasó esto: {motivo}. No se cambió nada."),
    "medir_sin_voz": (
        "Sin voz en español",
        "Windows no tiene ninguna voz en español para crear la muestra de prueba: instálala en Configuración, Hora e idioma, Voz.",
    ),
    "medir_sin_pruebas": ("Nada que medir", "Este equipo no tiene ninguna configuración que probar."),
    "medir_omitida_modelo": ("modelo sin descargar", "Ese modelo no está en el equipo y Recorder no descarga nada sin avisarte."),
    "medir_omitida_tiempo": ("sin tiempo", "La prueba tiene un tope de tiempo y esta no llegó a medirse."),
    "medir_omitida_poda": ("no hace falta", "Una más ligera ya iba más lenta que el habla: esta iría peor."),
    "medir_omitida_cancelada": ("sin medir", "La medición se paró antes de llegar aquí."),
    "medir_fallo": ("falló", "No se pudo probar: {motivo}."),
    "medir_mal": ("transcribe mal", "Fue rápida, pero se equivocó demasiado en la muestra: no se recomienda."),
    "medir_igpu_apagada": (
        "Gráfica integrada sin probar",
        "No está permitida. Para probarla, activa «Permitir GPU integrada» en Opciones y mide otra vez.",
    ),
    "medir_fecha": ("Medido el {fecha}", "Cuándo se hizo la última medición guardada."),
    "medir_donde_cpu": ("procesador, {n} hilos", "Se transcribe con el procesador."),
    "medir_donde_cpu_corto": ("CPU, {n} hilos", "Se transcribe con el procesador."),
    "medir_donde_gpu": ("tarjeta gráfica", "Se transcribe con la tarjeta gráfica."),
    "medir_donde_gpu_corto": ("GPU", "Se transcribe con la tarjeta gráfica."),
    "medir_donde_igpu": ("tarjeta gráfica integrada", "Se transcribe con la tarjeta integrada, que comparte memoria con el procesador."),
    "medir_donde_igpu_corto": ("GPU integrada", "Se transcribe con la tarjeta integrada."),
    "recomendacion_fiable_tuyo": ("Fiabilidad", "Medido en este equipo."),
    "medir_motivo_dos": (
        "Medido en tu equipo",
        "Medido en tu equipo el {fecha}: {prueba} fue la mejor, {velocidad} veces más rápido que el habla, y aguanta dos fuentes a la vez.",
    ),
    "medir_motivo_una": (
        "Medido en tu equipo",
        "Medido en tu equipo el {fecha}: ninguna aguanta dos fuentes a la vez. {prueba} fue la más rápida, {velocidad} veces el habla.",
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

# La introducción (recorder/intro.py, ui/intro.py y cli/intro.py). Van aparte de las secciones de
# arriba: no son (título, explicación) y no salen en los globos. Las claves son las del contrato,
# recorder/assets/intro/intro.json, que remite aquí para el texto de cada una.
INTRO: Dict[str, str] = {
    "intro.nombre": "Recorder",
    "intro.graba.titulo": "Graba tu daily",
    "intro.graba.subtitulo": "Tu micrófono y la reunión, a la vez.",
    "intro.transcribe.titulo": "Transcribe en tu equipo, sin nube",
    "intro.transcribe.subtitulo": "El texto aparece mientras hablan.",
    "intro.notas.titulo": "Notas en Markdown con capturas",
    "intro.notas.subtitulo": "Cada frase, con su hora.",
    "intro.comenzar.titulo": "Listo para tu próxima daily",
    "intro.comenzar.subtitulo": "Está también en el menú «Más».",
    "intro.saltar": "Saltar",
    "intro.comenzar": "Comenzar",
    "intro.pista": "Esc, Enter, Espacio o clic para saltar",
    "intro.terminal.lema": "Transcribe tu daily en tu equipo, sin nube.",
    "intro.ver": "Ver introducción",
    "intro.sin_animaciones": "Con las animaciones en «ninguna» no hay introducción. Cámbialo en Opciones.",
    "intro.opcion_sin_intro": "no muestra la introducción (el logotipo del primer daily)",
}

SECCIONES: Dict[str, Textos] = {"Ventana": VENTANA, "Terminal": TERMINAL, "Común": COMUN, "Glosario": GLOSARIO}
_TODOS: Textos = {clave: valor for seccion in SECCIONES.values() for clave, valor in seccion.items()}


def entrada(clave: str) -> Tuple[str, str]:
    """(título, explicación) de `clave`. Una clave que no existe es un error de programación: KeyError."""
    return _TODOS[clave]


def texto_intro(clave: str) -> str:
    """El texto de una clave de la introducción (`intro.graba.titulo`…). KeyError si no existe."""
    return INTRO[clave]


def linea(clave: str) -> str:
    """La línea de ayuda de una opción, para la terminal: la explicación sola (el título ya se ve)."""
    return entrada(clave)[1]

