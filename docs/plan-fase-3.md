# Plan de Implementación - Fase 3: Identificación de Participantes

Este documento define el alcance, las decisiones técnicas y los pasos concretos de la **Fase 3**
del proyecto **Recorder**: distinguir *quién* habla dentro del audio de la reunión.

---

## 1. Objetivo

Hoy la aplicación distingue dos fuentes por hardware: tu micrófono (`mic`, marcado con 🎤) y la
salida del sistema (`out`, todos los demás participantes mezclados por Teams).

La Fase 3 busca separar a los participantes **dentro** del canal `out`, para que una línea del
Markdown diga *quién* dijo la frase y no solo *cuándo*:

```markdown
- **09:14:22** **Bruno**: El manifiesto ya quedó separado por pedido.
- **09:14:41** 🎤 Falta probar el flujo de embarques.
- **09:15:03** **Chris**: Eso lo revisamos a nivel viaje, no a nivel PE.
```

---

## 2. Restricción física del problema

Teams entrega **un solo canal ya mezclado** al sistema operativo. Cuando el audio llega a WASAPI
loopback, todos los participantes remotos están sumados en la misma señal. **No existe información
de paneo, canal ni amplitud que permita separarlos** por análisis de señal simple.

La única vía es identificar la voz por su timbre, mediante huellas vectoriales (*speaker embeddings*).

---

## 3. Decisión técnica

Se evaluaron tres caminos:

| Opción | Cómo funciona | Veredicto |
| :--- | :--- | :--- |
| **Transcripción nativa de Teams** | Teams diariza y etiqueta por nombre en su backend. | **Verificar primero.** Si TI la habilita, gana en calidad y cuesta cero. Requiere licencia y permiso del organizador. |
| **Diarización genérica (pyannote.audio)** | Agrupa por similitud y etiqueta "hablante A/B" sin nombres. | **Descartada para vivo.** Modelo restringido en Hugging Face, pesado para CPU y no da nombres reales. |
| **Identificación por enrolamiento** | Se graba una vez la voz de cada compañero; cada fragmento se compara contra esas huellas. | **Elegida.** Da nombres reales, corre en CPU y el equipo del daily es fijo y pequeño. |

**Justificación:** el daily tiene siempre a las mismas cuatro o cinco personas. Enrolar una vez a
cada una convierte un problema de agrupamiento no supervisado (difícil) en uno de comparación
contra un catálogo cerrado (fácil y barato).

**Dependencia nueva:** `resemblyzer`. Corre sobre el `torch` CPU ya instalado y no requiere GPU.

---

## 4. Diseño del módulo

Se añade una capa nueva al pipeline, entre la captura y la inferencia de Whisper, respetando el
patrón productor-consumidor existente.

```
recorder/speakers/
├── __init__.py
├── embeddings.py    # voice_embedding(audio16k) -> vector; función pura
├── profiles.py      # alta, baja y persistencia de huellas en voices/<nombre>.npy
└── identifier.py    # SpeakerIdentifier.identify(audio) -> (nombre | None, confianza)
```

Reglas de diseño heredadas de la Fase 2:

* `embeddings.py` es **función pura**: entra audio, sale vector. Testeable sin micrófono.
* Las huellas viven en disco como `.npy`, **fuera de `config.json`**, que solo guarda la ruta y el umbral.
* Si la similitud máxima no supera el umbral, se devuelve `None` y la línea se escribe sin nombre.
  **Nunca se inventa un nombre.**

---

## 5. Puntos de integración

| Archivo | Cambio |
| :--- | :--- |
| `recorder/engine/models.py` | Añadir campos `speaker` y `confidence` a `AudioChunk` y `TranscriptionResult`. |
| `recorder/engine/whisper_worker.py` | Tras obtener el chunk y antes de transcribir, resolver el hablante cuando `kind == "out"`. Componer la línea con el nombre. |
| `recorder/config/schema.py` | Añadir `voices_dir`, `speaker_threshold` y `speakers_enabled`. |
| `recorder/ui/dialogs/` | Nuevo `speakers_dialog.py`: lista de voces enroladas, botón para grabar 15 s y alta de participante. |
| `recorder/ui/main_window.py` | Botón 👥 que abre el diálogo de voces. |

---

## 6. Pasos de implementación

Cada paso es un commit independiente y verificable.

1. **Huellas de voz.** Crear `embeddings.py` y `profiles.py`. Prueba unitaria: dos muestras de la
   misma voz superan el umbral de similitud, dos de voces distintas no lo superan.
2. **Identificador.** Crear `identifier.py` con carga de catálogo y búsqueda del vecino más cercano
   por similitud coseno. Prueba unitaria con vectores sintéticos, sin audio real.
3. **Configuración.** Extender `AppConfig` con los tres campos nuevos. Prueba de que un
   `config.json` viejo sigue cargando sin pérdida de datos.
4. **Enrolamiento.** Diálogo 👥 que graba 15 s del micrófono o de la salida y guarda la huella con
   nombre. Aceptación: enrolar dos voces y ver ambas en la lista tras reiniciar.
5. **Integración en el pipeline.** Enganchar el identificador en `whisper_worker.py`. Aceptación:
   una prueba con dos voces sintéticas distintas produce dos nombres distintos en el Markdown.
6. **Medición en un daily real.** Registrar aciertos y fallos sobre una reunión completa y ajustar
   el umbral. Sin este paso el módulo no se considera terminado.

---

## 7. Límites conocidos

* **Voces encimadas.** Si dos personas hablan al mismo tiempo, el fragmento mezcla ambos timbres.
  El identificador devolverá una sola persona, probablemente la más fuerte, o ninguna.
* **Enrolamiento obligatorio.** Una persona nueva en el equipo no se reconoce hasta que se graban
  sus 15 segundos.
* **Fragmentos cortos.** Por debajo de unos 3 segundos de voz la huella es inestable. Conviene no
  identificar fragmentos más cortos y dejarlos sin nombre.
* **Cambio de micrófono o auriculares** de un compañero altera su timbre y puede bajar la
  precisión. La solución es reenrolar.

---

## 8. Consideración de privacidad

Dos puntos que deben resolverse dentro de esta fase, no después:

* **Las huellas de voz son datos biométricos.** Se guardan solo en local, nunca se suben al
  repositorio. Añadir `voices/` a `.gitignore` en el primer paso.
* **Las capturas automáticas fotografían la pantalla completa.** Si en ese momento hay
  credenciales, cadenas de conexión o datos de cliente a la vista, quedan escritos en la carpeta de
  notas. Conviene que la carpeta de notas esté fuera de cualquier sincronización pública y valorar
  restringir la captura a un solo monitor.

---

## 9. Deuda técnica menor detectada

Hallazgos de la revisión posterior a la Fase 2, independientes del objetivo principal:

* **`AudioChunk` no se usa.** `whisper_worker.py` desempaqueta una tupla cruda `(t0, kind, audio)`
  en lugar de la dataclass ya definida en `engine/models.py`. Conviene unificarlo en el paso 5,
  que de todas formas toca esa estructura.
* **Colisión de nombres.** `recorder.py` y el paquete `recorder/` comparten nombre, así que
  `import recorder` resuelve al paquete y nunca al shim. No afecta a `daily` ni a
  `python recorder.py`, que funcionan por ejecución directa, pero impide importar el shim desde
  otro script.
* **Sin dependencias declaradas.** No existe `requirements.txt`. Al añadir `resemblyzer` conviene
  crearlo con las cinco dependencias reales.
