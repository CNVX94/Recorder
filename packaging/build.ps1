<#
.SYNOPSIS
    Construye Recorder como ejecutable de Windows (carpeta Recorder\ con Recorder.exe y daily.exe)
    y, si hay Inno Setup, su instalador.

.DESCRIPTION
    - Busca Python 3.10 o superior, igual que install.ps1.
    - Crea (o reutiliza) un entorno virtual de construccion en %LOCALAPPDATA%\RecorderBuild\venv
      e instala ahi requirements.txt y PyInstaller con version fija. No toca el .venv del repo.
    - Ejecuta packaging\recorder.spec con PyInstaller. La salida (dist), los temporales (build) y
      la cache van tambien a %LOCALAPPDATA%\RecorderBuild, nunca dentro del repositorio: esta en
      OneDrive y sincronizaria cientos de MB.
    - Prueba el resultado: daily.exe --selftest y daily.exe --help.
    - Si encuentra ISCC.exe (Inno Setup 6 o 7, por maquina, por usuario o en el PATH), compila
      packaging\recorder.iss y deja el instalador en %LOCALAPPDATA%\RecorderBuild\installer.
      Si no lo encuentra, dice como instalarlo y termina bien con la carpeta onedir.
    Se puede ejecutar varias veces: reutiliza el entorno virtual y la cache de PyInstaller.

    Que lleva el ejecutable y que no, tamanos y como publicarlo: docs/empaquetado.md.

.PARAMETER Limpio
    Construccion desde cero: borra temporales, salida, instalador y cache de PyInstaller antes
    de empezar (--clean). El entorno virtual se conserva; pip solo reinstala lo que cambie.

.PARAMETER SinInstalador
    Se detiene tras la carpeta onedir aunque Inno Setup este instalado.

.EXAMPLE
    .\packaging\build.ps1
    Carpeta onedir + instalador (si hay Inno Setup).

.EXAMPLE
    .\packaging\build.ps1 -Limpio -SinInstalador
    Solo la carpeta onedir, construida desde cero.
#>
[CmdletBinding()]
param(
    [switch]$Limpio,
    [switch]$SinInstalador
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Spec = Join-Path $PSScriptRoot "recorder.spec"
$Iss = Join-Path $PSScriptRoot "recorder.iss"

# Todo fuera del repositorio y con ruta corta (pip falla con rutas muy largas: MAX_PATH).
$BuildRoot = Join-Path $env:LOCALAPPDATA "RecorderBuild"
$VenvDir = Join-Path $BuildRoot "venv"
$WorkDir = Join-Path $BuildRoot "build"
$DistDir = Join-Path $BuildRoot "dist"
$InstallerDir = Join-Path $BuildRoot "installer"
$CacheDir = Join-Path $BuildRoot "cache"
$Salida = Join-Path $DistDir "Recorder"   # el nombre lo fija COLLECT(name=...) en recorder.spec

# Versiones fijas: las que se probaron con esta receta. Subirlas a proposito, no por accidente.
$PyInstallerVersion = "6.22.3"
$HooksContribVersion = "2026.8"

function Write-Step { param([string]$Texto) Write-Host ""; Write-Host "==> $Texto" -ForegroundColor Cyan }
function Write-Ok { param([string]$Texto) Write-Host "    OK: $Texto" -ForegroundColor Green }
function Write-Err { param([string]$Texto) Write-Host "    ERROR: $Texto" -ForegroundColor Red }
function Write-Aviso { param([string]$Texto) Write-Host "    AVISO: $Texto" -ForegroundColor Yellow }

# pip y PyInstaller escriben su registro en stderr. Con la salida redirigida, Windows PowerShell
# 5.1 lo convierte en errores y "Stop" cortaria el script aunque el programa termine bien: para
# los ejecutables se decide solo por $LASTEXITCODE.
function Invoke-Nativo {
    param([Parameter(Mandatory)] [scriptblock]$Bloque)
    $previo = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Bloque } finally { $ErrorActionPreference = $previo }
}

function Format-MB {
    param([long]$Bytes)
    return ("{0:N0} MB" -f ($Bytes / 1MB))
}

function Get-TamanoCarpeta {
    param([string]$Ruta)
    $suma = (Get-ChildItem -LiteralPath $Ruta -Recurse -File | Measure-Object -Property Length -Sum).Sum
    if (-not $suma) { $suma = 0 }
    return [long]$suma
}

# ---------------------------------------------------------------------------
# 1. Python 3.10 o superior (el mismo criterio que install.ps1)
# ---------------------------------------------------------------------------
Write-Step "Buscando Python 3.10 o superior..."

