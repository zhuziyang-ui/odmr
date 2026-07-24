@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo Usage: free_ports.bat PORT [PORT2 ...]
  exit /b 1
)

echo Freeing ports: %*
for %%P in (%*) do call :free_one %%P
echo Port cleanup done.
echo.
exit /b 0

:free_one
set "PORT=%~1"
if "%PORT%"=="" exit /b 0
echo  - checking port %PORT% ...
set "KILLED=0"
for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr /I "LISTENING"') do (
  if not "%%A"=="0" if not "%%A"=="" (
    echo    kill PID %%A
    taskkill /F /PID %%A >nul 2>&1
    set "KILLED=1"
  )
)
REM Fallback: PowerShell (IPv6 / edge cases)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { if ($_.OwningProcess -gt 0) { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host ('    kill PID ' + $_.OwningProcess + ' via PS') } }" 2>nul
if "%KILLED%"=="0" echo    port %PORT%: no previous LISTENING process
exit /b 0
