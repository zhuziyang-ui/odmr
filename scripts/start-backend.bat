@echo off
setlocal EnableExtensions

pushd "%~dp0.."
if errorlevel 1 (
  echo Failed to enter project root: %~dp0..
  pause
  exit /b 1
)

echo Starting backend on http://127.0.0.1:8000 ...
echo Current directory: %CD%
echo.
python main.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Backend exited with code %EXIT_CODE%.
  pause
)
popd
exit /b %EXIT_CODE%
