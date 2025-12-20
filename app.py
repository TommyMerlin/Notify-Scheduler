from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
from models import init_db, get_db, NotifyTask, NotifyChannel, NotifyStatus, User, UserChannel
from scheduler import scheduler
from auth import login_required, admin_required, user_login, user_register, update_user_profile
import json
import os

app = Flask(__name__, static_folder='static')
CORS(app)  # 启用跨域支持

# 配置JWT密钥
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# 初始化数据库
init_db()

# 加载待发送任务
scheduler.load_pending_tasks()


# 认证相关API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        result, error = user_login(username, password)
        if error:
            return jsonify({'error': error}), 401

        return jsonify({
            'message': '登录成功',
            'data': result
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not username or not email or not password:
            return jsonify({'error': '用户名、邮箱和密码不能为空'}), 400

        if len(password) < 6:
            return jsonify({'error': '密码长度至少6位'}), 400

        result, error = user_register(username, email, password)
        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'message': '注册成功',
            'data': result
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/profile', methods=['GET'])
@login_required
def get_profile():
    """获取当前用户信息"""
    try:
        return jsonify({
            'user': request.current_user.to_dict()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/profile', methods=['PUT'])
@login_required
def update_profile():
    """更新用户资料"""
    try:
        data = request.get_json()
        user_id = request.current_user.id

        result, error = update_user_profile(user_id, data)
        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'message': '更新成功',
            'data': result
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    """首页"""
    return send_from_directory('static', 'index.html')


@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    """
    创建通知任务

    请求体示例:
    {
        "title": "测试通知",
        "content": "这是一条测试通知",
        "channel": "wecom_webhook",
        "scheduled_time": "2024-12-01T10:00:00",
        "channel_config": {
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        },
        "is_recurring": false,
        "cron_expression": null
    }
    """
    try:
        data = request.get_json()

        # 兼容：重复任务不再强制要求 scheduled_time，由后端根据 cron 计算下一次执行时间
        is_recurring = bool(data.get('is_recurring', False))
        cron_expression = data.get('cron_expression')

        # 验证必填字段
        required_fields = ['title', 'content', 'channel', 'channel_config']
        # 非重复任务必须提供 scheduled_time
        if not is_recurring:
            required_fields.append('scheduled_time')
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

        scheduled_time = None
        if is_recurring:
            if not cron_expression:
                return jsonify({'error': '重复任务必须提供 cron_expression'}), 400
            # 由 cron 计算下一次运行时间（用于列表展示与排序）
            try:
                from apscheduler.triggers.cron import CronTrigger
                trigger = CronTrigger.from_crontab(cron_expression)
                next_run = trigger.get_next_fire_time(None, datetime.now())
                if not next_run:
                    return jsonify({'error': '无法根据 cron_expression 计算下一次执行时间'}), 400
                scheduled_time = next_run
            except Exception as e:
                return jsonify({'error': f'Cron 表达式无效: {str(e)}'}), 400
        else:
            # 解析时间
            try:
                scheduled_time = datetime.fromisoformat(data['scheduled_time'])
            except ValueError:
                return jsonify({'error': '时间格式错误，请使用 ISO 格式，如: 2024-12-01T10:00:00'}), 400

        # 验证通知渠道
        try:
            channel = NotifyChannel(data['channel'])
        except ValueError:
            valid_channels = [c.value for c in NotifyChannel]
            return jsonify({'error': f'无效的通知渠道，支持的渠道: {valid_channels}'}), 400

        # 创建任务
        with get_db() as db:
            task = NotifyTask(
                user_id=request.current_user.id,
                title=data['title'],
                content=data['content'],
                channel=channel,
                scheduled_time=scheduled_time,
                channel_config=json.dumps(data['channel_config'], ensure_ascii=False),
                is_recurring=is_recurring,
                cron_expression=cron_expression if is_recurring else None
            )

            db.add(task)
            db.commit()
            db.refresh(task)

            # 添加到调度器
            scheduler.add_task(task)

            return jsonify({
                'message': '任务创建成功',
                'task': task.to_dict()
            }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks', methods=['GET'])
@login_required
def list_tasks():
    """
    获取任务列表

    查询参数:
    - status: 过滤状态 (pending/sent/failed/cancelled)
    - page: 页码，默认 1
    - page_size: 每页数量，默认 20
    - sort_by: 排序字段 (scheduled_time/id/status/created_at)，默认 scheduled_time
    - sort_order: 排序方向 (asc/desc)，默认 asc
    """
    try:
        with get_db() as db:
            query = db.query(NotifyTask).filter(NotifyTask.user_id == request.current_user.id)

            # 状态过滤
            status = request.args.get('status')
            if status:
                try:
                    status_enum = NotifyStatus(status)
                    query = query.filter(NotifyTask.status == status_enum)
                except ValueError:
                    return jsonify({'error': f'无效的状态值: {status}'}), 400

            # 排序
            sort_by = request.args.get('sort_by', 'scheduled_time')
            sort_order = request.args.get('sort_order', 'asc').lower()

            sort_fields = {
                'scheduled_time': NotifyTask.scheduled_time,
                'id': NotifyTask.id,
                'status': NotifyTask.status,
                'created_at': NotifyTask.created_at
            }

            if sort_by not in sort_fields:
                return jsonify({'error': f'无效的排序字段: {sort_by}'}), 400

            if sort_order not in ('asc', 'desc'):
                return jsonify({'error': f'无效的排序方向: {sort_order}，可选 asc 或 desc'}), 400

            sort_clause = sort_fields[sort_by].asc() if sort_order == 'asc' else sort_fields[sort_by].desc()

            # 分页
            page = int(request.args.get('page', 1))
            page_size = int(request.args.get('page_size', 20))

            total = query.count()
            tasks = query.order_by(sort_clause).offset((page - 1) * page_size).limit(page_size).all()

            return jsonify({
                'total': total,
                'page': page,
                'page_size': page_size,
                'tasks': [task.to_dict() for task in tasks]
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    """获取单个任务详情"""
    try:
        with get_db() as db:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            return jsonify(task.to_dict())

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def cancel_task(task_id):
    """取消任务"""
    try:
        with get_db() as db:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            # 更新状态为已取消
            task.status = NotifyStatus.CANCELLED
            db.commit()

            # 从调度器移除
            scheduler.remove_task(task_id, task.is_recurring)

            return jsonify({'message': '任务已取消'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    """
    更新任务

    可更新字段: title, content, scheduled_time, channel_config, status
    支持重新启用已取消或已执行的任务，以及暂停/恢复重复任务
    """
    try:
        data = request.get_json()
        with get_db() as db:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            # 记录原始状态
            original_status = task.status

            # 处理状态变更（暂停/恢复）
            if 'status' in data:
                try:
                    target_status_str = data['status']
                    
                    # 暂停任务
                    if target_status_str == 'paused':
                        task.status = NotifyStatus.PAUSED
                        # 从调度器移除
                        scheduler.remove_task(task_id, task.is_recurring)
                        db.commit()
                        return jsonify({
                            'message': '任务已暂停',
                            'task': task.to_dict()
                        })
                    
                    # 恢复任务
                    elif target_status_str == 'pending' and task.status == NotifyStatus.PAUSED:
                        task.status = NotifyStatus.PENDING
                        # 恢复时重新计算下一次执行时间
                        if task.is_recurring and task.cron_expression:
                            try:
                                from apscheduler.triggers.cron import CronTrigger
                                trigger = CronTrigger.from_crontab(task.cron_expression)
                                next_run = trigger.get_next_fire_time(None, datetime.now())
                                if next_run:
                                    task.scheduled_time = next_run
                            except Exception as e:
                                return jsonify({'error': f'计算下一次执行时间失败: {str(e)}'}), 400
                        
                        scheduler.add_task(task)
                        db.commit()
                        return jsonify({
                            'message': '任务已恢复',
                            'task': task.to_dict()
                        })
                except Exception as e:
                    return jsonify({'error': f'状态更新失败: {str(e)}'}), 400

            # 更新字段
            if 'title' in data:
                task.title = data['title']
            if 'content' in data:
                task.content = data['content']
            if 'channel_config' in data:
                task.channel_config = json.dumps(data['channel_config'], ensure_ascii=False)

            # 处理时间更新
            if 'scheduled_time' in data:
                try:
                    task.scheduled_time = datetime.fromisoformat(data['scheduled_time'])
                except ValueError:
                    return jsonify({'error': '时间格式错误'}), 400

            # 关键：如果是重复任务，根据 cron 表达式重新计算下一次执行时间
            if task.is_recurring and task.cron_expression:
                try:
                    from apscheduler.triggers.cron import CronTrigger
                    trigger = CronTrigger.from_crontab(task.cron_expression)
                    # 以当前时间为基准，计算下一次执行时间
                    next_run = trigger.get_next_fire_time(None, datetime.now())
                    if next_run:
                        task.scheduled_time = next_run
                except Exception as e:
                    return jsonify({'error': f'根据 Cron 表达式计算下一次执行时间失败: {str(e)}'}), 400

            # 如果任务之前不是 PENDING 状态（且不是暂停操作），重新启用它
            # 注意：如果当前是 PAUSED 且没有明确请求 resume，通常保持 PAUSED
            is_paused = task.status == NotifyStatus.PAUSED
            
            if original_status != NotifyStatus.PENDING and not is_paused:
                task.status = NotifyStatus.PENDING
                task.sent_time = None
                task.error_msg = None

            db.commit()

            # 重新添加到调度器（如果任务被重新启用，需要添加到调度器）
            # 如果是 PAUSED，不添加
            scheduler.remove_task(task_id, task.is_recurring)
            if task.status == NotifyStatus.PENDING:
                scheduler.add_task(task)

            return jsonify({
                'message': '任务更新成功' if original_status == NotifyStatus.PENDING else '任务已重新启用',
                'task': task.to_dict()
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/jobs', methods=['GET'])
def get_scheduled_jobs():
    """获取调度器中的所有任务"""
    try:
        jobs = scheduler.get_scheduled_jobs()
        return jsonify({'jobs': jobs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/channels', methods=['GET'])
@login_required
def get_channels():
    """获取支持的通知渠道类型列表"""
    channels = [
        {
            'value': 'wecom',
            'label': '企业微信',
            'config_fields': ['corpid', 'corpsecret', 'agentid']
        },
        {
            'value': 'wecom_webhook',
            'label': '企业微信Webhook',
            'config_fields': ['webhook_url']
        },
        {
            'value': 'feishu',
            'label': '飞书',
            'config_fields': ['appid', 'appsecret', 'receiver_type', 'receiver_id']
        },
        {
            'value': 'feishu_webhook',
            'label': '飞书Webhook',
            'config_fields': ['webhook_url']
        },
        {
            'value': 'dingtalk_webhook',
            'label': '钉钉Webhook',
            'config_fields': ['webhook_url']
        },
        {
            'value': 'pushplus',
            'label': 'PushPlus',
            'config_fields': ['token']
        },
        {
            'value': 'serverchan',
            'label': 'Server酱',
            'config_fields': ['token']
        }
        ,
        {
            'value': 'gotify',
            'label': 'Gotify',
            'config_fields': ['server_url', 'token']
        },
        {
            'value': 'ntfy',
            'label': 'Ntfy (ntfy.sh)',
            'config_fields': ['server_url', 'topic']
        },
        {
            'value': 'iyuu',
            'label': 'IYUU',
            'config_fields': ['token']
        },
        {
            'value': 'bafayun',
            'label': '巴法云',
            'config_fields': ['token']
        }
    ]
    return jsonify({'channels': channels})


@app.route('/api/user/channels', methods=['GET'])
@login_required
def get_user_channels():
    """获取用户的通知渠道配置列表"""
    try:
        with get_db() as db:
            user_channels = db.query(UserChannel).filter(
                UserChannel.user_id == request.current_user.id
            ).all()

            return jsonify({
                'channels': [channel.to_dict() for channel in user_channels]
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/channels', methods=['POST'])
@login_required
def create_user_channel():
    """创建用户通知渠道配置"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['channel_name', 'channel_type', 'channel_config']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

        # 验证通知渠道类型
        try:
            channel_type = NotifyChannel(data['channel_type'])
        except ValueError:
            valid_channels = [c.value for c in NotifyChannel]
            return jsonify({'error': f'无效的通知渠道类型，支持的类型: {valid_channels}'}), 400

        with get_db() as db:
            # 检查用户是否已有相同名称的渠道
            existing_channel = db.query(UserChannel).filter(
                UserChannel.user_id == request.current_user.id,
                UserChannel.channel_name == data['channel_name']
            ).first()
            if existing_channel:
                return jsonify({'error': '渠道名称已存在'}), 400

            # 创建用户渠道配置
            user_channel = UserChannel(
                user_id=request.current_user.id,
                channel_name=data['channel_name'],
                channel_type=channel_type,
                channel_config=json.dumps(data['channel_config'], ensure_ascii=False),
                is_default=data.get('is_default', False)
            )

            db.add(user_channel)
            db.commit()
            db.refresh(user_channel)

            return jsonify({
                'message': '通知渠道配置创建成功',
                'channel': user_channel.to_dict()
            }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/channels/<int:channel_id>', methods=['PUT'])
@login_required
def update_user_channel(channel_id):
    """更新用户通知渠道配置"""
    try:
        data = request.get_json()
        with get_db() as db:
            channel = db.query(UserChannel).filter(
                UserChannel.id == channel_id,
                UserChannel.user_id == request.current_user.id
            ).first()
            if not channel:
                return jsonify({'error': '通知渠道配置不存在'}), 404

            # 更新字段
            if 'channel_name' in data:
                channel.channel_name = data['channel_name']
            if 'channel_config' in data:
                channel.channel_config = json.dumps(data['channel_config'], ensure_ascii=False)
            if 'is_default' in data:
                channel.is_default = data['is_default']

            db.commit()

            return jsonify({
                'message': '通知渠道配置更新成功',
                'channel': channel.to_dict()
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/channels/<int:channel_id>', methods=['DELETE'])
@login_required
def delete_user_channel(channel_id):
    """删除用户通知渠道配置"""
    try:
        with get_db() as db:
            channel = db.query(UserChannel).filter(
                UserChannel.id == channel_id,
                UserChannel.user_id == request.current_user.id
            ).first()
            if not channel:
                return jsonify({'error': '通知渠道配置不存在'}), 404

            db.delete(channel)
            db.commit()

            return jsonify({'message': '通知渠道配置删除成功'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/test-notification', methods=['POST'])
@login_required
def test_notification():
    """
    测试通知发送

    请求体示例:
    {
        "channel": "wecom_webhook",
        "channel_config": {
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        },
        "title": "测试通知",
        "content": "这是一条测试通知"
    }
    """
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['channel', 'channel_config']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

        # 验证通知渠道
        try:
            channel = NotifyChannel(data['channel'])
        except ValueError:
            valid_channels = [c.value for c in NotifyChannel]
            return jsonify({'error': f'无效的通知渠道，支持的渠道: {valid_channels}'}), 400

        # 解析配置
        from notifier import parse_config, NotificationSender
        config = parse_config(data['channel_config'])

        # 使用默认标题和内容，如果没有提供
        title = data.get('title', '🧪 通知测试')
        content = data.get('content', f'这是一条来自【通知定时发送系统】的测试消息。\n\n发送时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n如果您收到此消息，说明通知渠道配置正确！')

        # 发送测试通知
        try:
            NotificationSender.send(
                channel=channel,
                config=config,
                title=title,
                content=content
            )

            return jsonify({
                'success': True,
                'message': '测试通知发送成功！请检查您的通知渠道是否收到消息。'
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'发送失败: {str(e)}'
            }), 200  # 返回200但包含错误信息，便于前端处理

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'scheduler_running': scheduler.scheduler.running
    })


if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8080, debug=True)
    except KeyboardInterrupt:
        scheduler.shutdown()
