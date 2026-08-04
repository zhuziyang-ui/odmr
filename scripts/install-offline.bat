@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Install Python + frontend deps from an offline-bundle folder (no internet).
rem Usage:
rem   scripts\install-offline.bat
rem   scripts\install-offline.bat D:\odmr-offline\offline-bundle

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"

if "%~1"=="" (
  set "BUNDLE=%ROOT%\offline-bundle"
) else (
  set "BUNDLE=%~f1"
)

set "WHEELS=%BUNDLE%\python-wheels"
set "REQ=%BUNDLE%\requirements.txt"
if not exist "%REQ%" set "REQ=%ROOT%\requirements.txt"
set "NODE_MODULES_BAK=%BUNDLE%\frontend-node_modules"
set "NPM_CACHE=%BUNDLE%\npm-cache"

echo.
echo === ODMR offline install ===
echo Project : %ROOT%
echo Bundle  : %BUNDLE%
echo.

if not exist "%BUNDLE%" (
  echo [ERROR] offline bundle not found: %BUNDLE%
  echo Usage: scripts\install-offline.bat [path-to-offline-bundle]
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not in PATH. Install Python from bundle\installers first.
  exit /b 1
)

echo [1/3] Install Python packages from wheels ...
if not exist "%WHEELS%" (
  echo [ERROR] missing %WHEELS%
  exit /b 1
)

python -m pip install --upgrade pip --no-index --find-links="%WHEELS%" 2>nul
python -m pip install --no-index --find-links="%WHEELS%" -r "%REQ%"
if errorlevel 1 (
  echo [ERROR] pip offline install failed.
  echo Check Python version matches the machine that built the wheels.
  exit /b 1
)

echo.
echo [2/3] Install frontend deps ...
if not exist "%ROOT%\frontend" (
  echo [ERROR] frontend directory missing.
  exit /b 1
)

if exist "%NODE_MODULES_BAK%" (
  echo Using bundled frontend-node_modules ...
  if exist "%ROOT%\frontend\node_modules" rmdir /S /Q "%ROOT%\frontend\node_modules"
  xcopy /E /I /Q /Y "%NODE_MODULES_BAK%" "%ROOT%\frontend\node_modules" >nul
  if errorlevel 1 (
    echo [ERROR] failed to copy node_modules
    exit /b 1
  )
  echo node_modules restored.
) else (
  where npm.cmd >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] npm.cmd not found and no frontend-node_modules in bundle.
    exit /b 1
  )
  pushd "%ROOT%\frontend"
  if exist "%NPM_CACHE%" (
    echo Trying npm offline with cache: %NPM_CACHE%
    call npm.cmd ci --offline --cache "%NPM_CACHE%"
    if errorlevel 1 call npm.cmd install --offline --cache "%NPM_CACHE%"
  ) else (
    echo [ERROR] No frontend-node_modules and no npm-cache in bundle.
    popd
    exit /b 1
  )
  if errorlevel 1 (
    echo [ERROR] npm offline install failed. Prefer packing node_modules on a Windows PC.
    popd
    exit /b 1
  )
  popd
)

echo.
echo [3/3] Self-check ...
python -c "from backend.app.main import app; print('backend:', app.title)"
if errorlevel 1 (
  echo [ERROR] backend import failed.
  exit /b 1
)

if not exist "%ROOT%\frontend\node_modules" (
  echo [ERROR] frontend\node_modules still missing.
  exit /b 1
)

echo.
echo Offline install OK.
echo Start with:  start.bat
echo Frontend:    http://127.0.0.1:5173
echo Backend:     http://127.0.0.1:8000/docs
echo.
if /I not "%~1"=="silent" if /I not "%~2"=="silent" pause
exit /b 0
