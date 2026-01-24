@echo off
chcp 65001 >nul
echo 正在启动淘宝闪购智能助手Agent...
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

:: 安装依赖并运行
pip install -q PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml >nul 2>&1
python gui_app.py

pause
