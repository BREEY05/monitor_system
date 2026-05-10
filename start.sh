#!/bin/bash
# ============================================
# 工业环境监控系统 - 树莓派启动脚本
# ============================================

echo "========================================"
echo "  工业环境监控系统 - 树莓派后端启动"
echo "========================================"

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if [ -z "$python_version" ]; then
    echo "错误: 未找到 Python3"
    exit 1
fi
echo "Python 版本: $python_version"

# 创建虚拟环境（可选）
if [ ! -d "venv" ]; then
    echo "正在创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "正在安装依赖..."
pip install --upgrade pip
pip install fastapi uvicorn sqlalchemy aiofiles pillow requests

# 可选依赖（需要真实传感器时安装）
echo "安装传感器依赖（可选）..."
pip install smbus2 2>/dev/null || echo "  smbus2 安装失败（无 I2C 设备）"
pip install Adafruit-DHT 2>/dev/null || echo "  Adafruit-DHT 安装失败"

# 可选：OpenCV（摄像头）
pip install opencv-python-headless 2>/dev/null || echo "  opencv-python 安装失败"

echo ""
echo "========================================"
echo "  依赖安装完成"
echo "========================================"
echo ""
echo "启动选项:"
echo "  1. 完整模式（传感器 + 摄像头 + AI）"
echo "  2. 模拟模式（仅测试，无真实硬件）"
echo "  3. 查看当前配置"
echo ""

read -p "请选择 (1/2/3): " choice

case $choice in
    1)
        echo "启动完整模式..."
        python api_server.py
        ;;
    2)
        echo "启动模拟模式（将使用模拟传感器数据）..."
        python api_server.py --mock
        ;;
    3)
        echo "当前配置:"
        cat config.json 2>/dev/null || echo "无配置文件"
        ;;
    *)
        echo "无效选择，启动模拟模式..."
        python api_server.py --mock
        ;;
esac