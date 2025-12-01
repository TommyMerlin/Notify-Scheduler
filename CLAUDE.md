# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 Python Flask 的通知定时发送系统，支持多渠道通知（企业微信、飞书、钉钉等）的定时和重复发送。系统提供 Web 管理界面和 RESTful API。

## 常用开发命令

### 开发环境启动
```bash
# 使用启动脚本（推荐）
./start.sh

# 手动启动
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install gunicorn ANotify
python app.py
```

### 生产环境启动
```bash
# 使用 Gunicorn
./start.sh prod

# 使用 Docker
docker-compose up -d
```

### 数据库操作
```bash
# 初始化数据库
python -c "from models import init_db; init_db()"

# 重新初始化（清空数据）
python -c "from models import Base, engine; Base.metadata.drop_all(engine); Base.metadata.create_all(engine)"
```

### 测试
```bash
# 运行系统测试
python test_system.py

# API 使用示例
python example_usage.py
```

## 代码架构

### 核心模块
- **app.py**: Flask Web 应用主程序，提供 RESTful API 和前端服务
- **models.py**: SQLAlchemy 数据库模型定义（NotifyTask, NotifyChannel, NotifyStatus）
- **scheduler.py**: APScheduler 任务调度器封装，处理定时和重复任务
- **notifier.py**: 通知发送器，封装 ANotify 多渠道发送逻辑
- **static/index.html**: Web 前端单页面应用

### 数据流
```
Web 前端 → Flask API → APScheduler → NotificationSender → ANotify → 通知渠道
```

### 关键设计
- **时区处理**: 系统使用东八区（Asia/Shanghai）时间
- **任务状态**: pending（待发送）→ sent（已发送）/ failed（失败）/ cancelled（已取消）
- **重复任务**: 使用 Cron 表达式，支持复杂调度规则
- **错误处理**: 任务失败时记录错误信息，不影响其他任务执行
- **数据库**: SQLite 默认存储在 `notify_scheduler.db`

## API 接口

主要端点：
- `GET /` - Web 管理界面
- `POST /api/tasks` - 创建任务
- `GET /api/tasks` - 获取任务列表（支持状态筛选）
- `GET /api/tasks/{id}` - 获取任务详情
- `PUT /api/tasks/{id}` - 更新任务
- `DELETE /api/tasks/{id}` - 取消任务
- `GET /api/channels` - 获取支持的渠道列表

## 通知渠道配置

支持的渠道及必需配置字段：
- **wecom**: corpid, corpsecret, agentid
- **wecom_webhook**: webhook_url
- **feishu**: appid, appsecret, receiver_type, receiver_id
- **feishu_webhook**: webhook_url
- **dingtalk_webhook**: webhook_url
- **pushplus**: token
- **serverchan**: token

## 部署注意事项

1. **端口**: 默认 5000，可在 `gunicorn_config.py` 或 `app.py` 中修改
2. **日志**: 访问日志和错误日志保存在 `logs/` 目录
3. **数据持久化**: 数据库文件 `notify_scheduler.db` 需要备份
4. **生产环境**: 推荐使用 Gunicorn + Nginx + Systemd 的组合
5. **Docker**: 支持多种容器化部署方式，数据卷挂载确保数据持久化