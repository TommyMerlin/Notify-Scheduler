<div align="center">

# 通知定时发送系统

![GitHub License](https://img.shields.io/github/license/TommyMerlin/Notify-Scheduler?style=flat-square) ![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/TommyMerlin/Notify-Scheduler/docker-buid.yml?style=flat-square&label=Docker%20Build%20%26%20Push) ![Docker Pulls](https://img.shields.io/docker/pulls/7ommymerlin/notify-scheduler?style=flat-square) ![GitHub Release](https://img.shields.io/github/v/release/TommyMerlin/Notify-Scheduler?style=flat-square)  
[🌐 在线演示](https://notify.7ommy.dpdns.org/) · [🐛 报告问题](https://github.com/TommyMerlin/Notify-Scheduler/issues) · [✨ 功能建议](https://github.com/TommyMerlin/Notify-Scheduler/issues)
</div>

基于 [ANotify](https://github.com/TommyMerlin/ANotify) 库的通知定时发送系统，支持多种通知渠道的定时和重复发送。提供完整的 Web 管理界面、RESTful API 和日历订阅功能。

- **主界面**
![主界面](./assets/main-page.png)

- **日历视图**
![日历](./assets/calendar.png)

- **日历导出(订阅)**
![日历导出](./assets/calendar_export.png)

- **日历导入(同步)**
![日历导入](./assets/calendar_import.png)

## 功能特性

### 核心功能
- ✅ **多渠道支持**: 企业微信、飞书、钉钉、PushPlus、Server酱、Gotify、Ntfy、IYUU、巴法云、邮件等第三方推送
- 🎯 **多渠道同发**: 单个任务可同时向多个渠道发送通知
- ⏰ **定时发送**: 指定时间自动发送通知
- 🔁 **重复任务**: 支持使用 Cron 表达式创建重复任务（5位或6位格式）
- ⏸️ **任务暂停**: 重复任务支持暂停/恢复功能

### 渠道管理
- 💾 **渠道保存**: 保存常用通知渠道配置，避免重复填写
- ⚡ **快速选择**: 从已保存渠道快速选择创建任务
- ✏️ **在线编辑**: 支持渠道配置的在线编辑和管理

### Web 界面
- 🌐 **现代界面**: 美观的响应式前端界面
- 📱 **移动适配**: 完善的移动端触摸优化
- 📅 **日历视图**: 可视化日历展示任务，支持拖拽调整时间
- 🔄 **实时更新**: 任务状态实时推送（SSE）
- 📊 **状态筛选**: 按状态筛选和查看任务

### 日历功能
- 📆 **日历订阅**: 生成 iCal 格式的日历订阅链接
- 🔗 **外部同步**: 支持从外部日历（Google Calendar、Apple Calendar等）导入事件
- 🔄 **自动同步**: 外部日历自动定期同步（15分钟间隔）
- 📤 **导出导入**: 支持任务数据的导出和导入（带加密保护）

### 监控与日志
- 📈 **执行日志**: 详细的任务执行日志记录
- 📊 **统计信息**: 成功率、失败次数等统计数据

### API 与集成
- 🔌 **RESTful API**: 完整的 HTTP API 接口
- 🧪 **测试功能**: 内置通知测试功能，验证配置正确性
- 🔍 **健康检查**: 系统健康状态监控接口
- 📦 **版本管理**: 支持版本检查和更新提醒

### 部署运维
- 🐳 **容器化部署**: 支持 Docker 和 Docker Compose 部署
- 🚀 **生产就绪**: 提供 Nginx、Systemd、Gunicorn 等生产环境配置
- 💾 **数据备份**: SQLite 数据库，易于备份和迁移
- 🔄 **自动迁移**: 数据库结构自动迁移更新

## 系统架构

```
┌─────────────────┐
│   Web 前端界面   │  ← 用户交互（任务管理、日历视图、渠道配置）
└────────┬────────┘
         │ HTTP + SSE
┌────────▼────────┐
│   Flask API     │  ← RESTful 接口 + JWT 认证
│   + 用户认证     │
└────────┬────────┘
         │
    ┌────┴────┬─────────┬─────────┐
    │         │         │         │
┌───▼───┐ ┌──▼──┐  ┌───▼───┐ ┌──▼────┐
│ SQLite│ │APSche│  │Encrypt│ │EventMgr│
│  数据库 │ │ duler│  │ 加密   │ │ SSE推送 │
└───┬───┘ └──┬──┘  └───────┘ └────────┘
    │        │
    │    ┌───▼────────────┐
    │    │  Task Executor │  ← 任务执行与日志记录
    │    └───┬────────────┘
    │        │
    │    ┌───▼────────────┐
    │    │  Notification  │  ← 发送通知（模板变量替换）
    │    │    Sender      │
    │    └───┬────────────┘
    │        │
    │    ┌───▼────────────┐
    │    │    ANotify     │  ← 多渠道通知发送
    │    └───┬────────────┘
    │        │
    └────────┴────────────────────────┐
                                      │
    ┌─────────────────────────────────▼──────┐
    │  企业微信 │ 飞书 │ 钉钉 │ PushPlus ... │
    └────────────────────────────────────────┘
```

### 核心组件

- **Web 前端**: 单页应用，支持任务管理、日历视图、实时更新
- **Flask API**: RESTful API 服务，JWT 认证，数据验证
- **用户系统**: 多用户支持，数据隔离，权限控制
- **APScheduler**: 后台任务调度，支持定时和 Cron 重复任务
- **加密模块**: 敏感配置加密存储（Token、Webhook URL）
- **日志系统**: 详细的任务执行日志和错误追踪
- **告警系统**: 任务执行异常告警
- **日历功能**: iCal 订阅生成和外部日历同步
- **SSE 推送**: 任务状态实时推送到前端

## 快速开始

### 方式一：使用 Docker（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/TommyMerlin/Notify-Scheduler.git
cd Notify-Scheduler

# 2. 构建并启动容器
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 停止服务
docker-compose down
```

### 方式二：使用启动脚本

```bash
# 1. 克隆项目
git clone https://github.com/TommyMerlin/Notify-Scheduler.git
cd Notify-Scheduler

# 2. 安装依赖并启动（开发模式）
./start.sh

# 3. 或使用生产模式（Gunicorn）
./start.sh prod
```

### 方式三：手动安装

```bash
# 1. 克隆项目
git clone https://github.com/TommyMerlin/Notify-Scheduler.git
cd Notify-Scheduler

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
pip install gunicorn ANotify

# 4. 启动应用
python app.py  # 开发模式
# 或
gunicorn -c gunicorn_config.py app:app  # 生产模式
```

访问 `http://localhost:5000` 打开 Web 管理界面。

### 首次使用

1. 打开浏览器访问系统地址
2. 注册新用户账号
3. 登录后即可开始使用

## Web 界面使用说明

### 用户注册与登录

首次使用需要先注册账号：
1. 访问系统首页
2. 点击"注册"按钮
3. 填写用户名、邮箱和密码（密码至少6位）
4. 注册成功后自动登录

### 创建通知任务

#### 单渠道模式

1. 在左侧表单中填写通知信息：
   - **通知标题**: 任务标题
   - **通知内容**: 通知正文，支持 Markdown 格式和模板变量
   - **通知渠道**: 选择发送渠道（企业微信、飞书等）
   - **渠道配置**: 根据选择的渠道填写相应配置（如 Webhook URL）
   - **已保存渠道**: 从下拉列表快速选择已保存的渠道配置
   - **计划发送时间**: 选择发送时间
   - **重复任务**: 勾选后可设置 Cron 表达式创建重复任务

2. 点击"创建任务"按钮

#### 多渠道模式

支持一次性向多个渠道发送通知：
1. 选择多个通知渠道
2. 为每个渠道分别配置参数
3. 创建任务后会同时向所有渠道发送

### 模板变量

通知标题和内容支持以下模板变量：
- `{{date}}`: 当前日期 (YYYY-MM-DD)
- `{{time}}`: 当前时间 (HH:MM:SS)
- `{{datetime}}`: 日期时间
- `{{year}}`, `{{month}}`, `{{day}}`: 年月日
- `{{hour}}`, `{{minute}}`, `{{second}}`: 时分秒
- `{{timestamp}}`: Unix 时间戳
- `{{weekday}}`: 星期 (英文)
- `{{weekday_cn}}`: 星期 (中文)

### 管理任务

- **查看任务**: 右侧任务列表显示所有任务
- **筛选任务**: 使用状态筛选器查看不同状态的任务
  - `pending`: 待发送
  - `sent`: 已发送
  - `failed`: 发送失败
  - `cancelled`: 已取消
  - `paused`: 已暂停（重复任务）
- **取消任务**: 对于待发送的任务，点击"取消任务"按钮
- **暂停/恢复**: 重复任务支持暂停和恢复功能
- **编辑任务**: 点击任务卡片可编辑任务信息
- **查看日志**: 查看任务的详细执行日志
- **自动刷新**: 任务列表支持实时更新（SSE）

### 日历视图

点击"日历"标签切换到日历视图：
- **月视图**: 查看整月的任务安排
- **点击任务**: 查看任务详情或编辑
- **拖拽调整**: 拖拽任务卡片调整发送时间
- **快速创建**: 点击日期快速创建任务

### 渠道管理

在"我的通知渠道"板块可以：
- **添加渠道**: 保存常用的通知渠道配置
- **编辑渠道**: 修改已保存的渠道信息
- **删除渠道**: 删除不需要的渠道配置
- **设为默认**: 设置默认渠道，创建任务时自动选择
- **测试渠道**: 发送测试消息验证配置正确性

### 日历订阅

系统支持生成标准 iCal 格式的日历订阅：

1. 点击"日历订阅"按钮
2. 生成个人订阅令牌
3. 复制订阅链接
4. 在日历应用中添加订阅：
   - **Google Calendar**: 添加 → 通过 URL 添加
   - **Apple Calendar**: 文件 → 新建日历订阅
   - **Outlook**: 添加日历 → 从 Internet 订阅

### 外部日历同步

支持从外部日历导入事件并自动创建通知任务：

1. 点击"导入外部日历"
2. 填写日历名称和 iCal 订阅链接
3. 选择默认通知渠道
4. 系统会自动每15分钟同步一次
5. 支持的日历源：
   - Google Calendar
   - Apple iCloud Calendar
   - Outlook Calendar
   - 任何支持 iCal 格式的日历服务


## API 接口文档

### 用户认证

- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/profile` - 获取当前用户信息
- `PUT /api/auth/profile` - 更新用户资料

### 任务管理

- `POST /api/tasks` - 创建任务（支持单渠道和多渠道）
- `GET /api/tasks` - 获取任务列表（支持分页、排序、筛选）
- `GET /api/tasks/{id}` - 获取任务详情
- `PUT /api/tasks/{id}` - 更新任务
- `DELETE /api/tasks/{id}` - 取消任务
- `GET /api/tasks/{id}/logs` - 获取任务执行日志

### 渠道管理

- `GET /api/channels` - 获取支持的渠道列表
- `GET /api/user/channels` - 获取用户保存的渠道配置
- `POST /api/user/channels` - 保存新渠道配置
- `PUT /api/user/channels/{id}` - 更新渠道配置
- `DELETE /api/user/channels/{id}` - 删除渠道配置
- `POST /api/test-notification` - 测试通知发送

### 日历功能

- `GET /api/calendar/token` - 获取日历订阅令牌
- `POST /api/calendar/token` - 生成新的订阅令牌
- `GET /calendar/feed/{token}.ics` - 日历订阅源（iCal 格式）
- `GET /api/calendar/external` - 获取外部日历列表
- `POST /api/calendar/external` - 添加外部日历
- `DELETE /api/calendar/external/{id}` - 删除外部日历
- `POST /api/calendar/sync/{id}` - 手动同步外部日历

### 日志与监控

- `GET /api/logs` - 查询执行日志
- `GET /api/scheduler/jobs` - 获取调度器任务状态
- `GET /api/health` - 系统健康检查

### 告警规则

- `GET /api/alerts/rules` - 获取告警规则
- `POST /api/alerts/rules` - 创建告警规则
- `PUT /api/alerts/rules/{id}` - 更新告警规则
- `DELETE /api/alerts/rules/{id}` - 删除告警规则

### 数据管理

- `GET /api/export` - 导出数据（带加密）
- `POST /api/import` - 导入数据
- `GET /api/version` - 获取系统版本
- `GET /api/version/check` - 检查更新

## 项目结构

```
.
├── app.py                      # Flask Web API 主程序
├── models.py                   # 数据库模型定义
├── scheduler.py                # APScheduler 任务调度器
├── notifier.py                 # 通知发送器（封装 ANotify）
├── auth.py                     # 用户认证模块
├── encryption.py               # 数据加密模块
├── static/
│   ├── index.html             # Web 前端单页应用
│   ├── css/
│   │   ├── styles.css        # 主样式文件
│   │   └── calendar.css      # 日历视图样式
│   └── js/
│       ├── app.js            # 主应用逻辑
│       └── calendar.js       # 日历功能
├── data/
│   └── notify_scheduler.db    # SQLite 数据库
├── logs/                       # 日志目录
├── requirements.txt           # Python 依赖
├── gunicorn_config.py         # Gunicorn 配置
├── docker-compose.yml         # Docker Compose 配置
├── Dockerfile                 # Docker 镜像配置
├── notify-scheduler.service   # Systemd 服务配置
├── start.sh                   # 启动脚本
├── stop.sh                    # 停止脚本
├── config_examples.json       # 渠道配置示例
├── README.md                  # 项目文档
└── CLAUDE.md                  # 开发者指南
```

## 支持的通知渠道

具体见 [ANotify](https://github.com/TommyMerlin/ANotify)

| 渠道 | channel 值 | 配置字段 |
|------|-----------|---------|
| 企业微信 | `wecom` | corpid, corpsecret, agentid |
| 企业微信Webhook | `wecom_webhook` | webhook_url |
| 飞书 | `feishu` | appid, appsecret, receiver_type, receiver_id |
| 飞书Webhook | `feishu_webhook` | webhook_url |
| 钉钉Webhook | `dingtalk_webhook` | webhook_url |
| PushPlus | `pushplus` | token |
| Server酱 | `serverchan` | token |
| Gotify | `gotify` | server_url, token |
| Ntfy (ntfy.sh) | `ntfy` | server_url, topic |
| IYUU | `iyuu` | token (可选 `server_url`) |
| 巴法云 | `bafayun` | token (可选 `server_url`) |

## 数据管理

### 数据备份

```bash
# 备份数据库
cp data/notify_scheduler.db data/notify_scheduler.db.backup

# 使用 cron 定期备份
0 2 * * * cp /var/www/notify-scheduler/data/notify_scheduler.db /backup/notify_scheduler_$(date +\%Y\%m\%d).db
```

## 常见问题

**Q: 如何更改运行端口？**

A: 修改 `gunicorn_config.py` 中的 `bind` 配置，或在 Docker Compose 中修改端口映射。

**Q: 支持哪些 Python 版本？**

A: Python 3.8 及以上版本。建议使用 Python 3.11。

**Q: 可以同时运行多个实例吗？**

A: 不建议，APScheduler 可能导致任务重复执行。如需高可用，建议使用主备模式或配置外部调度器。

**Q: 重复任务的 Cron 表达式格式？**

A: 支持标准 5 位格式（分 时 日 月 周）和 6 位格式（秒 分 时 日 月 周）。示例：
- `0 9 * * *` - 每天 9:00
- `*/5 * * * *` - 每 5 分钟
- `0 0 9 * * MON` - 每周一 9:00（6位格式）

**Q: 如何查看系统日志？**

A: 日志保存在 `logs/` 目录下，或使用 `docker-compose logs -f` 查看容器日志。

## 开发计划

### 已完成
- [x] 用户认证系统
- [x] 日历视图支持点击任务进行编辑
- [x] 移动端响应式适配与触摸优化
- [x] 拖拽调整任务时间（日历视图）
- [x] 日历订阅及同步功能
- [x] 支持多渠道消息推送
- [x] 重复任务暂停功能
- [x] 数据导入/导出（带加密）
- [x] 任务执行日志查询
- [ ] 失败自动重试机制
- [ ] 任务执行前后脚本钩子
- [ ] 更多统计图表
- [ ] 密码重置功能
- [ ] Webhook 回调
- [ ] 任务模板功能

## License

MIT License

## 致谢

本项目使用 [ANotify](https://github.com/TommyMerlin/ANotify) 作为通知发送库。
