# Presets de calidad de transcripción

Elegir modelo, haz (`beam_size`), dispositivo y precisión a mano exige leer
`rendimiento.md` y `hardware-y-modelos.md` cada vez. Este documento describe los
cuatro presets (Baja, Media, Alta, Extra) que empaquetan esa decisión, pensados para
que **subir de calidad al cambiar de equipo sea elegir un nombre, no cuatro
parámetros**.

---

## 1. El mapeo

| Preset | Modelo | Haz | Dispositivo | Precisión | Qué implica |
| :--- | :--- | ---: | :--- | :--- | :--- |
| **Baja** | `small` | 1 | cpu | int8 | La más rápida en CPU: **~5,4x** tiempo real medido en reposo (`rendimiento.md` §2.2). No acumula retraso ni compartiendo el equipo con una videollamada. Es la que más confunde nombres propios y anglicismos técnicos. |
| **Media** | `small` | 5 | cpu | int8 | **~3,0x** medido en reposo. Mismo modelo que Baja, más precisa gracias al haz 5; sigue yendo holgada en CPU. Es la configuración de fábrica de `AppConfig`. |
| **Alta** | `large-v3-turbo` | 5 | cpu | int8 | La mejor calidad sin GPU. **~1,0x** en reposo, **0,33x medido con Teams abierto** (`rendimiento.md` §2.1, fila 2): al ritmo justo del tiempo real, se atrasa con cualquier carga extra. Es la configuración recomendada hoy para una CPU sin GPU (`hardware-y-modelos.md` §6). |
| **Extra** | `large-v3` | 5 | cuda | float16 | La mejor calidad de la familia Whisper. **Exige GPU NVIDIA con CUDA**: en esta CPU `large-v3` va a 0,3x-0,4x, muy por debajo del tiempo real (`hardware-y-modelos.md` §1.4); con una GPU de 6 GB o más va a 8x-15x (§2.2). No tiene sentido sin GPU salvo para dejar la configuración lista antes de mover el equipo o el `config.json` a una máquina que sí la tenga. |

El mapeo completo vive como datos en `recorder/config/schema.py`
(`QUALITY_PRESETS`), no en la interfaz: cada preset es un `QualityPreset` con
`model`, `beam_size`, `device`, `compute_type` y un texto (`summary`) que explica la
compensación velocidad/calidad. `medium` queda fuera a propósito: `rendimiento.md` y
`hardware-y-modelos.md` lo descartan por ser peor que `large-v3-turbo` en velocidad y
calidad a la vez.

`beam_size` en GPU casi no mueve el tiempo (10-25 % según `hardware-y-modelos.md`
§2.2), así que Extra usa haz 5 igual que Alta: no hay motivo para sacrificar precisión
ahí.

---

## 2. Cómo se reconoce el preset de una configuración

No existe un campo `quality_preset` guardado en `config.json`. En su lugar,
`preset_key_for_config(config)` compara los cuatro campos que definen un preset
(`model`, `beam_size`, `device`, `compute_type`) contra la tabla y devuelve la clave
que coincide, o `None` si ninguna lo hace. Es una función pura: no lee disco ni toca
hardware, así que se puede probar sin GUI y sin GPU.

Consecuencias de este diseño:

* **Personalizado no es un quinto preset, es la ausencia de coincidencia.** Si alguien
  afinó `beam_size` a mano a 3, o edita `config.json` directamente, el diálogo de
  Opciones lo muestra como "Personalizado" y, si se guarda sin tocar el desplegable,
  **no se modifica ningún campo de modelo/haz/dispositivo/precisión**.
* **Una configuración vieja se reconoce igual.** Un `config.json` de antes de este
  cambio no tiene `device` ni `compute_type`; `AppConfig.from_dict` los completa con
  sus valores de fábrica (`"cpu"`, `"int8"`), que es exactamente el comportamiento de
  siempre. La configuración de referencia del usuario, `large-v3-turbo` con haz 5, cae
  en `device="cpu"`/`compute_type="int8"` por defecto y se reconoce como **Alta**.
* **Guardar sin cambiar el preset es un no-op.** Si el desplegable ya muestra el
  preset detectado y se pulsa Guardar, `apply_preset` vuelve a escribir los mismos
  cuatro valores: no hay diferencia observable.

---

## 3. Detección de hardware, sin dependencias nuevas

`ctranslate2.get_cuda_device_count()` (ya instalado como dependencia de
`faster-whisper`, sin necesitar `torch`) dice cuántas GPUs CUDA ve el proceso ahora
mismo. `detect_cuda_device_count()` en `schema.py` envuelve esa llamada y devuelve
`0` ante cualquier fallo (biblioteca ausente, driver roto, lo que sea): es una
consulta puramente informativa para la interfaz y nunca debe romper el diálogo de
Opciones.

`preset_availability(key, cuda_device_count)` es la política pura correspondiente:
recibe el número de GPUs ya detectado (para poder testearla sin GPU) y devuelve si el
preset se puede usar aquí y, si no, por qué. Hoy solo **Extra** depende de esto; Baja,
Media y Alta corren en cualquier CPU y siempre están disponibles.

