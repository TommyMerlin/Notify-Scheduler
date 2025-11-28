# 📬 通知定时发送系统 - 项目总览

## 🎯 项目简介

这是一个功能完整的通知定时发送系统，具备以下特点：

- ✨ **美观的 Web 界面**：无需编写代码，通过浏览器即可管理所有通知任务
- ⏰ **精准定时发送**：支持指定任意时间发送通知
- 🔁 **灵活的重复任务**：使用 Cron 表达式创建每日、每周、每月等重复任务
- 📡 **多渠道支持**：企业微信、飞书、钉钉、PushPlus、Server酱等
- 🚀 **生产就绪**：提供完整的部署方案，包括 Docker、Systemd、Nginx 配置
- 🔌 **RESTful API**：完整的 API 接口，支持程序化调用

## 📂 项目文件说明

### 核心代码文件

| 文件 | 说明 | 重要程度 |
|------|------|---------|
| `app.py` | Flask Web 应用主程序，提供 API 和前端服务 | ⭐⭐⭐⭐⭐ |
| `models.py` | 数据库模型定义，任务数据结构 | ⭐⭐⭐⭐⭐ |
| `scheduler.py` | 任务调度器，负责定时执行任务 | ⭐⭐⭐⭐⭐ |
| `notifier.py` | 通知发送器，封装各渠道发送逻辑 | ⭐⭐⭐⭐⭐ |
| `static/index.html` | Web 前端界面 | ⭐⭐⭐⭐⭐ |

### 配置文件

| 文件 | 说明 | 用途 |
|------|------|------|
| `requirements.txt` | Python 依赖包列表 | 安装依赖 |
| `gunicorn_config.py` | Gunicorn 服务器配置 | 生产部署 |
| `nginx.conf` | Nginx 反向代理配置示例 | 生产部署 |
| `docker-compose.yml` | Docker Compose 配置 | Docker 部署 |
| `Dockerfile` | Docker 镜像配置 | Docker 部署 |
| `notify-scheduler.service` | Systemd 服务配置 | Linux 系统服务 |

### 脚本文件

| 文件 | 说明 | 使用场景 |
|------|------|---------|
| `start.sh` | 一键启动脚本 | 快速启动服务 |
| `stop.sh` | 停止服务脚本 | 停止运行中的服务 |

### 示例和文档

| 文件 | 说明 | 目标读者 |
|------|------|---------|
| `README.md` | 完整项目文档 | 所有用户 |
| `DEPLOY.md` | 快速部署指南 | 运维人员 |
| `example_usage.py` | API 使用示例 | 开发人员 |
| `test_system.py` | 系统测试脚本 | 测试人员 |
| `config_examples.json` | 各渠道配置示例 | 配置人员 |

## 🚀 快速开始（3步）

### 1️⃣ 选择部署方式

**A. Docker 部署（最简单）**
```bash
docker-compose up -d
```

**B. 脚本部署（推荐）**
```bash
chmod +x start.sh
./start.sh
```

**C. 手动部署**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install ANotify gunicorn
python app.py
```

### 2️⃣ 访问 Web 界面

打开浏览器访问：`http://your-server:5000`

### 3️⃣ 创建第一个通知任务

1. 选择通知渠道（如：企业微信Webhook）
2. 填写 Webhook URL
3. 输入通知标题和内容
4. 选择发送时间
5. 点击"创建任务"

完成！系统会在指定时间自动发送通知。

## 🎨 界面预览

Web 界面包含两大部分：

### 左侧：任务创建表单
- 通知标题输入框
- 通知内容输入框（支持 Markdown）
- 通知渠道下拉选择
- 渠道配置动态表单
- 计划发送时间选择器
- 重复任务选项（含 Cron 表达式）

### 右侧：任务列表
- 状态筛选器（全部/待发送/已发送/失败/已取消）
- 任务卡片展示
- 每个任务显示：标题、内容、状态、渠道、时间
- 待发送任务可以取消
- 自动刷新（30秒）

