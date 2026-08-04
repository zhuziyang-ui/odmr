@echo off
setlocal EnableExtensions

pushd "%~dp0..\frontend"
if errorlevel 1 (
  echo Failed to enter frontend directory: %~dp0..\frontend
  pause
  exit /b 1
)

echo Starting frontend on http://127.0.0.1:5173 ...
echo Current directory: %CD%
echo.
npm.cmd run dev -- --host 127.0.0.1 --port 5173
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Frontend exited with code %EXIT_CODE%.
  pause
)
popd
exit /b %EXIT_CODE%
