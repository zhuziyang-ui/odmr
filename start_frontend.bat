@echo off
setlocal
cd /d "%~dp0"

title NV ODMR Frontend
echo ============================================
echo  NV Measurement Frontend
echo  URL: http://127.0.0.1:5173
echo  Accuracy: http://127.0.0.1:5173/accuracy
echo ============================================
echo.

call "%~dp0free_ports.bat" 5173

cd /d "%~dp0frontend"
if errorlevel 1 (
  echo [ERROR] cannot cd to frontend
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js LTS.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Installing frontend dependencies...
  call npm.cmd install
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
)

echo.
echo Starting Vite...
echo.
call npm.cmd run dev:local
echo.
echo Frontend exited.
pause
