# Empaquetado: Recorder como ejecutable de Windows

Recorder se distribuye sin pedirle Python a nadie: una carpeta `Recorder\` con dos ejecutables y
un instalador que la deja en el equipo. Todo lo necesario vive en [`packaging/`](../packaging/).

| Archivo | Qué es |
| :--- | :--- |
| `packaging\build.ps1` | Construye la carpeta (PyInstaller) y, si hay Inno Setup, el instalador. |
| `packaging\recorder.spec` | La receta de PyInstaller: un análisis, una carpeta, dos ejecutables. |
| `packaging\recorder.iss` | El instalador (Inno Setup): por usuario, en español, con `daily` en el PATH. |
| `packaging\LEEME.txt` | La página que enseña el instalador (SmartScreen, primer uso, dónde queda cada cosa). |
| `packaging\generar_icono.py` | Genera `recorder\assets\recorder.ico` con Pillow (ya está en el repositorio). |

## Qué sale

* **`Recorder.exe`**: sin consola. Abre la ventana (es lo que hace `recorder.cli.app.arrancar` cuando
  `sys.stdout is None`).
* **`daily.exe`**: con consola. Es `daily`: grabar en la terminal, `daily menu`, `daily config`,
  `daily calibrar`, `daily sintesis`, `daily recomendar`, y también `--selftest` y `--recomendar`.
* Los dos comparten la carpeta `_internal\` (Python, dependencias y datos), así que la carpeta no
  se duplica. `Recorder.exe` y `daily.exe` llevan icono y la información de versión de Windows
  (Propiedades → Detalles), leída de `recorder/__init__.py` (`__version__`).
* **`Recorder-<versión>-setup.exe`**: el instalador, si Inno Setup está instalado.

## Cómo construir

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

| Parámetro | Efecto |
| :--- | :--- |
| `-SinInstalador` | Se detiene tras la carpeta onedir aunque haya Inno Setup. |
| `-Limpio` | Borra temporales, salida, instalador y caché de PyInstaller antes de empezar (`--clean`). El entorno virtual de construcción se conserva. |

Lo que hace, en orden:

1. Busca Python 3.10 o superior (`python`, y si no, `py -3`), como `install.ps1`.
2. Crea o reutiliza un entorno virtual **de construcción** en `%LOCALAPPDATA%\RecorderBuild\venv`
   e instala `requirements.txt` más `pyinstaller` y `pyinstaller-hooks-contrib` con versión fija
   (están en el propio `build.ps1`). No toca el `.venv` del repositorio.
3. Ejecuta `packaging\recorder.spec`. La salida va a `%LOCALAPPDATA%\RecorderBuild\dist\Recorder`,
   los temporales a `...\build` y la caché de PyInstaller a `...\cache`. **Nunca dentro del
   repositorio**: está en OneDrive y sincronizaría cientos de MB (y `pip` falla con rutas largas).
4. Prueba la carpeta: `daily.exe --selftest` (tiene que acabar en `selftest ok`) y `daily.exe --help`
   (tiene que listar todos los subcomandos; si falta uno, falta un módulo en el ejecutable).
5. Si encuentra `ISCC.exe` (Inno Setup 6 o 7, instalado por máquina, por usuario o en el PATH),
   compila el instalador en `%LOCALAPPDATA%\RecorderBuild\installer`. Si no:

   ```powershell
   winget install JRSoftware.InnoSetup
   ```

   y se vuelve a ejecutar `build.ps1`, que reutiliza lo ya construido.

Se puede ejecutar tantas veces como haga falta. La primera tarda varios minutos (descarga
`ctranslate2`, `onnxruntime`, `av`…); las siguientes, lo que tarde PyInstaller.

### Tamaños y tiempos medidos

Medidos en un sobremesa (i5-9500, 16 GB) con Python 3.12.10, PyInstaller 6.22.3 y hooks-contrib
2026.8, Recorder 2.0.0:

| Qué | Medida |
| :--- | :--- |
| `build.ps1` la primera vez (crear el entorno e instalar todo) | 219 s |
| Solo PyInstaller (carpeta onedir) | 94 s |
| Carpeta `Recorder\` | 265 MB, 1174 archivos (`Recorder.exe` y `daily.exe`, 11,5 MB cada uno) |
| Zip de la carpeta (`Compress-Archive`, nivel `Optimal`) | 112 MB, 42 s |
| Instalador (LZMA2 sólido) | pendiente de medir (hace falta Inno Setup) |
| Windows Defender (`MpCmdRun -Scan -ScanType 3` sobre la carpeta) | sin amenazas |

Lo que pesa, dentro de `_internal\`: `av.libs` (FFmpeg) 64 MB, `ctranslate2` 59 MB, `onnxruntime`
38 MB, `numpy` 26 MB, `PIL` 13 MB, `tokenizers` 8 MB y Tcl/Tk 7 MB. El código de Recorder y los
documentos no llegan a 1 MB.

## Qué va dentro y qué no

Dentro:

* `faster-whisper` con su VAD (`faster_whisper/assets/silero_vad_v6.onnx`, vía
  `collect_data_files`), `ctranslate2`, `onnxruntime`, `tokenizers`, `av`, `huggingface_hub`.
* `PyAudioWPatch` (WASAPI loopback), `Pillow`, `numpy`, `rich` y **`tkinter`** (la ventana lo
  necesita; no se excluye nunca).
* Los archivos del repositorio que el código busca por su ruta relativa, con esa misma ruta bajo
  `_internal\`: `tools\instalar_whispercpp.ps1`, `docs\*.md`, `recorder\assets\*` y
  `config.example.json`. En el ejecutable se resuelven bajo `sys._MEIPASS` (que en onedir es
  `_internal`).
* Los subcomandos de la terminal (`recorder.cli.configurar`, `calibrar`, `sintesis`,
  `recomendar`) se cargan por nombre con `importlib.import_module`, que PyInstaller no ve: el
  spec los declara con `collect_submodules("recorder")`. Si se añade un subcomando nuevo, entra
  solo.

Fuera, a propósito:

* **Los modelos de Whisper.** Se descargan la primera vez que se transcribe, a la caché de Hugging
  Face (`%USERPROFILE%\.cache\huggingface\hub`): ~500 MB `small`, ~1,5 GB `large-v3-turbo`. Meterlos
  haría el instalador de gigabytes y ataría a cada usuario a un modelo.
* **CUDA / cuDNN.** Quien tenga NVIDIA los instala aparte; sin ellos, Recorder transcribe en CPU
  (ver [presets-calidad.md](presets-calidad.md)).
* **whisper.cpp** (GPU AMD/Intel con Vulkan): se compila con `tools\instalar_whispercpp.ps1`, que
  va dentro de la carpeta instalada ([gpu-amd-vulkan.md](gpu-amd-vulkan.md)).
* **`hf_xet`** (9 MB): no carga congelado y `huggingface_hub` descarga por HTTP sin él.
* **UPX**: desactivado. Comprime poco estas DLL y dispara falsos positivos del antivirus.

## El instalador

`recorder.iss` es un instalador de Inno Setup (6.3 o superior, también 7) en español:

* **Por usuario, sin administrador** (`PrivilegesRequired=lowest`): instala en
  `%LOCALAPPDATA%\Programs\Recorder`. El diálogo deja elegir "para todos los usuarios" (entonces
  sí pide UAC y va a `Archivos de programa`).
* Accesos directos en el menú Inicio: **Recorder** (la ventana) y **Recorder (terminal)**, que
  abre `daily.exe menu`. Icono en el escritorio, opcional.
* **"Añadir `daily` a la terminal (PATH del usuario)"**, marcado por defecto: añade la carpeta de
  instalación al final de `HKCU\Environment\Path` **sin duplicarla y sin tocar el resto**, y la
  quita al desinstalar (código Pascal en el `.iss`). Con `ChangesEnvironment=yes` Windows avisa
  del cambio, así que una terminal **nueva** ya ve `daily`. Si se instaló para todos los usuarios,
  se usa el PATH del sistema.
* Al terminar ofrece abrir Recorder.
* **Desinstalar quita solo lo instalado.** Nunca borra `%APPDATA%\Recorder` (configuración),
  `%LOCALAPPDATA%\Recorder` (registros), las notas ni la caché de modelos.
* Al actualizar encima, `_internal\` se reemplaza entera para no dejar restos de versiones
  anteriores (la configuración nunca vive ahí).
* El `AppId` es un GUID fijo: así "Aplicaciones instaladas" reconoce la misma aplicación entre
  versiones.

`build.ps1` le pasa la versión (`/DMyAppVersion`), la carpeta onedir (`/DSourceDir`) y la salida
(`/DOutputDir`). Abierto en el IDE de Inno Setup sin esas definiciones, toma la carpeta de
`%LOCALAPPDATA%\RecorderBuild\dist\Recorder` y lee la versión del recurso de `Recorder.exe`.

## SmartScreen y firma de código

Los ejecutables **no están firmados**. Al ejecutar el instalador o `Recorder.exe` descargados de
internet, Windows SmartScreen muestra "Windows protegió su PC": hay que pulsar **Más información →
Ejecutar de todas formas** (`LEEME.txt` lo explica en el propio instalador). Solo pasa la primera
vez con cada archivo. Windows Defender no detecta nada en la carpeta (comprobado con
`MpCmdRun.exe -Scan -ScanType 3`).

Qué haría falta para que no salga el aviso:

* **Un certificado OV** (validación de organización) firma el ejecutable, pero **no quita el aviso
  de inmediato**: SmartScreen se fía por reputación, que se gana con descargas e instalaciones a lo
  largo de semanas. Cada versión nueva firmada con el mismo certificado hereda esa reputación.
* **Un certificado EV** daba reputación inmediata, pero desde 2024 Microsoft dejó de darle ese
  trato especial; hoy sirve como un OV con más requisitos.
* **Microsoft Artifact Signing** (antes Trusted Signing): firma en la nube de Microsoft con
  reputación inmediata y barato, pero la validación **individual** solo está abierta en algunos
  países; para una persona en México no está disponible por ahora. Con una empresa registrada sí
  se podría.
* **Microsoft Store**: un paquete MSIX publicado en la Store lo firma Microsoft y no pasa por
  SmartScreen. Es el camino más limpio si Recorder se publica para más gente; exige una cuenta de
  desarrollador y adaptar el empaquetado a MSIX.

Mientras tanto: sin firma, con el aviso explicado, y publicando el hash SHA-256 de cada archivo
junto con la versión para que quien quiera pueda comprobarlo.

## Publicar una versión

1. Subir `__version__` en `recorder/__init__.py` y confirmar el cambio.
2. Construir desde cero: `packaging\build.ps1 -Limpio` (con Inno Setup, sale también el
   instalador).
3. Hacer el zip de la carpeta y los hashes:

   ```powershell
   $v = "2.0.0"
   $b = "$env:LOCALAPPDATA\RecorderBuild"
   Compress-Archive -Path "$b\dist\Recorder" -DestinationPath "$b\installer\Recorder-$v-win64.zip"
   Get-FileHash "$b\installer\*" -Algorithm SHA256 | Format-Table Hash, Path -AutoSize
   ```

4. Etiqueta y *release* en GitHub, con el instalador, el zip y los hashes:

   ```powershell
   git tag -a "v$v" -m "Recorder $v"
   git push origin "v$v"
   gh release create "v$v" "$b\installer\Recorder-$v-setup.exe" "$b\installer\Recorder-$v-win64.zip" --title "Recorder $v" --notes "..."
   ```

   El zip sirve a quien no quiera instalador: se descomprime en cualquier carpeta y se ejecuta
   `Recorder.exe` o `daily.exe` desde ahí (sin `daily` en el PATH ni accesos directos).

### Más adelante: winget

Con el instalador publicado en una URL estable por versión (GitHub Releases lo da), Recorder se
puede ofrecer en `winget` (`winget install Recorder`) enviando un manifiesto al repositorio
`microsoft/winget-pkgs`. Lo que hace falta ya está: Inno Setup admite instalación silenciosa
(`/VERYSILENT /NORESTART`, que el manifiesto declara como `InstallerType: inno`), el `AppId` es
fijo y el instalador va con versión. `wingetcreate new <url del instalador>` genera el manifiesto
y abre el *pull request*; cada versión nueva es un `wingetcreate update`. No quita el aviso de
SmartScreen (winget ejecuta el mismo instalador), pero sí simplifica instalar y actualizar.

## Si algo falla

| Síntoma | Qué mirar |
| :--- | :--- |
| `daily.exe --help` no lista un subcomando | El módulo no entró en el ejecutable. `collect_submodules("recorder")` lo debería incluir; comprobar que el archivo está en `recorder/cli/` y que no falla al importarse (`warn-recorder.txt` en `%LOCALAPPDATA%\RecorderBuild\build\recorder`). |
| `Recorder.exe` se cierra sin ventana | Es un ejecutable sin consola: la excepción no se ve. Lanzar `daily.exe ventana` desde una terminal para ver el error, o mirar los registros en `%LOCALAPPDATA%\Recorder\logs`. |
| `daily recomendar` dice `(sin detectar) GPUs (Vulkan)` con `invalid choice: ...hardware.py` | La consulta de Vulkan relanza el propio programa con `--vulkan`; en el ejecutable eso lo tiene que atender la entrada (`recorder.py`) antes de repartir subcomandos. Si vuelve a salir, el código de entrada perdió ese atajo. |
| `pip` falla con rutas largas | Mantener la construcción en `%LOCALAPPDATA%\RecorderBuild` (ruta corta); una carpeta temporal profunda supera `MAX_PATH`. |
| Defender pone en cuarentena algo de `_internal` | Falso positivo con binarios (`ctranslate2`, `pyaudiowpatch`). Restaurar desde Defender y reconstruir con `-Limpio`. |
| El instalador no compila: `Spanish.isl` no existe | Inno Setup está instalado sin los idiomas; reinstalar con `winget install JRSoftware.InnoSetup`. |
