<#
.SYNOPSIS
    Instalador de Recorder para Windows PowerShell 5.1+.

.DESCRIPTION
    - Comprueba que haya Python 3.10 o superior.
    - Crea (o reutiliza) un entorno virtual en .venv dentro del repo e instala
      requirements.txt ahi, no en el Python global.
    - Copia config.example.json a config.json solo si config.json no existe todavia.
      Nunca lo sobrescribe: ahi vive la configuracion personal.
    - Anade la funcion `daily` al perfil de PowerShell (y al de PowerShell 7 si esta
      instalado), apuntando siempre al Python del entorno virtual y al recorder.py de
      esta misma carpeta (via $PSScriptRoot, sin rutas fijas).
    Se puede ejecutar varias veces sin duplicar nada ni perder datos.

.PARAMETER ProfilePath
    Perfil de Windows PowerShell a modificar. Por defecto, $PROFILE (el perfil real
    de quien ejecuta el instalador). Pensado para pruebas: se le puede pasar la ruta
    de un perfil temporal para no tocar el perfil real de nadie.

.PARAMETER PwshProfilePath
    Perfil de PowerShell 7 (pwsh) a modificar. Si no se indica, se intenta detectar
    llamando a `pwsh` (si esta instalado) y preguntandole su propio $PROFILE.

.PARAMETER SkipPwsh
    No toca ningun perfil de PowerShell 7, aunque pwsh este instalado.

.EXAMPLE
    .\install.ps1
    Instalacion normal, para quien lo ejecuta.

.EXAMPLE
    .\install.ps1 -ProfilePath C:\temp\perfil_prueba.ps1 -SkipPwsh
    Instalacion de prueba: no toca el perfil real ni el de PowerShell 7.
#>
[CmdletBinding()]
param(
    [string]$ProfilePath = $PROFILE,
    [string]$PwshProfilePath = "",
    [switch]$SkipPwsh
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$MarcadorInicio = "# >>> recorder >>>"
$MarcadorFin = "# <<< recorder <<<"

function Write-Step {
    param([string]$Texto)
    Write-Host ""
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Texto)
    Write-Host "    OK: $Texto" -ForegroundColor Green
}

function Write-Err {
    param([string]$Texto)
    Write-Host "    ERROR: $Texto" -ForegroundColor Red
}

function Write-Aviso {
    param([string]$Texto)
    Write-Host "    AVISO: $Texto" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 1. Python 3.10 o superior
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
    Write-Host "    (marca la casilla 'Add python.exe to PATH' durante la instalacion)" -ForegroundColor Yellow
    Write-Host "    y vuelve a ejecutar install.bat." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Python $($Python.Version) encontrado ('$($Python.Exe)')."

# ---------------------------------------------------------------------------
# 2. Entorno virtual (.venv) e instalacion de requirements.txt
# ---------------------------------------------------------------------------
Write-Step "Preparando el entorno virtual en .venv..."

$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (Test-Path $VenvPython) {
    Write-Ok "Ya existe .venv, se reutiliza."
} else {
    & $Python.Exe @($Python.Args) -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Write-Err "No se pudo crear el entorno virtual en '$VenvDir'."
        exit 1
    }
    Write-Ok "Entorno virtual creado en '$VenvDir'."
}

Write-Step "Instalando dependencias (requirements.txt)... puede tardar varios minutos la primera vez."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Aviso "No se pudo actualizar pip, se continua con la version que trae el entorno virtual."
}

$RequirementsPath = Join-Path $RepoRoot "requirements.txt"
& $VenvPython -m pip install -r $RequirementsPath
if ($LASTEXITCODE -ne 0) {
    Write-Err "Fallo 'pip install -r requirements.txt'. Revisa el mensaje de pip de mas arriba."
    exit 1
}
Write-Ok "Dependencias instaladas en .venv."

# ---------------------------------------------------------------------------
# 3. config.json a partir de la plantilla (sin pisar uno que ya exista)
# ---------------------------------------------------------------------------
Write-Step "Preparando config.json..."

$ConfigPath = Join-Path $RepoRoot "config.json"
$ConfigExamplePath = Join-Path $RepoRoot "config.example.json"

if (Test-Path $ConfigPath) {
    Write-Ok "config.json ya existe, no se toca (ahi vive tu configuracion personal)."
} elseif (Test-Path $ConfigExamplePath) {
    Copy-Item -Path $ConfigExamplePath -Destination $ConfigPath
    Write-Ok "config.json creado a partir de config.example.json."
} else {
    Write-Aviso "No se encontro config.example.json en '$RepoRoot'; Recorder arrancara con sus valores de fabrica."
}

