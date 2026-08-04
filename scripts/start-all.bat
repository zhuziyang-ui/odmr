@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"

call "%SCRIPT_DIR%stop-services.bat" silent

echo.
echo Project root: %ROOT%
echo Launching backend and frontend in new windows...
echo.

start "NV Backend" cmd /k call "%SCRIPT_DIR%start-backend.bat"
ping -n 3 127.0.0.1 >nul
start "NV Frontend" cmd /k call "%SCRIPT_DIR%start-frontend.bat"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Close the "NV Backend" / "NV Frontend" windows to stop a service,
echo or double-click stop.bat to kill both by port.
echo.
if /I not "%~1"=="silent" pause
