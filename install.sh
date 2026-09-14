#!/usr/bin/env bash
# Recorder solo funciona en Windows (usa WASAPI y ctypes.windll), asi que este
# script no es una segunda implementacion del instalador: es una envoltura fina
# para quien, por costumbre, escriba `./install.sh` desde Git Bash en Windows.
# Toda la logica real vive en install.ps1 y se ejecuta con Windows PowerShell.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$DIR/install.ps1" "$@"
