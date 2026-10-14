<#
.SYNOPSIS
    Compila whisper.cpp con Vulkan desde el codigo oficial y deja listo el motor para GPUs AMD.

.DESCRIPTION
    whisper.cpp no publica binarios Vulkan para Windows, asi que se compila aqui una etiqueta
    fija del repositorio oficial (github.com/ggml-org/whisper.cpp). Deja esta estructura:

        <Destino>\src       codigo fuente (etiqueta -Version)
        <Destino>\bin       whisper-server.exe y sus DLL
        <Destino>\models    ggml-<modelo>.bin y el VAD ggml-silero-v6.2.0.bin
        <Destino>\logs      registro del servidor (lo escribe Recorder)

    Requisitos que NO instala: Git, CMake, Visual Studio 2022/2026 con C++ y el Vulkan SDK
    (winget install KhronosGroup.VulkanSDK). Se puede ejecutar varias veces: no vuelve a
    clonar ni a descargar lo que ya esta.

    No uses una carpeta dentro de OneDrive: los modelos pesan varios GB.
    Ver docs/gpu-amd-vulkan.md.

.PARAMETER Destino
    Carpeta de instalacion. Es lo que va en "whispercpp_dir" de config.json.

.PARAMETER Version
    Etiqueta de whisper.cpp a compilar.

.PARAMETER Modelos
    Modelos ggml a descargar de huggingface.co/ggerganov/whisper.cpp.

.PARAMETER SinModelos
    Solo compila; no descarga modelos.

.PARAMETER ConfigPath
    El config.json en el que escribir "whispercpp_dir". Por defecto, el mismo que usa Recorder
    (recorder/rutas.py): la variable RECORDER_CONFIG si esta definida; si no, config.json junto a
    recorder.py cuando el script esta en el repositorio (desde el codigo), y si no (Recorder
    instalado, con el script en _internal\tools) %APPDATA%\Recorder\config.json.

.PARAMETER SoloConfig
    No compila ni descarga nada: solo escribe "whispercpp_dir" = -Destino (que debe existir) en el
    config.json. Para registrar una carpeta de whisper.cpp ya preparada, o para probar este paso.

.EXAMPLE
    .\tools\instalar_whispercpp.ps1 -Destino E:\whispercpp

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\Recorder\_internal\tools\instalar_whispercpp.ps1" -Destino E:\whispercpp
    Con Recorder instalado: deja whispercpp_dir en %APPDATA%\Recorder\config.json.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Destino,
    [string]$Version = "v1.9.4",
    [string[]]$Modelos = @("large-v3", "large-v3-turbo"),
    [switch]$SinModelos,
    [string]$ConfigPath = "",
    [switch]$SoloConfig
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Texto) Write-Host ""; Write-Host "==> $Texto" -ForegroundColor Cyan }
function Write-Ok { param([string]$Texto) Write-Host "    OK: $Texto" -ForegroundColor Green }
function Stop-Con { param([string]$Texto) Write-Host "    ERROR: $Texto" -ForegroundColor Red; exit 1 }

# El config.json que usa Recorder, con la misma regla que recorder/rutas.py (ruta_config).
function Get-RecorderConfigPath {
    if ($env:RECORDER_CONFIG) { return $env:RECORDER_CONFIG }
    $raiz = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $raiz "recorder.py")) { return Join-Path $raiz "config.json" }
    return Join-Path $env:APPDATA "Recorder\config.json"
}

