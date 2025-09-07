@echo off
setlocal

cd /d "%~dp0%"

echo === PASO 3: Moviendo archivos generados por Nuitka...
if exist "NVIDIA_DLSS_Unlocker_App.dist" (
    if not exist dist\lib mkdir dist\lib
    xcopy /E /Y /I "NVIDIA_DLSS_Unlocker_App.dist\" "dist\lib\" >nul
    echo Carpeta movida: NVIDIA_DLSS_Unlocker_App.dist -> dist\lib
    rmdir /S /Q "NVIDIA_DLSS_Unlocker_App.dist"
    echo Carpeta eliminada: NVIDIA_DLSS_Unlocker_App.dist
) else (
    echo ❌ ERROR: No se encontró la carpeta NVIDIA_DLSS_Unlocker_App.dist
)

echo === PASO 4: Eliminando duplicados...
if exist "dist\lib\NVIDIA_DLSS_Unlocker_App.exe" (
    echo Eliminando duplicado: NVIDIA_DLSS_Unlocker_App.exe
    del /Q "dist\lib\NVIDIA_DLSS_Unlocker_App.exe"
) else (
    echo ℹ️ No se encontró duplicado: NVIDIA_DLSS_Unlocker_App.exe
)

echo.
echo ===============================
echo ✅ ¡PROCESO COMPLETADO EXITOSAMENTE!
echo ===============================
pause