function Find-Python {
    $candidatos = @(
        [PSCustomObject]@{ Exe = "python"; Args = @() },
        [PSCustomObject]@{ Exe = "py"; Args = @("-3") }
    )
    foreach ($c in $candidatos) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $verTexto = $null
        try {
            $verTexto = & $c.Exe @($c.Args) -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        } catch {
            $verTexto = $null
        }
        if ($LASTEXITCODE -ne 0 -or -not $verTexto) { continue }
        $verTexto = ([string]$verTexto).Trim()
        $partes = $verTexto.Split(".")
        $mayor = [int]$partes[0]
        $menor = [int]$partes[1]
        if ($mayor -gt 3 -or ($mayor -eq 3 -and $menor -ge 10)) {
            return [PSCustomObject]@{ Exe = $c.Exe; Args = $c.Args; Version = $verTexto }
        } else {
            Write-Aviso "Se encontro Python $verTexto via '$($c.Exe)', pero hace falta 3.10 o superior."
        }
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Write-Err "No se encontro Python 3.10 o superior en el PATH."
    Write-Host "    Instala Python 3.10+ desde https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "    (marca la casilla 'Add python.exe to PATH' durante la instalacion)." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Python $($Python.Version) encontrado ('$($Python.Exe)')."

# ---------------------------------------------------------------------------
# 2. Entorno virtual de construccion y dependencias
# ---------------------------------------------------------------------------
Write-Step "Preparando el entorno virtual de construccion en '$VenvDir'..."

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $VenvPython) {
    Write-Ok "Ya existe, se reutiliza."
} else {
    New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
    & $Python.Exe @($Python.Args) -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Write-Err "No se pudo crear el entorno virtual en '$VenvDir'."
        exit 1
    }
    Write-Ok "Entorno virtual creado."
}

Write-Step "Instalando dependencias y PyInstaller $PyInstallerVersion (la primera vez tarda varios minutos)..."
Invoke-Nativo { & $VenvPython -m pip install --upgrade pip --quiet }
if ($LASTEXITCODE -ne 0) {
    Write-Aviso "No se pudo actualizar pip, se continua con la version del entorno virtual."
}
$Requirements = Join-Path $RepoRoot "requirements.txt"
Invoke-Nativo {
    & $VenvPython -m pip install --quiet -r $Requirements "pyinstaller==$PyInstallerVersion" "pyinstaller-hooks-contrib==$HooksContribVersion"
}
if ($LASTEXITCODE -ne 0) {
    Write-Err "Fallo la instalacion de dependencias. Revisa el mensaje de pip de mas arriba."
    exit 1
}
Write-Ok "Dependencias y PyInstaller listos."

# ---------------------------------------------------------------------------
# 3. Version e icono
# ---------------------------------------------------------------------------
Write-Step "Leyendo la version e icono..."

$InitPy = Join-Path $RepoRoot "recorder\__init__.py"
$coincidencia = Select-String -LiteralPath $InitPy -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $coincidencia) {
    Write-Err "No se encontro __version__ en '$InitPy'."
    exit 1
}
$Version = $coincidencia.Matches[0].Groups[1].Value
Write-Ok "Recorder $Version."

$Icono = Join-Path $RepoRoot "recorder\assets\recorder.ico"
if (Test-Path $Icono) {
    Write-Ok "Icono: $Icono"
} else {
    Write-Aviso "No existe el icono; se genera con packaging\generar_icono.py."
    & $VenvPython (Join-Path $PSScriptRoot "generar_icono.py")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Icono)) {
        Write-Err "No se pudo generar el icono."
        exit 1
    }
}

# ---------------------------------------------------------------------------
# 4. PyInstaller (onedir)
# ---------------------------------------------------------------------------
if ($Limpio) {
    Write-Step "Limpiando construcciones anteriores..."
    foreach ($carpeta in @($WorkDir, $Salida, $InstallerDir, $CacheDir)) {
        if (Test-Path $carpeta) {
            Remove-Item -LiteralPath $carpeta -Recurse -Force
            Write-Ok "Borrado '$carpeta'."
        }
    }
}

Write-Step "Construyendo con PyInstaller (suele tardar 1 o 2 minutos)..."
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
$env:PYINSTALLER_CONFIG_DIR = $CacheDir   # su cache de binarios, tambien fuera del repo
$argsPyInstaller = @("-m", "PyInstaller", "--noconfirm", "--distpath", $DistDir, "--workpath", $WorkDir)
if ($Limpio) { $argsPyInstaller += "--clean" }
$argsPyInstaller += $Spec

$crono = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-Nativo { & $VenvPython @argsPyInstaller }
$crono.Stop()
if ($LASTEXITCODE -ne 0) {
    Write-Err "PyInstaller termino con codigo $LASTEXITCODE. Revisa su salida de mas arriba."
    exit 1
}
$ExeVentana = Join-Path $Salida "Recorder.exe"
$ExeTerminal = Join-Path $Salida "daily.exe"
if (-not (Test-Path $ExeVentana) -or -not (Test-Path $ExeTerminal)) {
    Write-Err "PyInstaller termino pero faltan Recorder.exe o daily.exe en '$Salida'."
    exit 1
}
$tamano = Get-TamanoCarpeta $Salida
Write-Ok ("Carpeta '{0}' lista en {1:N0} s ({2})." -f $Salida, $crono.Elapsed.TotalSeconds, (Format-MB $tamano))

