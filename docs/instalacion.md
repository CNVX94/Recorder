# Guia de instalacion rapida

Recorder es una aplicacion de escritorio para Windows (usa WASAPI y `ctypes.windll`,
no funciona en macOS/Linux). Esta guia sirve para dos lectores: una persona instalando
la herramienta a mano, y un agente automatizado que necesite instalarla sin supervision.
Los pasos y los archivos son los mismos para los dos; cambia solo el nivel de detalle.

---

## Para una persona

### Requisitos

* Windows 10 o Windows 11.
* [Python 3.10 o superior](https://www.python.org/downloads/) instalado y accesible como
  `python` desde una terminal (al instalarlo, marca la casilla **"Add python.exe to PATH"**).
* Conexion a internet la primera vez: para descargar las dependencias de Python y, la
  primera vez que transcribas, el modelo de Whisper.

### Pasos

1. Clona o descarga el repositorio de Recorder.
2. En el explorador de archivos, haz **doble clic en `install.bat`**.

   Se abrira una ventana de terminal que instala todo automaticamente. `install.bat` no
   hace nada por si mismo: solo lanza `install.ps1` saltandose la politica de ejecucion
   de PowerShell **para esa ventana**, sin cambiar ninguna configuracion del sistema.
3. Espera a que termine. La ventana va mostrando cada paso (`==>`) y si salio bien (`OK:`).
   La instalacion de dependencias (`faster-whisper`, `numpy`, etc.) es la parte que mas
   tarda; puede llevar varios minutos la primera vez, menos las siguientes porque reutiliza
   la cache de `pip`. Despues detecta tu equipo (CPU, memoria, GPU, bateria) y deja en
   `config.json` la calidad y los hilos que le convienen; si ya tenias un `config.json`, solo
   te dice cual seria y lo puedes aplicar en Opciones con **Usar recomendado**
   ([recomendacion-hardware.md](recomendacion-hardware.md)). Con una GPU AMD o Intel, la
   transcripcion en GPU se instala aparte: [gpu-amd-vulkan.md](gpu-amd-vulkan.md).
4. Al final veras un aviso de que la primera transcripcion descarga el modelo de Whisper
   configurado (puede pesar mas de 1 GB segun el modelo elegido en `config.json`). Necesita
   internet solo esa vez; despues queda guardado en tu equipo.
5. Presiona una tecla para cerrar la ventana (lo pide `install.bat` al terminar).
6. Abre una terminal **nueva** de PowerShell y escribe:

   ```powershell
   daily
   ```

   Deberia abrirse la ventana de Recorder. Si la terminal ya estaba abierta antes de
   instalar, recarga el perfil sin cerrarla:

   ```powershell
   . $PROFILE
   ```

### Si algo falla

| Sintoma | Causa probable | Que hacer |
| :--- | :--- | :--- |
| `ERROR: No se encontro Python 3.10 o superior en el PATH.` | Python no esta instalado, o se instalo sin marcar "Add to PATH". | Instala Python desde python.org marcando esa casilla y vuelve a hacer doble clic en `install.bat`. |
| La ventana se cierra sola sin mostrar nada, o Windows abre la Microsoft Store al ejecutar `python`. | El `python` del PATH es el "alias" que abre la Store, no un Python real. | Instala Python desde python.org (no desde la Store) y asegurate de que sea el primero en el PATH. |
| `Fallo 'pip install -r requirements.txt'` con un error de red. | Sin internet, o una red corporativa que bloquea PyPI. | Comprueba la conexion (o el proxy) y vuelve a ejecutar `install.bat`; no borra nada de lo que ya se instalo. |
| `AVISO: Ya existe una funcion 'daily' en ... fuera de los marcadores` | Tu perfil de PowerShell ya tenia una funcion `daily` propia, de antes de usar este instalador. | Abre el perfil (`notepad $PROFILE`), decide si quieres conservar tu version o borrarla, y si la borras vuelve a ejecutar `install.bat` para que quede la del entorno virtual. |
| `daily` da "no se reconoce como nombre de cmdlet" tras instalar. | La terminal es la misma de antes de instalar y no recargo el perfil. | Abre una terminal nueva, o ejecuta `. $PROFILE` en la actual. |
| Windows Defender u otro antivirus pone en cuarentena algo dentro de `.venv`. | Falso positivo, ocurre a veces con paquetes que traen binarios (`pyaudiowpatch`, `ctranslate2`). | Restaura el archivo desde el antivirus y anadelo a las exclusiones, o vuelve a ejecutar `install.bat` para que `pip` lo reinstale. |

Ejecutar `install.bat` mas de una vez es seguro: no duplica nada, no reinstala el entorno
virtual si ya existe, y nunca toca un `config.json` que ya tengas.

Esta guia es la de Recorder **desde el codigo**, y ahi `config.json` vive en la raiz del
repositorio. Con Recorder **instalado** como ejecutable (`Recorder.exe` / `daily.exe`, sin Python)
la configuracion esta en `%APPDATA%\Recorder\config.json`, que se crea solo en el primer arranque, y
los fallos quedan en `%LOCALAPPDATA%\Recorder\logs\recorder.log`
([architecture.md](architecture.md), §2.8).

### Desinstalar

Recorder no deja nada fuera de su propia carpeta salvo el comando `daily`. Para quitarlo
todo:

1. Borra la carpeta `.venv` dentro del repositorio (libera el espacio del entorno virtual
   y sus dependencias).
2. Abre tu perfil de PowerShell (`notepad $PROFILE`, y si usas tambien PowerShell 7,
   `pwsh -NoProfile -Command "notepad $PROFILE"`) y borra el bloque completo entre las
   lineas:

   ```powershell
   # >>> recorder >>>
   ...
   # <<< recorder <<<
   ```
3. Si tambien quieres borrar tu configuracion personal (vocabulario, dispositivos,
   carpetas), borra `config.json` en la raiz del repositorio. Es opcional: no hace falta
   para quitar el comando `daily`.
4. Borra la carpeta del repositorio si ya no la necesitas.

---

## Para un agente de IA

Pasos deterministas para instalar Recorder sin supervision humana, con como verificar
cada uno.

1. **Clonar el repositorio** (si no esta ya clonado):

   ```powershell
   git clone <url-del-repositorio> "<ruta-destino>"
   ```

2. **Ejecutar el instalador** desde la raiz del repositorio clonado. No uses `install.bat`
   (abre una ventana y hace `pause`, pensado para un humano); llama directamente a
   `install.ps1` con PowerShell:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "<ruta-destino>\install.ps1"
   ```

   Codigo de salida esperado: `0`. Compruebalo con `$LASTEXITCODE` inmediatamente despues
   (en la misma sesion de PowerShell que lo lanzo).

   Para no tocar el perfil de PowerShell real de la maquina (por ejemplo, en una prueba
   o en una maquina compartida), pasa un perfil alternativo y omite PowerShell 7:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "<ruta-destino>\install.ps1" -ProfilePath "<ruta-perfil-temporal>.ps1" -SkipPwsh
   ```

3. **Verificar el entorno virtual**: debe existir el interprete de Python dentro del repo.

   ```powershell
   Test-Path "<ruta-destino>\.venv\Scripts\python.exe"   # debe devolver True
   ```

4. **Verificar `config.json`**: debe existir tras la instalacion (se crea a partir de
   `config.example.json` si no existia ya). En uno recien creado, el instalador ya escribio
   la configuracion recomendada para la maquina (`==> Detectando el equipo...`, lineas
   `Equipo:`, `Recomendado:` y `Motivo:`); en uno previo solo la muestra. Para verla de
   nuevo sin tocar nada:

   ```powershell
   Test-Path "<ruta-destino>\config.json"   # debe devolver True
   & "<ruta-destino>\.venv\Scripts\python.exe" "<ruta-destino>\recorder.py" --recomendar
   ```

5. **Verificar el bloque en el perfil de PowerShell usado** (el real, o el que se haya
   pasado con `-ProfilePath`): debe contener las lineas `# >>> recorder >>>` y
   `# <<< recorder <<<`, con una funcion `daily` en medio que referencie
   `.venv\Scripts\python.exe` y `recorder.py` de esa misma carpeta.

   ```powershell
   Select-String -Path "<ruta-perfil>" -Pattern "# >>> recorder >>>"   # debe encontrar 1 coincidencia
   ```

6. **Verificar que la aplicacion arranca de verdad**, sin abrir la interfaz grafica, con
   el selftest integrado:

   ```powershell
   & "<ruta-destino>\.venv\Scripts\python.exe" "<ruta-destino>\recorder.py" --selftest
   ```

   Salida esperada: la ultima linea es `selftest ok (Fase 2 Modular)` y el codigo de
   salida es `0`. Si falla, el problema esta en el entorno (audio/pantalla no disponibles
   en la maquina, por ejemplo en una VM sin dispositivos WASAPI) y no en la instalacion en
   si; revisa el mensaje de la asercion que fallo.

7. **Reejecucion**: el instalador es idempotente. Volver a ejecutar el paso 2 con el mismo
   `-ProfilePath` no debe duplicar el bloque del perfil (sigue habiendo una sola aparicion
   de `# >>> recorder >>>`) ni sobrescribir un `config.json` que ya existiera.

### Notas para el agente

* Si el paso 2 termina con codigo distinto de `0`, el mensaje `ERROR:` impreso en la
  salida indica la causa (Python ausente/antiguo, o fallo de `pip install`). No sigas
  con los pasos siguientes hasta resolverlo.
* Si aparece `AVISO: Ya existe una funcion 'daily' en ... fuera de los marcadores`, el
  perfil indicado no se modifico a proposito, para no pisar una funcion `daily` previa
  que no vino de este instalador. Eso no es un fallo del instalador: decide si conviene
  renombrar/borrar esa funcion antes de reintentar, o usar otro `-ProfilePath`.
* `pip install -r requirements.txt` necesita salida a internet (PyPI). Si la maquina no
  tiene, replica la instalacion con un indice de paquetes local o una cache de `pip` ya
  poblada.