# ---------------------------------------------------------------------------
# 4. Comando `daily` en el perfil de PowerShell
# ---------------------------------------------------------------------------
Write-Step "Registrando el comando 'daily' en el perfil de PowerShell..."

$RecorderPy = Join-Path $RepoRoot "recorder.py"

function Set-DailyFunction {
    param(
        [Parameter(Mandatory)] [string]$RutaPerfil,
        [Parameter(Mandatory)] [string]$PythonVenv,
        [Parameter(Mandatory)] [string]$ScriptRecorder,
        [Parameter(Mandatory)] [string]$Etiqueta
    )

    $bloque = @"
$MarcadorInicio
# Instalado por install.ps1 del proyecto Recorder. No editar a mano:
# se reemplaza por completo cada vez que se ejecuta el instalador.
function daily {
    & "$PythonVenv" "$ScriptRecorder" @args
}
$MarcadorFin
"@

    $contenidoPrevio = ""
    if (Test-Path -LiteralPath $RutaPerfil) {
        $leido = Get-Content -LiteralPath $RutaPerfil -Raw
        if ($leido) { $contenidoPrevio = $leido }
    }

    $patronBloque = "(?ms)^" + [regex]::Escape($MarcadorInicio) + ".*?^" + [regex]::Escape($MarcadorFin) + "\r?\n?"
    $sinBloque = [regex]::Replace($contenidoPrevio, $patronBloque, "")

    if ($sinBloque -match "(?im)^\s*function\s+daily\b") {
        Write-Aviso "Ya existe una funcion 'daily' en '$RutaPerfil' ($Etiqueta) fuera de los marcadores $MarcadorInicio / $MarcadorFin."
        Write-Aviso "No se toca ese perfil para no pisarla. Borra o renombra esa funcion a mano y vuelve a ejecutar el instalador."
        return $false
    }

    # Split-Path -LiteralPath no admite -Parent en Windows PowerShell 5.1 (son
    # conjuntos de parametros distintos ahi); [System.IO.Path] no tiene ese problema.
    $carpetaPerfil = [System.IO.Path]::GetDirectoryName($RutaPerfil)
    if ($carpetaPerfil -and -not (Test-Path -LiteralPath $carpetaPerfil)) {
        New-Item -ItemType Directory -Path $carpetaPerfil -Force | Out-Null
    }

    $base = $sinBloque.TrimEnd("`r", "`n")
    if ([string]::IsNullOrEmpty($base)) {
        $nuevoContenido = $bloque + "`r`n"
    } else {
        $nuevoContenido = $base + "`r`n`r`n" + $bloque + "`r`n"
    }

    Set-Content -LiteralPath $RutaPerfil -Value $nuevoContenido -NoNewline -Encoding UTF8
    return $true
}

$okWindowsPS = Set-DailyFunction -RutaPerfil $ProfilePath -PythonVenv $VenvPython -ScriptRecorder $RecorderPy -Etiqueta "Windows PowerShell"
if ($okWindowsPS) {
    Write-Ok "Comando 'daily' registrado en '$ProfilePath'."
}

if (-not $SkipPwsh) {
    $rutaPwsh = $PwshProfilePath
    if (-not $rutaPwsh) {
        $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
        if ($pwshCmd) {
            try {
                $rutaPwsh = & pwsh -NoLogo -NoProfile -Command "`$PROFILE"
                if ($rutaPwsh) { $rutaPwsh = ([string]$rutaPwsh).Trim() }
            } catch {
                $rutaPwsh = ""
            }
        }
    }
    if ($rutaPwsh) {
        $okPwsh = Set-DailyFunction -RutaPerfil $rutaPwsh -PythonVenv $VenvPython -ScriptRecorder $RecorderPy -Etiqueta "PowerShell 7 (pwsh)"
        if ($okPwsh) {
            Write-Ok "Comando 'daily' tambien registrado en '$rutaPwsh' (PowerShell 7)."
        }
    } else {
        Write-Host "    (PowerShell 7 / pwsh no detectado, se omite su perfil.)" -ForegroundColor DarkGray
    }
}

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------
Write-Step "Instalacion terminada."
Write-Host "    Abre una terminal NUEVA de PowerShell y escribe 'daily' para abrir Recorder." -ForegroundColor White
Write-Host "    (En esta misma terminal tambien funciona tras ejecutar: . `$PROFILE)" -ForegroundColor White
Write-Host ""
Write-Host "    Aviso: la primera vez que transcribas, Recorder descarga el modelo de Whisper" -ForegroundColor Yellow
Write-Host "    configurado en config.json (segun el modelo, puede pesar mas de 1 GB). Hace" -ForegroundColor Yellow
Write-Host "    falta conexion a internet solo esa primera vez; despues queda en cache local." -ForegroundColor Yellow