# Escribe "whispercpp_dir": -Destino en el config.json (seccion 6). Solo se cambia esa clave, como
# texto: el resto del archivo (vocabulario, correcciones, formato) queda tal cual. Sin esta linea,
# la GPU no se usa aunque todo este instalado.
function Set-WhisperCppDir {
    if (-not $ConfigPath) { $ConfigPath = Get-RecorderConfigPath }
    $DestinoAbs = (Resolve-Path -LiteralPath $Destino).Path
    $par = '"whispercpp_dir": "' + (($DestinoAbs -replace '\\', '\\') -replace '"', '\"') + '"'
    if (Test-Path -LiteralPath $ConfigPath) {
        Write-Step "Guardando whispercpp_dir en $ConfigPath..."
        $texto = [IO.File]::ReadAllText($ConfigPath)
        $evaluador = [Text.RegularExpressions.MatchEvaluator] { param($m) $par }
        $clave = [regex]'"whispercpp_dir"\s*:\s*"(?:[^"\\]|\\.)*"'
        if ($clave.IsMatch($texto)) {
            $nuevo = $clave.Replace($texto, $evaluador, 1)
        } else {
            $nuevo = ([regex]'\{').Replace($texto, [Text.RegularExpressions.MatchEvaluator] { param($m) "{`r`n  $par," }, 1)
        }
        $valido = $true
        try { $null = $nuevo | ConvertFrom-Json } catch { $valido = $false }
        if ($valido) {
            [IO.File]::WriteAllText($ConfigPath, $nuevo, (New-Object Text.UTF8Encoding $false))
            Write-Ok "$par"
        } else {
            Write-Host "    AVISO: no se pudo editar $ConfigPath sin romperlo; anade a mano: $par" -ForegroundColor Yellow
        }
        Write-Step "Listo. Abre Recorder y en Opciones pulsa 'Usar recomendado' (o: daily recomendar --aplicar)."
    } else {
        Write-Step "Listo. Todavia no existe $ConfigPath (Recorder lo crea al arrancar); cuando exista, anade:"
        Write-Host "    $par" -ForegroundColor White
        Write-Host "    y en Opciones pulsa 'Usar recomendado'." -ForegroundColor White
    }
}

if ($SoloConfig) {
    if (-not (Test-Path -LiteralPath $Destino -PathType Container)) { Stop-Con "No existe la carpeta $Destino." }
    Set-WhisperCppDir
    exit 0
}

# Git y CMake escriben avisos en stderr. Con la salida redirigida, Windows PowerShell 5.1 los
# convierte en errores y "Stop" cortaria el script aunque el programa termine bien: para los
# ejecutables se decide solo por $LASTEXITCODE.
function Invoke-Nativo {
    param([Parameter(Mandatory)] [scriptblock]$Bloque)
    $previo = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Bloque } finally { $ErrorActionPreference = $previo }
}

# ---------------------------------------------------------------------------
# 1. Herramientas
# ---------------------------------------------------------------------------
Write-Step "Comprobando herramientas..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Stop-Con "Falta Git (winget install Git.Git)." }

$cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source
if (-not $cmake -and (Test-Path "$env:ProgramFiles\CMake\bin\cmake.exe")) { $cmake = "$env:ProgramFiles\CMake\bin\cmake.exe" }
if (-not $cmake) { Stop-Con "Falta CMake (winget install Kitware.CMake)." }

# Un SDK recien instalado no aparece en las variables de una terminal abierta antes.
if (-not $env:VULKAN_SDK) { $env:VULKAN_SDK = [Environment]::GetEnvironmentVariable("VULKAN_SDK", "Machine") }
if (-not $env:VULKAN_SDK -or -not (Test-Path "$env:VULKAN_SDK\Bin\glslc.exe")) {
    Stop-Con "Falta el Vulkan SDK (winget install KhronosGroup.VulkanSDK) o no se encuentra glslc.exe."
}
$env:PATH = "$env:VULKAN_SDK\Bin;$env:PATH"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere) -or -not (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)) {
    Stop-Con "Falta Visual Studio con el componente de C++ (MSVC x64)."
}
Write-Ok "Git, CMake ($cmake), Vulkan SDK ($env:VULKAN_SDK) y MSVC."

