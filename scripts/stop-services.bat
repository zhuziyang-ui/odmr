@echo off
setlocal EnableExtensions

echo Stopping processes on ports 8000 and 5173...

for %%P in (8000 5173) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    if not "%%A"=="0" (
      echo Killing PID %%A on port %%P
      taskkill /PID %%A /F >nul 2>&1
    )
  )
)

echo Done.
if /I not "%~1"=="silent" pause
