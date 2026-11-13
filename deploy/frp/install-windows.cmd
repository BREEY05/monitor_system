@echo off
setlocal
set "HERE=%~dp0"
set "SRV=%~2"
if "%SRV%"=="" set "SRV=81.70.92.137"
if "%~1"=="" (
  echo Usage: install-windows.cmd ^<frps-token^> [server-addr]
  echo Example: deploy\frp\install-windows.cmd 85c9e7dd...
  exit /b 1
)
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator rights, please click Yes on the UAC prompt...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1','%SRV%' -Verb RunAs"
  echo If UAC was cancelled, nothing was installed.
  exit /b
)
echo Administrator rights OK, installing frpc...
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%install-frpc.ps1" -ServerAddr "%SRV%" -Token "%~1"
echo.
pause