# Documento de Planificación y Especificación - Fase 2

Este documento registra los objetivos, decisiones de diseño y resultados de la **Fase 2** del proyecto **Recorder**.

---

## 1. Objetivos de la Fase 2

1. **Investigación y Diagnóstico:**
   * Evaluar la deuda técnica del script monolítico original de 431 líneas (`recorder.py`).
   * Identificar puntos de acoplamiento entre hilos de captura de audio, inferencia de IA, persistencia de archivos y la interfaz de usuario.
2. **Definición Arquitectónica:**
   * Diseñar una arquitectura modular robusta basada en Clean Architecture y un modelo Productor-Consumidor por eventos.
   * Aislar la lógica de procesamiento digital de señales (DSP), inferencia Whisper y reglas de filtrado de texto.
3. **Módulo de Calibración Anti-Alucinaciones (Fine-Tuning Personal):**
   * Dotar al usuario de herramientas para neutralizar alucinaciones por silencio, bucles de repetición y errores fonéticos de jerga técnica.
   * Diseñar una interfaz interactiva con probador en vivo (sandbox).
4. **Retrocompatibilidad Completa:**
   * Asegurar que el comando `daily` en PowerShell siga funcionando con exactitud y que el archivo de configuración `config.json` preexistente se mantenga sin pérdidas de datos.

---

## 2. Decisiones de Diseño

| Módulo | Enfoque Anterior | Enfoque Fase 2 | Beneficio |
| :--- | :--- | :--- | :--- |
| **Configuración** | Diccionario mutable global `cfg` | Dataclass `AppConfig` + `ConfigManager` | Validación de tipos, defaults seguros y guardado atómico. |
| **Audio** | Hilos globales con funciones sueltas | `AudioCaptureManager` | Encapsulación de estado, inicio/parada limpios y reinicio de dispositivos sin reiniciar la app. |
| **Filtros NLP** | Funciones `clean()` y `fix()` sueltas | Pipeline modular (`TextPipeline`) | Componible, testeable con unit tests y configurable en caliente. |
| **Fine-Tuning** | Edición manual de JSON o campos planos | Ventana `TuningDialog` con Sandbox | Calibración visual inmediata y validación de reglas antes de guardar. |
| **Entrada CLI** | Script único monolítico | Paquete `recorder/` + shim `recorder.py` | Compatible tanto con `python -m recorder` como con `daily` o `recorder.py --selftest`. |

---

## 3. Estado de Cumplimiento y Pruebas

* [x] Estructura modular creada en `recorder/`.
* [x] Suite de pruebas automatizadas en `tests/` con 15 casos de prueba aprobados.
* [x] Compatibilidad con `daily` en PowerShell verificada desde cualquier directorio.
* [x] Interfaz gráfica validada con arranque y parada limpios.
* [x] Documentación completa en `README.md` y carpeta `docs/`.