El diálogo de Opciones (`settings_dialog.py`) llama a `detect_cuda_device_count()` una
vez al abrirse y usa el resultado para:

1. Anotar en el propio desplegable qué preset no está disponible aquí
   (`"Extra (no disponible en este equipo)"`).
2. Mostrar en rojo, bajo el desplegable, por qué no lo está y qué pasa si se elige
   igual: *"Si se guarda igual, Recorder cae a CPU solo, sin romperse."*

Elegir Extra en un equipo sin GPU **sigue siendo una acción válida**: sirve para dejar
el `config.json` listo antes de copiarlo a una máquina con GPU (ver
`hardware-y-modelos.md` §5, la opción de delegar a un sobremesa con GPU en la red). No
se bloquea la selección; solo se advierte.

---

## 4. Qué hace `whisper_worker.py` si se pide GPU y no hay

**La decisión se toma antes de construir el modelo**, y el orden importa. `WhisperModel`
descarga los pesos **antes** de validar el dispositivo. Si la caída a CPU se decidiera
después del fallo, elegir Extra en un equipo sin GPU descargaría varios GB de `large-v3`
para acabar ejecutándolo en CPU a un tercio del tiempo real, que es justo el problema que
los presets pretenden evitar.

Por eso `TranscriberWorker.run()` llama primero a
`resolve_runtime(config, detect_cuda_device_count())`, una función pura de `schema.py` que
devuelve modelo, dispositivo, precisión, haz y aviso:

| Situación | Qué carga | Aviso |
| :--- | :--- | :--- |
| Preset de CPU (Baja, Media, Alta) | Lo configurado, sin cambios | Ninguno |
| Extra **con** GPU detectada | `large-v3` en CUDA, float16 | Ninguno |
| Extra **sin** GPU detectada | **El preset Alta completo**: `large-v3-turbo` en CPU, con su haz. Nunca se pide `large-v3` | En la cabecera, sugiriendo elegir un preset de CPU |
| Extra con GPU detectada **que no logra cargar** (driver, VRAM) | El mismo modelo en CPU, int8 | En la cabecera |

La caída sin GPU es al preset **entero**, no solo al dispositivo: cambiar solo el
dispositivo dejaría `large-v3` en CPU. El único caso en que se intenta CUDA y después se
reintenta en CPU es el último, cuando la GPU existe pero falla al cargar.

Lo prueban `tests/test_extra_fallback.py`, que verifica que sin GPU nunca se llega a pedir
`large-v3`, y `tests/test_quality_presets.py`, con el reintento cuando la GPU está presente
pero no carga.

---

## 5. Qué se cambió en el código

* `recorder/config/schema.py`: dos campos nuevos en `AppConfig` (`device: str = "cpu"`,
  `compute_type: str = "int8"`); `QualityPreset`, `QUALITY_PRESETS`, `PRESET_ORDER`,
  `CUSTOM_PRESET`; `preset_key_for_config`, `apply_preset`, `PresetAvailability`,
  `preset_availability`, `detect_cuda_device_count`.
* `recorder/engine/whisper_worker.py`: `WhisperModel` usa `self.config.device` y
  `self.config.compute_type` en vez de valores fijos, resueltos antes de construir el
  modelo como se describe en la sección 4.
* `recorder/ui/dialogs/settings_dialog.py`: la fila "Modelo Whisper" se sustituye por
  "Calidad de transcripción", con el preset detectado, un texto explicativo que
  cambia al elegir otro, y el aviso de no-disponibilidad para Extra. Guardar sin tocar
  el desplegable no modifica modelo/haz/dispositivo/precisión si el estado era
  Personalizado.
* `config.example.json`: documenta `"device": "cpu"` y `"compute_type": "int8"` junto
  a `model`/`beam_size` (la combinación que trae por defecto corresponde al preset
  Media).
* `tests/test_quality_presets.py`: mapeo de cada preset, reconocimiento de una
  configuración (incluida una sin `device`/`compute_type`, simulando un `config.json`
  viejo), viabilidad según el hardware detectado (sin GPU real), `detect_cuda_device_count`
  ante un `ctranslate2` simulado, y la caída a CPU del worker cuando se pide `cuda` y
  falla.

---

## 6. Qué no se verificó

* **Extra no se probó con una GPU real ni descargando `large-v3`**: pesa varios GB y
  en esta CPU no serviría de nada. Lo verificado es la lógica (mapeo, detección,
  caída a CPU) y el comportamiento de la interfaz en un equipo sin GPU.
* Las cifras de velocidad de la tabla son las de `rendimiento.md` y
  `hardware-y-modelos.md`, con sus mismas salvedades: la fila de Alta con Teams
  abierto se midió con carga ajena y no es una medida limpia; las de GPU son de
  terceros por analogía de hardware, no medidas en este proyecto.