## 🔧 支持的通知渠道

| 渠道 | 需要配置 | 获取方式 |
|------|---------|---------|
| 企业微信 Webhook | Webhook URL | 企业微信群机器人 |
| 飞书 Webhook | Webhook URL | 飞书群机器人 |
| 钉钉 Webhook | Webhook URL | 钉钉群机器人 |
| 企业微信应用 | corpid, corpsecret, agentid | 企业微信后台 |
| 飞书应用 | appid, appsecret, 接收者信息 | 飞书开发者后台 |
| PushPlus | Token | PushPlus 官网 |
| Server酱 | Token | Server酱官网 |

## 💡 典型使用场景

### 场景 1：定时提醒
- 每天早上 9 点发送工作提醒
- 每周一发送周报提醒
- 每月 1 号发送月度汇报提醒

### 场景 2：延迟通知
- 30 分钟后发送会议提醒
- 2 小时后发送跟进提醒
- 明天发送生日祝福

### 场景 3：批量通知
- 通过 API 批量创建任务
- 定时向不同群发送通知
- 多渠道同时发送

### 场景 4：监控告警
- 系统监控结果定时推送
- 异常情况即时通知
- 定期报告自动发送

## 📊 系统特性

### 高可靠性
- SQLite 数据库持久化
- 任务状态实时跟踪
- 失败任务错误记录
- 服务重启自动恢复

### 易于部署
- 多种部署方式可选
- 一键启动脚本
- Docker 容器化支持
- 详细部署文档

### 生产就绪
- Gunicorn WSGI 服务器
- Nginx 反向代理支持
- Systemd 服务管理
- 日志轮转配置
- 数据库备份方案

### 安全性
- 支持 HTTPS
- 配置信息加密存储
- Nginx 访问控制
- 防火墙配置指南

## 📖 文档导航

- **新手入门**：阅读 `README.md` 的"快速开始"部分
- **部署上线**：参考 `DEPLOY.md` 快速部署指南
- **API 开发**：查看 `example_usage.py` 了解 API 使用
- **渠道配置**：参考 `config_examples.json` 配置各个渠道
- **故障排查**：查看 `README.md` 的"故障排查"部分

## 🎯 下一步操作

### 对于运维人员
1. 阅读 `DEPLOY.md` 选择部署方式
2. 配置 Nginx 和 SSL 证书
3. 设置日志轮转和数据备份
4. 配置监控告警

### 对于开发人员
1. 查看 `example_usage.py` 学习 API 使用
2. 运行 `test_system.py` 测试系统功能
3. 根据需要扩展新的通知渠道
4. 集成到现有系统中

### 对于普通用户
1. 访问 Web 界面
2. 配置你常用的通知渠道
3. 创建第一个测试任务
4. 查看任务执行结果

## ❓ 常见问题快速解答

**Q: 需要什么技术背景？**
A: 不需要！有 Web 界面，点击鼠标即可使用。

**Q: 支持哪些操作系统？**
A: Linux、macOS、Windows（推荐 Linux）。

**Q: 可以免费使用吗？**
A: 完全免费，开源项目。

**Q: 任务会丢失吗？**
A: 不会，所有任务保存在数据库中，服务重启后自动恢复。

**Q: 可以发送图片吗？**
A: 目前仅支持文本，可扩展支持图片（需修改代码）。

**Q: 支持多少任务？**
A: 理论上无限制，实际取决于服务器性能。

## 🤝 技术支持

项目基于以下优秀的开源项目：

- [ANotify](https://github.com/TommyMerlin/ANotify) - 多渠道通知发送库
- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [APScheduler](https://apscheduler.readthedocs.io/) - 任务调度
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM 数据库

## 📄 许可证

MIT License - 可自由使用、修改和分发。

---

**开始使用吧！如有问题，请查阅 README.md 或 DEPLOY.md 获取详细帮助。** 🚀
