# Gunicorn 配置文件
import multiprocessing

# 绑定地址和端口
bind = "0.0.0.0:5000"

# 工作进程数
workers = multiprocessing.cpu_count() * 2 + 1

# 工作模式
worker_class = "sync"

# 超时时间
timeout = 120

# 日志
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# 进程名称
proc_name = "notify_scheduler"

# 守护进程模式（后台运行）
daemon = False

# PID 文件
pidfile = "logs/gunicorn.pid"
