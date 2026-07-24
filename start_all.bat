@echo off
setlocal
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

start "NV ODMR Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 3 /nobreak >nul
start "NV ODMR Frontend" cmd /k "%~dp0start_frontend.bat"

echo Two windows opened.
echo Open: http://127.0.0.1:5173/accuracy
echo.
timeout /t 4 >nul