# ---------------------------------------------------------------------------
# 5. Pruebas de humo del ejecutable
# ---------------------------------------------------------------------------
Write-Step "Probando el ejecutable..."

Invoke-Nativo { $script:salidaSelftest = (& $ExeTerminal --selftest | Out-String) }
if ($LASTEXITCODE -ne 0 -or $salidaSelftest -notmatch "selftest ok") {
    Write-Err "daily.exe --selftest fallo (codigo $LASTEXITCODE):"
    Write-Host $salidaSelftest
    exit 1
}
Write-Ok "daily.exe --selftest: $($salidaSelftest.Trim().Split("`n")[-1].Trim())"

Invoke-Nativo { $script:salidaAyuda = (& $ExeTerminal --help | Out-String) }
if ($LASTEXITCODE -ne 0 -or $salidaAyuda -notmatch "uso: daily") {
    Write-Err "daily.exe --help fallo (codigo $LASTEXITCODE):"
    Write-Host $salidaAyuda
    exit 1
}
foreach ($comando in @("menu", "config", "calibrar", "sintesis", "recomendar")) {
    if ($salidaAyuda -notmatch "\b$comando\b") {
        Write-Err "daily.exe --help no lista el subcomando '$comando': falta un modulo en el ejecutable."
        exit 1
    }
}
Write-Ok "daily.exe --help lista todos los subcomandos."

# ---------------------------------------------------------------------------
# 6. Instalador (Inno Setup), si esta disponible
# ---------------------------------------------------------------------------
function Find-Iscc {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $raices = @(${env:ProgramFiles(x86)}, $env:ProgramFiles, (Join-Path $env:LOCALAPPDATA "Programs")) | Where-Object { $_ }
    foreach ($raiz in $raices) {
        foreach ($nombre in @("Inno Setup 7", "Inno Setup 6")) {
            $ruta = Join-Path (Join-Path $raiz $nombre) "ISCC.exe"
            if (Test-Path $ruta) { return $ruta }
        }
    }
    return $null
}

$Instalador = $null
if ($SinInstalador) {
    Write-Step "Instalador omitido (-SinInstalador)."
} else {
    Write-Step "Buscando Inno Setup (ISCC.exe)..."
    $Iscc = Find-Iscc
    if (-not $Iscc) {
        Write-Aviso "No se encontro Inno Setup 6 o 7. La carpeta onedir ya esta lista; para el instalador:"
        Write-Host "        winget install JRSoftware.InnoSetup" -ForegroundColor Yellow
        Write-Host "    y vuelve a ejecutar packaging\build.ps1 (reutiliza lo construido)." -ForegroundColor Yellow
    } else {
        Write-Ok "Inno Setup: $Iscc"
        Write-Step "Compilando el instalador (LZMA2 solido; tarda un par de minutos)..."
        New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
        $cronoIss = [System.Diagnostics.Stopwatch]::StartNew()
        Invoke-Nativo {
            & $Iscc "/Qp" "/DMyAppVersion=$Version" "/DSourceDir=$Salida" "/DOutputDir=$InstallerDir" $Iss
        }
        $cronoIss.Stop()
        if ($LASTEXITCODE -ne 0) {
            Write-Err "ISCC termino con codigo $LASTEXITCODE. Revisa su salida de mas arriba."
            exit 1
        }
        $Instalador = Join-Path $InstallerDir "Recorder-$Version-setup.exe"
        if (-not (Test-Path $Instalador)) {
            Write-Err "ISCC termino pero no aparece '$Instalador'."
            exit 1
        }
        Write-Ok ("Instalador '{0}' listo en {1:N0} s ({2})." -f $Instalador, $cronoIss.Elapsed.TotalSeconds, (Format-MB (Get-Item $Instalador).Length))
    }
}

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
Write-Step "Construccion terminada."
Write-Host "    Carpeta onedir:  $Salida  ($(Format-MB $tamano))" -ForegroundColor White
Write-Host "                     Recorder.exe (ventana) y daily.exe (terminal)" -ForegroundColor White
if ($Instalador) {
    Write-Host "    Instalador:      $Instalador" -ForegroundColor White
}
Write-Host "    Para publicar un zip de la carpeta:" -ForegroundColor DarkGray
Write-Host "        Compress-Archive -Path '$Salida' -DestinationPath '$InstallerDir\Recorder-$Version-win64.zip'" -ForegroundColor DarkGray
