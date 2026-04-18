# Gunicorn 配置文件

# 绑定地址和端口
bind = "0.0.0.0:5000"

# 工作进程数
# 当前项目使用进程内 APScheduler，并在应用启动时加载待执行任务。
# 如果启用多个 Gunicorn worker，每个进程都会各自启动调度器并重复执行同一任务。
# 因此生产环境必须保持单 worker，除非后续将调度器拆到独立进程或引入共享 job store / 分布式锁。
workers = 1

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