# ---------------------------------------------------------------------------
# 2. Codigo fuente
# ---------------------------------------------------------------------------
Write-Step "Codigo fuente de whisper.cpp $Version..."
$src = Join-Path $Destino "src"
if (-not (Test-Path (Join-Path $src ".git"))) {
    Invoke-Nativo { git clone --depth 1 --branch $Version https://github.com/ggml-org/whisper.cpp $src }
    if ($LASTEXITCODE -ne 0) { Stop-Con "No se pudo clonar whisper.cpp." }
} else {
    $actual = Invoke-Nativo { git -C $src describe --tags --exact-match 2>$null }
    if ($actual -ne $Version) {
        Invoke-Nativo { git -C $src fetch --depth 1 origin tag $Version; git -C $src checkout --quiet $Version }
        if ($LASTEXITCODE -ne 0) { Stop-Con "No se pudo cambiar a $Version." }
    }
}
Write-Ok "$src en $(Invoke-Nativo { git -C $src rev-parse --short HEAD })."

# ---------------------------------------------------------------------------
# 3. Compilacion con Vulkan
# ---------------------------------------------------------------------------
Write-Step "Compilando con Vulkan (varios minutos la primera vez)..."
$build = Join-Path $src "build"
Invoke-Nativo { & $cmake -S $src -B $build -DGGML_VULKAN=ON -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF }
if ($LASTEXITCODE -ne 0) { Stop-Con "Fallo la configuracion de CMake." }
Invoke-Nativo { & $cmake --build $build --config Release --target whisper-server whisper-bench -j $env:NUMBER_OF_PROCESSORS }
if ($LASTEXITCODE -ne 0) { Stop-Con "Fallo la compilacion." }

$salida = Join-Path $build "bin\Release"
if (-not (Test-Path (Join-Path $salida "whisper-server.exe"))) { Stop-Con "No aparece whisper-server.exe en $salida." }
$bin = Join-Path $Destino "bin"
New-Item -ItemType Directory -Force $bin | Out-Null
Copy-Item -Path (Join-Path $salida "*") -Destination $bin -Include *.exe, *.dll -Force
Write-Ok "Binarios en $bin."

# ---------------------------------------------------------------------------
# 4. Modelos
# ---------------------------------------------------------------------------
$models = Join-Path $Destino "models"
New-Item -ItemType Directory -Force $models | Out-Null
if (-not $SinModelos) {
    Write-Step "Modelos..."
    $descargas = @(@{ Repo = "ggml-org/whisper-vad"; Archivo = "ggml-silero-v6.2.0.bin" })
    foreach ($m in $Modelos) { $descargas += @{ Repo = "ggerganov/whisper.cpp"; Archivo = "ggml-$m.bin" } }
    foreach ($d in $descargas) {
        $url = "https://huggingface.co/$($d.Repo)/resolve/main/$($d.Archivo)"
        $archivo = Join-Path $models $d.Archivo
        $esperado = [int64](Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing).Headers["Content-Length"]
        if ((Test-Path $archivo) -and (Get-Item $archivo).Length -eq $esperado) { Write-Ok "$($d.Archivo) ya descargado."; continue }
        Invoke-Nativo { curl.exe -L --fail --show-error -C - -o $archivo $url }
        if ($LASTEXITCODE -ne 0) { Stop-Con "No se pudo descargar $($d.Archivo)." }
        Write-Ok "$($d.Archivo) ($([math]::Round((Get-Item $archivo).Length / 1MB)) MB)."
    }
}

# ---------------------------------------------------------------------------
# 5. Que GPU toma whisper.cpp
# ---------------------------------------------------------------------------
# whisper-bench no admite -dev: muestra lo que haria whisper-server sin -dev (su dispositivo 0) y
# la lista de GPUs con su numero, que es el que va en "whispercpp_device" si se quiere otra.
$bench = Join-Path $bin "whisper-bench.exe"
$modeloBench = @("large-v3-turbo", "large-v3") | ForEach-Object { Join-Path $models "ggml-$_.bin" } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ((Test-Path $bench) -and $modeloBench) {
    Write-Step "Comprobando la GPU con whisper-bench ($([IO.Path]::GetFileName($modeloBench)), unos segundos)..."
    $salidaBench = Invoke-Nativo { & $bench -m $modeloBench -t 4 2>&1 | ForEach-Object { "$_" } }
    $lineas = @($salidaBench | Where-Object { $_ -match "ggml_vulkan: \d+ = |using Vulkan\d+ backend|no GPU found|encode time" })
    foreach ($l in $lineas) { Write-Host "    $($l.Trim())" -ForegroundColor White }
    $usada = $salidaBench | Select-String -Pattern "using Vulkan(\d+) backend" | Select-Object -First 1
    if (-not $usada) {
        Write-Host "    AVISO: whisper.cpp no encontro una GPU de Vulkan; Recorder usara la CPU." -ForegroundColor Yellow
    } else {
        $n = $usada.Matches[0].Groups[1].Value
        if ($salidaBench -match "ggml_vulkan: $n = .*\| uma: 1") {
            Write-Host "    AVISO: el dispositivo $n es una GPU integrada. Recorder no la usa en automatico: elige la" -ForegroundColor Yellow
            Write-Host "    dedicada (o esta, si la mediste) en Opciones > 'GPU de whisper.cpp'." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "    (Sin whisper-bench o sin modelos: no se comprueba la GPU.)" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 6. whispercpp_dir en config.json
# ---------------------------------------------------------------------------
Set-WhisperCppDir
