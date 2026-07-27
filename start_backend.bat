@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title NV ODMR Backend
echo ============================================
echo  NV Measurement Backend
echo  URL: http://127.0.0.1:8000
echo  Docs: http://127.0.0.1:8000/docs
echo ============================================
echo.

call "%~dp0free_ports.bat" 8000

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found on PATH.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate .venv
  pause
  exit /b 1
)

REM Skip full reinstall when core packages are already importable.
python -c "import fastapi,uvicorn" >nul 2>&1
if errorlevel 1 (
  echo Installing Python dependencies...
  python -m pip install -q -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
  )
) else (
  echo Python dependencies already present.
)

echo.
echo Starting uvicorn on 127.0.0.1:8000 ...
echo.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
set "EC=%ERRORLEVEL%"
echo.
if not "%EC%"=="0" (
  echo [ERROR] Backend exited with code %EC%
) else (
  echo Backend exited.
)
pause
exit /b %EC%
