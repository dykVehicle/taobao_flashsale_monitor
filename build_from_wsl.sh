#!/bin/bash
# 从WSL环境调用Windows Python进行编译
# 用法: bash build_from_wsl.sh

# 记录开始时间
START_TIME=$(date +%s)

# 进度显示函数 (使用 ASCII 字符避免乱码)
show_progress() {
    local step=$1
    local total=5
    local percent=$((step * 100 / total))
    local filled=$((percent / 5))
    local empty=$((20 - filled))
    
    printf "[%3d%%] [" "$percent"
    printf "%${filled}s" | tr ' ' '#'
    printf "%${empty}s" | tr ' ' '-'
    printf "] Step %d/%d\n" "$step" "$total"
}

# 计算耗时函数
show_duration() {
    local end_time=$(date +%s)
    local duration=$((end_time - START_TIME))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))
    echo "[TIME] Build duration: ${minutes}m ${seconds}s"
}

echo "======================================"
echo " 淘宝闪购智能助手Agent - 从WSL编译Windows exe"
echo "======================================"
echo ""

# 获取当前目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 获取Windows用户名
WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
if [ -z "$WIN_USER" ] || [ "$WIN_USER" == "%USERNAME%" ]; then
    WIN_USER="dyk"  # Fallback to known user if detection fails
fi

# Windows临时编译目录
WIN_BUILD_DIR="/mnt/c/Users/$WIN_USER/Desktop/taobao_monitor_build"
WIN_BUILD_PATH="C:\\Users\\$WIN_USER\\Desktop\\taobao_monitor_build"

echo "WSL项目目录: $SCRIPT_DIR"
echo "Windows编译目录: $WIN_BUILD_PATH"
echo ""

# Step 1: 检查Windows Python
show_progress 1
echo "[1/5] 检查Windows Python..."
WIN_PYTHON_VERSION=$(cd /mnt/c && cmd.exe /c "python --version" 2>&1 | tr -d '\r')
if [[ ! "$WIN_PYTHON_VERSION" =~ "Python" ]]; then
    echo "警告: 未能通过默认路径找到Python ($WIN_PYTHON_VERSION)"
    echo "尝试查找 Conda 环境..."
    if [ -f "/mnt/d/ProgramData/miniconda3/python.exe" ]; then
        echo "  [OK] 找到 Conda Python: D:\ProgramData\miniconda3\python.exe"
        PYTHON_CMD="D:\ProgramData\miniconda3\python.exe"
    else
        echo "错误: 未找到Windows Python，请确保 python 在 PATH 中"
        exit 1
    fi
else
    echo "  [OK] 找到 $WIN_PYTHON_VERSION"
    PYTHON_CMD="python"
fi

# Step 2: 复制文件到Windows目录
echo ""
show_progress 2
echo "[2/5] 复制项目文件到Windows..."
mkdir -p "$WIN_BUILD_DIR"
rm -rf "$WIN_BUILD_DIR/build" 2>/dev/null
rm -f "$WIN_BUILD_DIR"/*.py "$WIN_BUILD_DIR"/*.json "$WIN_BUILD_DIR"/*.txt "$WIN_BUILD_DIR"/*.spec 2>/dev/null

cp "$SCRIPT_DIR/gui_app.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/config_manager.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/selenium_fetcher.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/shop_manager.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/parallel_monitor.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/version.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/build_exe.py" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$WIN_BUILD_DIR/"
cp "$SCRIPT_DIR/version.json" "$WIN_BUILD_DIR/" 2>/dev/null || echo '{"version": "1.0"}' > "$WIN_BUILD_DIR/version.json"
echo "  [OK] 文件复制完成"

# Step 3: 安装依赖
echo ""
show_progress 3
echo "[3/5] 安装Python依赖..."
(cd /mnt/c && cmd.exe /c "$PYTHON_CMD -m pip install -q PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml pyinstaller" 2>/dev/null)
echo "  [OK] 依赖安装完成"

# Step 4: 打包
echo ""
show_progress 4
echo "[4/5] 开始打包..."
PACK_START=$(date +%s)

(cd /mnt/c && cmd.exe /c "chcp 65001 >nul && cd /d $WIN_BUILD_PATH && $PYTHON_CMD build_exe.py")

PACK_END=$(date +%s)
PACK_DURATION=$((PACK_END - PACK_START))
echo "  打包阶段耗时: ${PACK_DURATION}秒"

# Step 5: 检查结果并复制回来
echo ""
show_progress 5
echo "[5/5] 检查打包结果..."

BUILD_VERSION=$(cat "$WIN_BUILD_DIR/version.json" 2>/dev/null | grep -oP '"version"\s*:\s*"\K[^"]+')
EXE_NAME="TaobaoFlashSaleMonitorV${BUILD_VERSION}.exe"
EXE_FILE="$WIN_BUILD_DIR/dist/$EXE_NAME"

if [ -n "$BUILD_VERSION" ] && [ -f "$EXE_FILE" ]; then
    echo "  编译版本: V$BUILD_VERSION"
    
    mkdir -p "$SCRIPT_DIR/dist"
    cp "$EXE_FILE" "$SCRIPT_DIR/dist/"
    
    if [ -f "$WIN_BUILD_DIR/version.json" ]; then
        cp "$WIN_BUILD_DIR/version.json" "$SCRIPT_DIR/"
    fi
    
    echo ""
    echo "======================================"
    echo "[SUCCESS] Build completed!"
    echo "======================================"
    echo ""
    show_duration
    echo ""
    echo "EXE file: $EXE_NAME"
    echo "Location:"
    echo "  Desktop: $WIN_BUILD_PATH\\dist\\$EXE_NAME"
    echo "  Copied to: $SCRIPT_DIR/dist/$EXE_NAME"
    echo ""
    
    SIZE=$(ls -lh "$SCRIPT_DIR/dist/$EXE_NAME" | awk '{print $5}')
    echo "File size: $SIZE"
    echo ""
    echo "You can double-click $EXE_NAME to run!"
else
    echo ""
    echo "======================================"
    echo "[FAILED] Build failed!"
    echo "======================================"
    echo ""
    show_duration
    echo ""
    echo "请尝试在Windows命令提示符中手动运行:"
    echo "  1. 打开 CMD 或 PowerShell"
    echo "  2. cd $WIN_BUILD_PATH"
    echo "  3. python build_exe.py"
fi
