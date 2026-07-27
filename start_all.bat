@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title NV ODMR Start All
echo ============================================
echo  Starting backend + frontend
echo  Backend : http://127.0.0.1:8000
echo  Frontend: http://127.0.0.1:5173
echo  Accuracy: http://127.0.0.1:5173/accuracy
echo ============================================
echo.

call "%~dp0free_ports.bat" 8000 5173

echo Launching backend window...
start "NV ODMR Backend" cmd /k call "%~dp0start_backend.bat"

echo Waiting for backend health (up to ~90s)...
set /a tries=0
:wait_backend
set /a tries+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/system/health' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Backend is up.
  goto start_frontend
)
if %tries% GEQ 45 (
  echo [WARN] Backend not ready after ~90s. Starting frontend anyway.
  goto start_frontend
)
REM ping is more reliable than timeout when stdin is redirected
ping -n 3 127.0.0.1 >nul
goto wait_backend

:start_frontend
echo Launching frontend window...
start "NV ODMR Frontend" cmd /k call "%~dp0start_frontend.bat"

echo Waiting for frontend (up to ~60s)...
set /a tries=0
:wait_frontend
set /a tries+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:5173/' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Frontend is up.
  goto open_browser
)
if %tries% GEQ 30 (
  echo [ERROR] Frontend did not become ready on http://127.0.0.1:5173
  echo Check the "NV ODMR Frontend" window for npm/vite errors.
  echo.
  pause
  exit /b 1
)
ping -n 3 127.0.0.1 >nul
goto wait_frontend

:open_browser
echo.
echo ============================================
echo  Ready
echo  Open: http://127.0.0.1:5173/accuracy
echo ============================================
echo.
start "" "http://127.0.0.1:5173/accuracy"
ping -n 4 127.0.0.1 >nul
exit /b 0
