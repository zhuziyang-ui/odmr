@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
echo Building portable package (this may take several minutes)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-portable.ps1"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo Build failed with code %EC%.
  pause
  exit /b %EC%
)
echo.
echo Output: dist-portable\ODMR_Console\
echo Copy that folder to USB and double-click 双击启动.bat
if /I not "%~1"=="silent" pause
exit /b 0
