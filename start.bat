@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

title 工业环境监控系统

cd /d "%~dp0"

echo.
echo ================================================
echo    工业环境监控系统 - 一键启动
echo ================================================
echo.

echo [1/4] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo    ❌ 错误: 未找到Python，请先安装Python 3.8+
    echo.
    pause
    exit /b 1
)
echo    ✅ Python已就绪
echo.

echo [2/4] 检查依赖包...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo    📦 正在安装依赖...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo    ⚠️  依赖安装可能有警告，请检查下方输出
    )
) else (
    echo    ✅ 依赖已安装
)
echo.

echo [3/4] 配置端口...
set PORT=8000
if not "%1"=="" (
    if "%1"=="--port=*" (
        set PORT=%1
        set PORT=!PORT:~7!
    )
)
echo    ✅ 使用端口 !PORT!
echo.

echo [4/4] 启动服务...
echo.
echo ================================================
echo    🚀 正在启动服务...
echo ================================================
echo.
echo    前端地址: http://localhost:!PORT!
echo    API文档:  http://localhost:!PORT!/api
echo.
echo    按 Ctrl+C 停止服务
echo ================================================
echo.

python start.py --no-browser
