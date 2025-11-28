#!/bin/bash

# 通知定时发送系统停止脚本

echo "====================================="
echo "停止通知定时发送系统"
echo "====================================="

# 查找 Gunicorn 进程
if [ -f "logs/gunicorn.pid" ]; then
    PID=$(cat logs/gunicorn.pid)
    if ps -p $PID > /dev/null; then
        echo "停止 Gunicorn 进程 (PID: $PID)..."
        kill -TERM $PID
        echo "服务已停止"
    else
        echo "PID 文件存在，但进程未运行"
        rm logs/gunicorn.pid
    fi
else
    # 如果没有 PID 文件，尝试查找进程
    PIDS=$(pgrep -f "gunicorn.*app:app")
    if [ -n "$PIDS" ]; then
        echo "找到 Gunicorn 进程: $PIDS"
        echo "停止进程..."
        kill -TERM $PIDS
        echo "服务已停止"
    else
        echo "未找到运行中的服务"
    fi
fi

echo "====================================="
