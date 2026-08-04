@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo Usage: free_ports.bat PORT [PORT2 ...]
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0free_ports.ps1" %*
exit /b %ERRORLEVEL%
