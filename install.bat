@echo off
rem Doble clic para instalar Recorder. Solo lanza install.ps1 saltandose la
rem politica de ejecucion de PowerShell PARA ESTE PROCESO, sin tocar la del sistema.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
