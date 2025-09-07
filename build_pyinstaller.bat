@echo off
setlocal

cd /d "%~dp0%"

echo === Compilando con PyInstaller...
pyinstaller --noconsole --onefile --noupx --name="NVIDIA DLSS Unlocker" "NVIDIA_DLSS_Unlocker_App.pyw"

echo.
echo === ¡COMPILACIÓN TERMINADA! ===
pause
