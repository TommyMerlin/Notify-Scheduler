#!/bin/bash

# 通知定时发送系统启动脚本

echo "====================================="
echo "通知定时发送系统启动脚本"
echo "====================================="

# 检查 Python 版本
python_version=$(python3 --version 2>&1)
echo "Python 版本: $python_version"

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "安装依赖包..."
pip install -r requirements.txt
pip install gunicorn ANotify

# 创建必要的目录
mkdir -p logs data

# 初始化数据库
echo "初始化数据库..."
python3 -c "from models import init_db; init_db()"

# 启动服务
echo "====================================="
echo "启动服务..."
echo "访问地址: http://localhost:5000"
echo "====================================="

# 选择启动方式
if [ "$1" == "prod" ]; then
    # 生产环境：使用 Gunicorn
    echo "使用 Gunicorn 启动（生产模式）"
    gunicorn -c gunicorn_config.py app:app
else
    # 开发环境：使用 Flask 开发服务器
    echo "使用 Flask 开发服务器启动（开发模式）"
    python3 app.py
fi
