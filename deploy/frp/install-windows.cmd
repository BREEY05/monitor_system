@echo off
setlocal
set "HERE=%~dp0"
set "SRV=%~2"
if "%SRV%"=="" set "SRV=81.70.92.137"
if "%~1"=="" (
  echo 用法: install-windows.cmd ^<frps-token^> [server-addr]
  echo 例:   deploy\frp\install-windows.cmd 85c9e7ddb597cf1759115716032f21ccce400243d3d3cf57
  exit /b 1
)
net session >nul 2>&1
if errorlevel 1 (
  echo 正在请求管理员权限，请在弹窗中点击「是」...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1','%SRV%' -Verb RunAs"
  exit /b
)
echo 管理员权限已获取，开始安装 frpc...
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%install-frpc.ps1" -ServerAddr "%SRV%" -Token "%~1"
echo.
pause