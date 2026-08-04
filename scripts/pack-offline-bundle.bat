@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Pack offline install assets on a networked Windows PC.
rem Output: <project>\offline-bundle\

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"
set "BUNDLE=%ROOT%\offline-bundle"
set "WHEELS=%BUNDLE%\python-wheels"
set "INSTALLERS=%BUNDLE%\installers"
set "NPM_CACHE=%BUNDLE%\npm-cache"
set "NODE_MODULES_BAK=%BUNDLE%\frontend-node_modules"

echo.
echo === ODMR offline bundle packer ===
echo Project: %ROOT%
echo Output : %BUNDLE%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found in PATH.
  exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm.cmd not found. Install Node.js first.
  exit /b 1
)

if not exist "%ROOT%\requirements.txt" (
  echo [ERROR] requirements.txt missing: %ROOT%\requirements.txt
  exit /b 1
)

if not exist "%BUNDLE%" mkdir "%BUNDLE%"
if not exist "%WHEELS%" mkdir "%WHEELS%"
if not exist "%INSTALLERS%" mkdir "%INSTALLERS%"

echo [1/4] Download Python wheels into python-wheels ...
python -m pip download -r "%ROOT%\requirements.txt" -d "%WHEELS%"
if errorlevel 1 (
  echo [ERROR] pip download failed. Check network / package names.
  exit /b 1
)
copy /Y "%ROOT%\requirements.txt" "%BUNDLE%\requirements.txt" >nul

echo.
echo [2/4] Prepare frontend offline assets ...
pushd "%ROOT%\frontend"
if errorlevel 1 (
  echo [ERROR] cannot enter frontend\
  exit /b 1
)

if not exist "node_modules" (
  echo node_modules missing, running npm.cmd install first ...
  call npm.cmd install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    popd
    exit /b 1
  )
)

echo Copying frontend\node_modules -^> offline-bundle\frontend-node_modules ...
if exist "%NODE_MODULES_BAK%" rmdir /S /Q "%NODE_MODULES_BAK%"
xcopy /E /I /Q /Y "node_modules" "%NODE_MODULES_BAK%" >nul
if errorlevel 1 (
  echo [WARN] xcopy node_modules failed; try manual copy later.
) else (
  echo node_modules backup OK.
)

for /f "delims=" %%C in ('npm.cmd config get cache 2^>nul') do set "NPM_SYS_CACHE=%%C"
if defined NPM_SYS_CACHE (
  if exist "!NPM_SYS_CACHE!" (
    echo Copying npm cache from !NPM_SYS_CACHE! ...
    if exist "%NPM_CACHE%" rmdir /S /Q "%NPM_CACHE%"
    xcopy /E /I /Q /Y "!NPM_SYS_CACHE!" "%NPM_CACHE%" >nul
  )
)
popd

echo.
echo [3/4] Write offline README ...
(
  echo ODMR offline bundle
  echo ===================
  echo.
  echo 1. Install Python + Node from installers\ ^(add Python to PATH^).
  echo 2. Copy project source to the offline PC.
  echo 3. In project root run:
  echo      scripts\install-offline.bat ^<path-to-this-offline-bundle^>
  echo 4. start.bat
  echo.
  echo Manual Python install:
  echo   python -m pip install --no-index --find-links=python-wheels -r requirements.txt
  echo.
  echo Manual frontend ^(preferred^):
  echo   xcopy /E /I /Y frontend-node_modules PROJECT\frontend\node_modules
  echo.
  echo See project OFFLINE_SETUP.md for full guide.
) > "%BUNDLE%\README-OFFLINE.txt"

echo.
echo [4/4] Installer checklist
echo.
echo Please MANUALLY download and put these into:
echo   %INSTALLERS%
echo.
echo   - python-3.xx.x-amd64.exe   ^(same major as this PC if possible^)
echo   - node-vxx.x.x-x64.msi      ^(LTS^)
echo.
python --version
node --version
npm.cmd --version
echo.
echo Bundle ready: %BUNDLE%
echo Copy the whole offline-bundle folder + project source via USB.
echo.
if /I not "%~1"=="silent" pause
exit /b 0
