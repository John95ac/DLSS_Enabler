@echo off
echo === PASO 1: Compilando con cx_Freeze...
cxfreeze "NVIDIA_DLSS_Unlocker_App.pyw" --target-dir dist --base-name=Win32GUI

echo === PASO 2: Compilando con Nuitka...
nuitka --standalone --windows-disable-console --enable-plugin=tk-inter --remove-output "NVIDIA_DLSS_Unlocker_App.pyw"

echo.
echo === COMPILACIÓN PARCIAL COMPLETA. ===
