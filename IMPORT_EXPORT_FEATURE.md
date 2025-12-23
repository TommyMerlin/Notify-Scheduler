# 数据导入导出功能说明

## 功能概述

新增了完整的数据导入导出功能，支持用户在不同环境间迁移数据，包括：
- 通知任务
- 通知渠道配置
- 外部日历订阅

## 安全特性

### 敏感数据加密
导出时自动加密以下敏感字段：
- `webhook_url` - Webhook URLs（包含密钥）
- `token` - API tokens
- `app_secret` - 应用密钥
- `corp_secret` - 企业密钥
- `corpid` - 企业 ID
- `agentid` - 应用 ID
- `app_id` - App ID
- `receiver_id` - 接收者 ID
- `sendkey` - 发送密钥
- `server_url` - 服务器地址（可能包含认证信息）
- `username` - 用户名
- `password` - 密码

### 加密实现
- **算法**: Fernet (AES-128-CBC + HMAC)
- **密钥派生**: HKDF-SHA256 从应用 SECRET_KEY 派生
- **版本标识**: 支持未来密钥轮换和格式升级

## 使用方法

### 导出数据
1. 点击顶部工具栏的 "📤 导出" 按钮
2. 自动下载 JSON 文件（文件名包含时间戳）
3. 文件包含加密的敏感配置

### 导入数据
1. 点击顶部工具栏的 "📥 导入" 按钮
2. 选择之前导出的 JSON 文件
3. 查看导入预览（任务数、通道数、日历数）
4. 确认后执行导入
5. 查看导入统计（成功/跳过数量）

### 导入策略
**合并模式（跳过重复）**:
- **任务**: 通过 `title` + `scheduled_time`（定时任务）或 `title` + `cron_expression`（周期任务）检测重复
- **通道**: 通过 `channel_name` 检测重复
- **日历**: 通过 `name` 检测重复
- 已存在的项将被跳过，不会覆盖

## API 端点

### GET /api/export
导出当前用户的所有数据

**响应格式**:
```json
{
  "version": "1.0",
  "export_date": "2025-12-23T10:30:00",
  "user": {
    "username": "user1",
    "email": "user@example.com"
  },
  "tasks": [...],
  "user_channels": [...],
  "external_calendars": [...]
}
```

### POST /api/import
导入用户数据（合并模式）

**请求体**: 导出的 JSON 数据

**响应**:
```json
{
  "message": "导入成功",
  "stats": {
    "tasks_imported": 5,
    "tasks_skipped": 2,
    "channels_imported": 3,
    "channels_skipped": 1,
    "calendars_imported": 2,
    "calendars_skipped": 0
  }
}
```

## 技术实现

### 后端
- **文件**: `encryption.py` - 加密工具模块
- **依赖**: `cryptography>=41.0.0`
- **端点**: `/api/export`, `/api/import`

### 前端
- **HTML**: 导入/导出按钮（`static/index.html`）
- **JS**: `exportData()`, `importData()` 函数（`static/js/app.js`）
- **CSS**: 渐变按钮样式（`static/css/styles.css`）

## 注意事项

1. **密钥一致性**: 导入数据必须使用相同的 `SECRET_KEY`，否则无法解密
2. **数据备份**: 建议定期导出数据作为备份
3. **跨用户**: 数据导入到当前登录用户，不支持跨用户导入
4. **任务调度**: 导入的待发送任务会自动加入调度器
5. **文件格式**: 仅支持 JSON 格式

## 未来增强

- [ ] 支持选择性导出（按日期范围、状态筛选）
- [ ] 支持 CSV 格式导出（简化版）
- [ ] 批量导入验证报告
- [ ] 导入冲突解决策略选择（替换/合并/追加）
- [ ] 压缩大文件导出
