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
        "Puedes aplicarla ahí mismo.",
    ),
    "menu_ventana": (
        "Abrir la ventana",
        "Abre Recorder con ventana y botones en vez de en la terminal: mismos ajustes y misma nota.",
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
        "Cambia audio, micrófono y capturas sin parar la grabación. Elige con el número; Esc vuelve sin cambiar nada.",
    ),
    "tecla_q": (
        "Salir",
        "Termina la grabación. Si queda audio sin transcribir, te pregunta si esperar o salir "
        "perdiéndolo. Ctrl+C hace lo mismo.",
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

