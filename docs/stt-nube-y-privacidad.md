# Transcripción en la nube y privacidad

Comparativa de servicios de reconocimiento de voz para este proyecto, con la privacidad como
criterio de primer orden. Las reuniones que transcribe esta herramienta contienen información
interna: infraestructura, nombres de sistemas y datos de clientes. Mandar ese audio a un servicio
externo **saca esa información de la empresa**, y ninguna cláusula contractual lo deshace.

> **Convención de fuentes.** `[proveedor]` = lo afirma el proveedor en su propia documentación.
> `[terceros]` = medido o reportado por alguien externo. «No encontrado» = no se localizó el dato
> en fuente accesible. Investigación de septiembre de 2026: **los precios y las políticas cambian,
> verifica antes de decidir**.

---

## 1. La conclusión primero

Para este caso concreto, reuniones de Teams con contenido interno, hay tres caminos sensatos y
uno que conviene descartar.

| Camino | Qué implica | Veredicto |
| :--- | :--- | :--- |
| **Transcripción nativa de Teams** | El audio nunca sale del inquilino de Microsoft 365 de la empresa. `es-MX` soportado. Se leen los resultados con Microsoft Graph. | **Lo primero a verificar con TI.** Exposición mínima y coste cero de ingeniería. |
| **Contenedor en local** | Speechmatics o Azure desconectado. El audio se procesa dentro de la red. | **La mejor opción si hace falta app propia.** Ver sección 3. |
| **Modelos abiertos en local** | Lo que ya hace esta herramienta. Cero exposición por definición. | **Lo actual.** Su límite es el hardware, no la privacidad. |
| **API pública en la nube** | El audio viaja a Estados Unidos o Europa. La retención cero es una promesa contractual, no una barrera técnica. | **Descartable** mientras el contenido sea interno. |

---

## 2. El dato que más sorprende

**El contenedor de Speechmatics corre en CPU, sin GPU**, con 1 vCPU y de 2 a 5 GB de RAM, y su
licencia es un archivo que no necesita conexión: funciona en una red aislada. Es la opción
local más madura de las revisadas y no exige comprar hardware.

Fuente: documentación de requisitos del contenedor de CPU y de licenciamiento de Speechmatics.

---

## 3. Ejecución fuera de la nube

| Opción | ¿Audio sale de la red? | Requisitos | Cómo se obtiene |
| :--- | :--- | :--- | :--- |
| **Speechmatics, contenedor** | No. Licencia offline, admite red aislada. | CPU: 1 vCPU, 2-5 GB RAM. Sin GPU. | Ventas o soporte. |
| **Azure, contenedor desconectado** | No. Licencia descargada con caducidad. | Ejemplo oficial: 4 CPU, 8 GB RAM. Imagen `es-mx` disponible. | Formulario y aprobación, unos 10 días hábiles. Compromiso anual por adelantado. |
| **Azure, contenedor conectado** | El audio no, pero **reporta facturación a Azure de forma continua**. | Igual que el anterior. | Suscripción normal. |
| **Google, on-prem** | No. | Contenedor en Kubernetes. | Función privada, vía comercial. |
| **Deepgram, autoalojado** | El audio no, pero **exige conexión permanente al servidor de licencias**. | **GPU NVIDIA obligatoria**, 16 GB de VRAM, 4 CPU, 32 GB RAM. Solo plan Enterprise. | Ventas. |
| **AssemblyAI, autoalojado** | No. | Contenedores con GPU. | Ventas, requisitos no publicados. |
| **Pesos abiertos** | No. | Whisper en CPU (lo actual). Voxtral Realtime 4B necesita GPU de 16 GB. | Descarga directa. |

**Sin opción local:** Amazon Transcribe, OpenAI, ElevenLabs, Gladia (lo niega explícitamente),
Groq y la transcripción de Teams como servicio suelto.

---

## 4. Si aun así se valora la nube

### Lo que hay que mirar antes que el precio

