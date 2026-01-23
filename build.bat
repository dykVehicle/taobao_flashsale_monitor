@echo off
chcp 65001 >nul
echo ====================================
echo  淘宝闪购监控工具 - Windows打包脚本
echo ====================================
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 安装依赖
echo [1/3] 安装依赖包...
pip install -q PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml pyinstaller

:: 执行打包
echo.
echo [2/3] 开始打包...
python build_exe.py

:: 完成
echo.
echo [3/3] 完成！
echo.
echo 打包完成后，可执行文件位于: dist\淘宝闪购监控工具.exe
echo.
pause
