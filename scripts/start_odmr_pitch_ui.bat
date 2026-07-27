@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo ============================================
echo  NV ODMR A/B pitch interactive UI
echo  Repo: %CD%
echo  Browser: http://localhost:8501
echo ============================================
echo.

set "PYEXE="

REM Prefer known Anaconda with packages (avoids WindowsApps stub python)
if exist "D:\download\anaconda\python.exe" (
  "D:\download\anaconda\python.exe" -c "import streamlit,numpy,plotly" >nul 2>&1
  if not errorlevel 1 set "PYEXE=D:\download\anaconda\python.exe"
)

if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe" (
  "%USERPROFILE%\anaconda3\python.exe" -c "import streamlit,numpy,plotly" >nul 2>&1
  if not errorlevel 1 set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
)

if not defined PYEXE (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -c "import streamlit,numpy,plotly" >nul 2>&1
    if not errorlevel 1 set "PYEXE=py -3.12"
  )
)

if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import streamlit,numpy,plotly" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
  )
)

if not defined PYEXE if exist "D:\download\anaconda\python.exe" (
  set "PYEXE=D:\download\anaconda\python.exe"
)

if not defined PYEXE (
  echo [ERROR] No Python found. Install Anaconda or Python 3.11+.
  pause
  exit /b 1
)

echo Using: %PYEXE%
%PYEXE% -c "import sys; print('  ', sys.executable)"

%PYEXE% -c "import streamlit,numpy,plotly; v=plotly.__version__; assert v.startswith('5.'), v" >nul 2>&1
if errorlevel 1 (
  echo Installing / fixing chart deps: streamlit, numpy, plotly 5.x ...
  %PYEXE% -m pip install "streamlit>=1.28,<1.40" "numpy>=1.24" "plotly>=5.18,<6" "packaging>=16.8,<24" "tenacity>=8.1,<9"
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
  )
)

echo.
echo Starting Streamlit on http://localhost:8501
echo Defaults: B0=11 mT, FWHM=14 MHz, Earth=Wuhan ON
echo Close this window or Ctrl+C to stop.
echo.

REM Free port 8501 if a previous instance is still listening
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
  echo Stopping old process on 8501: PID %%P
  taskkill /F /PID %%P >nul 2>&1
)

REM Skip Streamlit email / usage prompts (see .streamlit\credentials.toml)
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set PYTHONWARNINGS=ignore

%PYEXE% -m streamlit run scripts\odmr_pitch_ui\app.py --server.port 8501 --browser.gatherUsageStats false --server.headless false
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo Streamlit exited with code %ERR%.
  pause
  exit /b %ERR%
)

endlocal