**Entrenan con tu audio por defecto**, salvo que lo desactives: Amazon Transcribe (se sale con una
política de exclusión de AWS Organizations), Deepgram (parámetro `mip_opt_out` en cada petición, y
[terceros] salir cuesta un descuento del 50 %), el plan Starter de Gladia y el plan gratuito de
Mistral.

**Ningún proveedor tiene región en México**, con dos excepciones: Amazon Transcribe en *streaming*
en `mx-central-1`, y Microsoft 365 con Residencia de Datos Avanzada, que sí cubre México. En
Latinoamérica lo habitual es São Paulo o nada.

**Español de México explícito** solo en Azure, Amazon y Google (este en versión preliminar).
AssemblyAI dice manejar el dialecto mexicano sin código de variante. El resto usa `es` genérico.

### Precio por hora de audio

Convertido a dólares por hora. Mezcla cifras `[proveedor]` y `[terceros]`; varias páginas oficiales
cargan los importes por JavaScript y no se pudieron extraer.

| Servicio | Por hora | Nota |
| :--- | ---: | :--- |
| Groq, Whisper turbo | $0.04 | El más barato. Sin streaming. |
| Mistral Voxtral Transcribe 2 | $0.18 | |
| Azure, batch | ~$0.18 | [terceros], cifras divergentes |
| OpenAI gpt-4o-mini-transcribe | $0.18 | |
| AssemblyAI Universal-3.5 Pro | $0.21 | |
| ElevenLabs Scribe v2 | $0.22 | |
| Deepgram Nova-3 | ~$0.26 | |
| OpenAI gpt-transcribe | $0.27 | El recomendado por OpenAI |
| Speechmatics | ~$0.30 | Unidad ambigua en la página oficial |
| Amazon Transcribe, batch | $0.36 | |
| Google Speech-to-Text v2 | ~$0.96 | |
| Azure, tiempo real | ~$1.00 | El más caro |

### Retención cero

Disponible en autoservicio solo en **Groq**, que además no retiene por defecto. Con aprobación
previa en OpenAI y Mistral. Solo en plan Enterprise en ElevenLabs y Gladia. Azure afirma no
almacenar nada en tiempo real por diseño, y Speechmatics tampoco en tiempo real, aunque en lote
guarda siete días.

---

## 5. Alucinaciones

Solo dos proveedores publican afirmaciones concretas, y **ninguna está verificada por terceros
independientes**:

* **AssemblyAI** `[proveedor]`: alrededor de un 30 % menos de alucinaciones que Whisper. Un análisis
  externo señala que no publican la metodología de esa métrica.
* **OpenAI** `[proveedor]`: mejora de tasa de error, y su propia guía de migración **advierte de
  «alucinación de palabras clave»**, es decir, insertar términos sugeridos como contexto que nadie
  llegó a decir. Ese aviso es directamente relevante aquí, porque esta herramienta pasa un
  vocabulario largo como contexto inicial.

Deepgram, ElevenLabs, Mistral, Google, Amazon y Azure no mencionan el problema. Gladia y
Speechmatics lo usan para criticar a sus competidores.

---

## 6. Transcripción nativa de Teams

Categoría aparte, y probablemente la más interesante para este caso.

* Las transcripciones se guardan **en el OneDrive del organizador**, dentro del inquilino de
  Microsoft 365 de la empresa, con caducidad por defecto de 120 días, configurable.
* `es-MX` está en la lista de idiomas soportados.
* México es geografía local para Microsoft 365, y con Residencia de Datos Avanzada hay compromiso
  contractual de residencia.
* Está incluida en los planes Business Standard, E3, E5 y similares. No requiere Copilot.
* **No hay API de reconocimiento de voz**: los resultados se leen con Microsoft Graph, en el
  endpoint de transcripciones de la reunión.
* Microsoft **no publica el diagrama de flujo** ni afirma explícitamente dónde termina el
  procesamiento.

**Acción recomendada:** preguntar a TI si la transcripción de Teams está habilitada en el inquilino
y si el organizador puede activarla. Si la respuesta es sí, es la vía con menos exposición y sin
trabajo de ingeniería, y esta herramienta puede quedarse para lo que Teams no da: las capturas de
pantalla por palabra clave y las notas en Markdown.
