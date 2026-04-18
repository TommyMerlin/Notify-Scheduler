from flask import Flask, request, jsonify, send_from_directory, Response, make_response
from flask_cors import CORS
from datetime import datetime, timezone
from models import init_db, get_db, NotifyTask, NotifyChannel, NotifyStatus, User, UserChannel, ExternalCalendar
from scheduler import scheduler, get_cron_trigger, event_manager
from auth import login_required, admin_required, user_login, user_register, update_user_profile
from encryption import encrypt_sensitive_fields, decrypt_sensitive_fields
import json
import os
import jwt
import secrets
import uuid
from sqlalchemy import or_

app = Flask(__name__, static_folder='static')
CORS(app)  # 启用跨域支持

# 配置JWT密钥
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# 初始化数据库
init_db()

# 加载待发送任务
scheduler.load_pending_tasks()
# 启动外部日历同步任务 (每15分钟)
scheduler.add_external_calendar_sync_job()


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

    支持单渠道和多渠道两种模式：
    
    单渠道模式 (向后兼容):
    {
        "title": "测试通知",
        "content": "这是一条测试通知",
        "channel": "wecom_webhook",
        "channel_config": {"webhook_url": "..."},
        "scheduled_time": "2024-12-01T10:00:00",
        "is_recurring": false
    }
    
    多渠道模式:
    {
        "title": "测试通知",
        "content": "这是一条测试通知",
        "channels": ["wecom_webhook", "pushplus"],
        "channels_config": {
            "wecom_webhook": {"webhook_url": "..."},
            "pushplus": {"token": "..."}
        },
        "scheduled_time": "2024-12-01T10:00:00",
        "is_recurring": false
    }
    """
    try:
        data = request.get_json()

        # 兼容：重复任务不再强制要求 scheduled_time，由后端根据 cron 计算下一次执行时间
        is_recurring = bool(data.get('is_recurring', False))
        cron_expression = data.get('cron_expression')

        # 检测是多渠道模式还是单渠道模式
        is_multi_channel = 'channels' in data
        
        # 验证必填字段
        required_fields = ['title', 'content']
        if is_multi_channel:
            required_fields.extend(['channels', 'channels_config'])
        else:
            required_fields.extend(['channel', 'channel_config'])
        
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
                trigger = get_cron_trigger(cron_expression)
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

        # 创建任务
        with get_db() as db:
            task = NotifyTask(
                user_id=request.current_user.id,
                title=data['title'],
                content=data['content'],
                scheduled_time=scheduled_time,
                is_recurring=is_recurring,
                cron_expression=cron_expression if is_recurring else None
            )
            
            if is_multi_channel:
                # 多渠道模式
                channels = data['channels']
                channels_config = data['channels_config']
                
                # 验证所有渠道类型
                if not isinstance(channels, list) or len(channels) == 0:
                    return jsonify({'error': 'channels 必须是非空数组'}), 400
                
                valid_channels = [c.value for c in NotifyChannel]
                for ch in channels:
                    if ch not in valid_channels:
                        return jsonify({'error': f'无效的通知渠道: {ch}，支持的渠道: {valid_channels}'}), 400
                
                # 验证每个渠道都有配置
                for ch in channels:
                    if ch not in channels_config:
                        return jsonify({'error': f'渠道 {ch} 缺少配置信息'}), 400
                
                task.channels_json = json.dumps(channels, ensure_ascii=False)
                task.channels_config_json = json.dumps(channels_config, ensure_ascii=False)
            else:
                # 单渠道模式（向后兼容）
                try:
                    channel = NotifyChannel(data['channel'])
                except ValueError:
                    valid_channels = [c.value for c in NotifyChannel]
                    return jsonify({'error': f'无效的通知渠道，支持的渠道: {valid_channels}'}), 400
                
                task.channel = channel
                task.channel_config = json.dumps(data['channel_config'], ensure_ascii=False)

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


@app.route('/api/cron/preview', methods=['POST'])
@login_required
def preview_cron():
    """
    预览 Cron 表达式的未来执行时间
    
    请求参数:
    - cron_expression: Cron 表达式字符串
    
    返回:
    - success: 成功标志
    - times: 未来5次执行时间列表（格式: 2025-12-27 14:30:00）
    - error: 错误信息（如果有）
    """
    try:
        data = request.get_json()
        cron_expression = data.get('cron_expression', '').strip()
        
        if not cron_expression:
            return jsonify({
                'success': False,
                'error': 'Cron表达式不能为空'
            }), 400
        
        try:
            # 使用现有的 get_cron_trigger 函数获取触发器
            trigger = get_cron_trigger(cron_expression)
            
            # 计算未来5次执行时间
            times = []
            # 使用本地时区的当前时间
            import pytz
            local_tz = pytz.timezone('Asia/Shanghai')
            base_time = datetime.now(local_tz)
            previous_time = None
            
            for _ in range(5):
                next_time = trigger.get_next_fire_time(previous_time, base_time)
                if not next_time:
                    break
                # 格式化为字符串: 2025-12-27 14:30:00
                times.append(next_time.strftime('%Y-%m-%d %H:%M:%S'))
                # 重要：更新previous_time和base_time，确保下次循环计算的是之后的时间
                previous_time = next_time
                base_time = next_time
            
            if not times:
                return jsonify({
                    'success': False,
                    'error': '无法计算执行时间，请检查Cron表达式'
                }), 400
            
            return jsonify({
                'success': True,
                'times': times
            }), 200
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Cron表达式格式错误: {str(e)}'
            }), 400
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tasks', methods=['GET'])
@login_required
def list_tasks():
    """
    获取任务列表

    查询参数:
    - status: 过滤状态 (pending/sent/failed/cancelled)
    - search: 按标题或内容关键词搜索
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

            # 关键词搜索
            search = request.args.get('search', '').strip()
            if search:
                search_pattern = f'%{search}%'
                query = query.filter(
                    or_(
                        NotifyTask.title.ilike(search_pattern),
                        NotifyTask.content.ilike(search_pattern)
                    )
                )

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
def delete_task(task_id):
    """彻底删除任务"""
    try:
        with get_db() as db:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            # 从调度器移除
            scheduler.remove_task(task_id, task.is_recurring)

            # 彻底删除
            db.delete(task)
            db.commit()

            return jsonify({'message': '任务已彻底删除'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    """
    更新任务

    可更新字段: title, content, scheduled_time, channel_config, channels_config, status
    支持重新启用已取消或已执行的任务，以及暂停/恢复重复任务
    支持在单渠道和多渠道模式间切换
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

            # 处理状态变更（暂停/恢复/取消）
            if 'status' in data:
                try:
                    target_status_str = data['status']
                    
                    # 取消任务 (软删除)
                    if target_status_str == 'cancelled':
                        task.status = NotifyStatus.CANCELLED
                        scheduler.remove_task(task_id, task.is_recurring)
                        db.commit()
                        return jsonify({
                            'message': '任务已取消',
                            'task': task.to_dict()
                        })

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
                                trigger = get_cron_trigger(task.cron_expression)
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

            # 更新基本字段
            if 'title' in data:
                task.title = data['title']
            if 'content' in data:
                task.content = data['content']
            
            # 处理渠道配置更新（支持单渠道和多渠道模式）
            if 'channels' in data and 'channels_config' in data:
                # 更新为多渠道模式
                channels = data['channels']
                channels_config = data['channels_config']
                
                if not isinstance(channels, list) or len(channels) == 0:
                    return jsonify({'error': 'channels 必须是非空数组'}), 400
                
                valid_channels = [c.value for c in NotifyChannel]
                for ch in channels:
                    if ch not in valid_channels:
                        return jsonify({'error': f'无效的通知渠道: {ch}'}), 400
                
                for ch in channels:
                    if ch not in channels_config:
                        return jsonify({'error': f'渠道 {ch} 缺少配置信息'}), 400
                
                task.channels_json = json.dumps(channels, ensure_ascii=False)
                task.channels_config_json = json.dumps(channels_config, ensure_ascii=False)
                # 清空单渠道字段
                task.channel = None
                task.channel_config = None
            elif 'channel_config' in data:
                # 更新单渠道模式的配置
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
                    trigger = get_cron_trigger(task.cron_expression)
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
                # 清空多渠道发送结果
                task.send_results = None

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


@app.route('/api/events')
def sse_events():
    """服务器发送事件 (SSE) 端点"""
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 401
    
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        # 尝试获取 user_id，兼容常见的 payload key
        user_id = payload.get('user_id') or payload.get('id') or payload.get('sub')
        if not user_id:
             return jsonify({'error': 'Invalid token payload'}), 401
    except Exception:
        return jsonify({'error': 'Invalid token'}), 401

    def stream():
        messages = event_manager.listen(user_id)
        try:
            while True:
                msg = messages.get()
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            pass

    return Response(stream(), mimetype='text/event-stream')


# --- 日历订阅与同步相关 API ---

@app.route('/api/calendar/token', methods=['GET', 'POST'])
@login_required
def manage_calendar_token():
    """获取或重置日历订阅Token"""
    try:
        with get_db() as db:
            user = db.query(User).filter(User.id == request.current_user.id).first()
            
            if request.method == 'POST' or not user.calendar_token:
                # 生成新Token
                user.calendar_token = secrets.token_urlsafe(32)
                db.commit()
            
            # 智能检测协议，解决反向代理下的 Mixed Content 问题导致浏览器提示"无法安全下载"
            scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
            feed_url = f"{scheme}://{request.host}/calendar/feed/{user.calendar_token}.ics"
                
            return jsonify({
                'token': user.calendar_token,
                'feed_url': feed_url
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calendar/feed/<token>.ics')
def calendar_feed(token):
    """生成 iCalendar (.ics) 订阅源"""
    try:
        with get_db() as db:
            user = db.query(User).filter(User.calendar_token == token).first()
            if not user:
                return "Invalid Token", 404
            
            tasks = db.query(NotifyTask).filter(
                NotifyTask.user_id == user.id,
                NotifyTask.status != NotifyStatus.CANCELLED
            ).all()
            
            # 构建 ICS 内容
            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Notify Scheduler//CN",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                f"X-WR-CALNAME:Notify Scheduler ({user.username})",
                "X-WR-TIMEZONE:Asia/Shanghai",
            ]
            
            for task in tasks:
                if not task.scheduled_time:
                    continue
                    
                dt_start = task.scheduled_time.strftime('%Y%m%dT%H%M%S')
                # 简单的结束时间 (开始时间 + 30分钟)
                dt_end = (task.scheduled_time.timestamp() + 1800)
                dt_end_str = datetime.fromtimestamp(dt_end).strftime('%Y%m%dT%H%M%S')
                
                lines.append("BEGIN:VEVENT")
                lines.append(f"UID:notify-task-{task.id}@{request.host}")
                lines.append(f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}")
                lines.append(f"DTSTART;TZID=Asia/Shanghai:{dt_start}")
                lines.append(f"DTEND;TZID=Asia/Shanghai:{dt_end_str}")
                lines.append(f"SUMMARY:{task.title}")
                
                # 处理描述 (转义换行)
                desc = (task.content or "").replace("\n", "\\n")
                lines.append(f"DESCRIPTION:{desc}")
                
                status_map = {
                    NotifyStatus.PENDING: 'TENTATIVE',
                    NotifyStatus.SENT: 'CONFIRMED',
                    NotifyStatus.FAILED: 'CONFIRMED',
                    NotifyStatus.PAUSED: 'CANCELLED'
                }
                lines.append(f"STATUS:{status_map.get(task.status, 'CONFIRMED')}")
                
                if task.is_recurring and task.cron_expression:
                    # 简单的 RRULE 转换 (仅支持基础 Cron 转换，复杂 Cron 难以完全映射到 RRULE)
                    # 这里仅作标记，实际日历软件可能无法完美解析所有 Cron
                    lines.append(f"X-CRON-EXPRESSION:{task.cron_expression}")
                    
                lines.append("END:VEVENT")
                
            lines.append("END:VCALENDAR")
            
            response = make_response("\r\n".join(lines))
            response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
            response.headers['Content-Disposition'] = 'attachment; filename="notify_scheduler.ics"'
            # 添加缓存控制头
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
            
    except Exception as e:
        return str(e), 500

@app.route('/api/calendar/external', methods=['GET'])
@login_required
def list_external_calendars():
    """获取外部日历列表"""
    try:
        with get_db() as db:
            cals = db.query(ExternalCalendar).filter(ExternalCalendar.user_id == request.current_user.id).all()
            return jsonify({'calendars': [c.to_dict() for c in cals]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/calendar/external', methods=['POST'])
@login_required
def add_external_calendar():
    """添加外部日历订阅"""
    try:
        data = request.get_json()
        if not data.get('name') or not data.get('url'):
            return jsonify({'error': '名称和URL不能为空'}), 400
            
        with get_db() as db:
            cal = ExternalCalendar(
                user_id=request.current_user.id,
                name=data['name'],
                url=data['url'],
                channel_id=data.get('channel_id')
            )
            db.add(cal)
            db.commit()
            
            # 立即触发一次同步
            from scheduler import sync_single_calendar
            scheduler.scheduler.add_job(
                sync_single_calendar, 
                args=[cal.id], 
                id=f"sync_cal_{cal.id}_init",
                misfire_grace_time=300
            )
            
            return jsonify({'message': '日历添加成功，正在后台同步', 'calendar': cal.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/calendar/external/<int:cal_id>', methods=['DELETE'])
@login_required
def delete_external_calendar(cal_id):
    """删除外部日历"""
    try:
        with get_db() as db:
            cal = db.query(ExternalCalendar).filter(
                ExternalCalendar.id == cal_id,
                ExternalCalendar.user_id == request.current_user.id
            ).first()
            if not cal:
                return jsonify({'error': '日历不存在'}), 404
                
            # 可选：删除该日历导入的任务
            # db.query(NotifyTask).filter(NotifyTask.external_uid.like(f"ext-{cal_id}-%")).delete(synchronize_session=False)
            
            db.delete(cal)
            db.commit()
            return jsonify({'message': '日历已删除'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/calendar/sync/<int:cal_id>', methods=['POST'])
@login_required
def sync_external_calendar_endpoint(cal_id):
    """手动触发同步"""
    try:
        with get_db() as db:
            cal = db.query(ExternalCalendar).filter(
                ExternalCalendar.id == cal_id,
                ExternalCalendar.user_id == request.current_user.id
            ).first()
            if not cal:
                return jsonify({'error': '日历不存在'}), 404
        
        from scheduler import sync_single_calendar
        # 异步执行
        scheduler.scheduler.add_job(
            sync_single_calendar, 
            args=[cal_id], 
            id=f"sync_cal_{cal_id}_manual_{uuid.uuid4().hex[:8]}",
            misfire_grace_time=300
        )
        return jsonify({'message': '同步任务已提交'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 版本信息API
@app.route('/api/version', methods=['GET'])
def get_version():
    """获取当前版本号"""
    try:
        import re
        with open('version.yml', 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'version:\s*([\d\.]+)', content)
            if match:
                version = match.group(1)
            else:
                version = '0.0.0'
        return jsonify({'version': version}), 200
    except Exception as e:
        return jsonify({'version': '0.0.0'}), 200


@app.route('/api/version/check', methods=['GET'])
def check_version_update():
    """检查 GitHub 最新版本"""
    try:
        import requests
        import re
        
        # 获取当前版本
        current_version = '0.0.0'
        try:
            with open('version.yml', 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'version:\s*([\d\.]+)', content)
                if match:
                    current_version = match.group(1)
        except:
            pass
        
        # 调用 GitHub API 获取最新 release
        response = requests.get(
            'https://api.github.com/repos/TommyMerlin/Notify-Scheduler/releases/latest',
            timeout=5
        )
        
        if response.status_code == 200:
            latest = response.json()
            latest_version = latest.get('tag_name', '').lstrip('v')
            
            # 版本对比
            def compare_versions(v1, v2):
                """比较两个版本号，v1 < v2 返回 True"""
                try:
                    parts1 = [int(x) for x in v1.split('.')]
                    parts2 = [int(x) for x in v2.split('.')]
                    # 补齐长度
                    while len(parts1) < len(parts2):
                        parts1.append(0)
                    while len(parts2) < len(parts1):
                        parts2.append(0)
                    return parts1 < parts2
                except:
                    return False
            
            update_available = compare_versions(current_version, latest_version)
            
            return jsonify({
                'current_version': current_version,
                'latest_version': latest_version,
                'update_available': update_available,
                'release_url': latest.get('html_url', ''),
                'release_notes': latest.get('body', '')
            }), 200
        else:
            return jsonify({'error': 'Failed to fetch release info'}), 500
            
    except Exception as e:
        app.logger.error(f'Version check failed: {str(e)}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/export', methods=['GET'])
@login_required
def export_data():
    """
    导出用户数据为 JSON 格式
    Export user data as JSON with encrypted sensitive fields
    """
    try:
        current_user = request.current_user
        secret_key = app.config['SECRET_KEY']
        
        with get_db() as db:
            # 导出任务
            tasks = db.query(NotifyTask).filter_by(user_id=current_user.id).all()
            tasks_data = []
            for task in tasks:
                task_dict = {
                    'title': task.title,
                    'content': task.content,
                    'channel': task.channel.value if task.channel else None,
                    'scheduled_time': task.scheduled_time.isoformat() if task.scheduled_time else None,
                    'channel_config': task.channel_config,
                    'channels': task.channels_json,
                    'channel_configs': task.channels_config_json,
                    'status': task.status.value,
                    'is_recurring': task.is_recurring,
                    'cron_expression': task.cron_expression,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                }
                
                # 加密单通道配置
                if task_dict['channel_config']:
                    try:
                        config_dict = json.loads(task_dict['channel_config'])
                        encrypted_config = encrypt_sensitive_fields(config_dict, secret_key)
                        task_dict['channel_config'] = json.dumps(encrypted_config)
                    except:
                        pass
                
                # 加密多通道配置
                if task_dict['channel_configs']:
                    try:
                        configs_dict = json.loads(task_dict['channel_configs'])
                        encrypted_configs = {}
                        for channel, config in configs_dict.items():
                            encrypted_configs[channel] = encrypt_sensitive_fields(config, secret_key)
                        task_dict['channel_configs'] = json.dumps(encrypted_configs)
                    except:
                        pass
                
                tasks_data.append(task_dict)
            
            # 导出通道配置
            user_channels = db.query(UserChannel).filter_by(user_id=current_user.id).all()
            channels_data = []
            for channel in user_channels:
                channel_dict = {
                    'channel_name': channel.channel_name,
                    'channel_type': channel.channel_type.value,
                    'channel_config': channel.channel_config,
                    'is_default': channel.is_default,
                    'created_at': channel.created_at.isoformat() if channel.created_at else None,
                }
                
                # 加密通道配置
                if channel_dict['channel_config']:
                    try:
                        config_dict = json.loads(channel_dict['channel_config'])
                        encrypted_config = encrypt_sensitive_fields(config_dict, secret_key)
                        channel_dict['channel_config'] = json.dumps(encrypted_config)
                    except:
                        pass
                
                channels_data.append(channel_dict)
            
            # 导出外部日历
            external_calendars = db.query(ExternalCalendar).filter_by(user_id=current_user.id).all()
            calendars_data = []
            for calendar in external_calendars:
                calendar_dict = {
                    'name': calendar.name,
                    'url': calendar.url,
                    'is_active': calendar.is_active,
                    'default_channel_id': None,  # 不导出内部 ID
                }
                
                # 如果有默认通道，尝试找到对应的通道名称
                if calendar.default_channel_id:
                    default_channel = db.query(UserChannel).filter_by(
                        id=calendar.default_channel_id,
                        user_id=current_user.id
                    ).first()
                    if default_channel:
                        calendar_dict['default_channel_name'] = default_channel.channel_name
                
                calendars_data.append(calendar_dict)
        
        # 构建导出数据（在 with 块外，使用已收集的数据）
        export_payload = {
            'version': '1.0',
            'export_date': datetime.now().isoformat(),
            'tasks': tasks_data,
            'user_channels': channels_data,
            'external_calendars': calendars_data,
        }
        
        # 设置响应头，触发下载
        filename = f'notify-scheduler-export-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
        response = make_response(jsonify(export_payload))
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        response.headers['Content-Type'] = 'application/json'
        
        return response
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        app.logger.error(f'Export failed: {str(e)}\n{error_detail}')
        return jsonify({'error': f'导出失败: {str(e)}'}), 500


@app.route('/api/import', methods=['POST'])
@login_required
def import_data():
    """
    导入用户数据（合并模式 - 跳过重复）
    Import user data with merge mode (skip duplicates)
    """
    try:
        current_user = request.current_user
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的导入数据'}), 400
        
        # 验证数据版本
        if data.get('version') != '1.0':
            return jsonify({'error': '不支持的数据版本'}), 400
        
        secret_key = app.config['SECRET_KEY']
        
        stats = {
            'tasks_imported': 0,
            'tasks_skipped': 0,
            'channels_imported': 0,
            'channels_skipped': 0,
            'calendars_imported': 0,
            'calendars_skipped': 0,
        }
        
        with get_db() as db:
            # 导入通道配置（先导入，因为任务可能依赖它们）
            if 'user_channels' in data:
                for channel_data in data['user_channels']:
                    # 检查是否已存在同名通道
                    existing = db.query(UserChannel).filter_by(
                        user_id=current_user.id,
                        channel_name=channel_data['channel_name']
                    ).first()
                    
                    if existing:
                        stats['channels_skipped'] += 1
                        continue
                    
                    # 解密配置
                    channel_config = channel_data.get('channel_config')
                    if channel_config:
                        try:
                            config_dict = json.loads(channel_config)
                            decrypted_config = decrypt_sensitive_fields(config_dict, secret_key)
                            channel_config = json.dumps(decrypted_config)
                        except:
                            pass
                    
                    # 创建新通道
                    new_channel = UserChannel(
                        user_id=current_user.id,
                        channel_name=channel_data['channel_name'],
                        channel_type=NotifyChannel(channel_data['channel_type']),
                        channel_config=channel_config,
                        is_default=channel_data.get('is_default', False),
                    )
                    db.add(new_channel)
                    stats['channels_imported'] += 1
            
            db.commit()
            
            # 导入任务
            if 'tasks' in data:
                for task_data in data['tasks']:
                    # 检查重复：相同标题和计划时间
                    scheduled_time = None
                    if task_data.get('scheduled_time'):
                        try:
                            scheduled_time = datetime.fromisoformat(task_data['scheduled_time'])
                        except:
                            pass
                    
                    # 对于定时任务，检查标题+时间；对于周期任务，只检查标题+cron
                    if task_data.get('is_recurring'):
                        existing = db.query(NotifyTask).filter_by(
                            user_id=current_user.id,
                            title=task_data['title'],
                            cron_expression=task_data.get('cron_expression')
                        ).first()
                    else:
                        existing = db.query(NotifyTask).filter_by(
                            user_id=current_user.id,
                            title=task_data['title'],
                            scheduled_time=scheduled_time
                        ).first()
                    
                    if existing:
                        stats['tasks_skipped'] += 1
                        continue
                    
                    # 解密通道配置
                    channel_config = task_data.get('channel_config')
                    if channel_config:
                        try:
                            config_dict = json.loads(channel_config)
                            decrypted_config = decrypt_sensitive_fields(config_dict, secret_key)
                            channel_config = json.dumps(decrypted_config)
                        except:
                            pass
                    
                    # 解密多通道配置
                    channel_configs = task_data.get('channel_configs')
                    if channel_configs:
                        try:
                            configs_dict = json.loads(channel_configs)
                            decrypted_configs = {}
                            for channel, config in configs_dict.items():
                                decrypted_configs[channel] = decrypt_sensitive_fields(config, secret_key)
                            channel_configs = json.dumps(decrypted_configs)
                        except:
                            pass
                    
                    # 创建新任务
                    new_task = NotifyTask(
                        user_id=current_user.id,
                        title=task_data['title'],
                        content=task_data.get('content', ''),
                        channel=NotifyChannel(task_data['channel']) if task_data.get('channel') else None,
                        scheduled_time=scheduled_time,
                        channel_config=channel_config,
                        channels_json=task_data.get('channels'),
                        channels_config_json=channel_configs,
                        status=NotifyStatus(task_data.get('status', 'pending')),
                        is_recurring=task_data.get('is_recurring', False),
                        cron_expression=task_data.get('cron_expression'),
                    )
                    db.add(new_task)
                    stats['tasks_imported'] += 1
                    
                    # 如果是待发送的任务，加入调度器
                    if new_task.status == NotifyStatus.PENDING:
                        db.commit()  # 先提交获取 ID
                        db.refresh(new_task)  # 刷新对象获取最新数据
                        scheduler.add_task(new_task)
            
            db.commit()
            
            # 导入外部日历
            if 'external_calendars' in data:
                for calendar_data in data['external_calendars']:
                    # 检查是否已存在同名日历
                    existing = db.query(ExternalCalendar).filter_by(
                        user_id=current_user.id,
                        name=calendar_data['name']
                    ).first()
                    
                    if existing:
                        stats['calendars_skipped'] += 1
                        continue
                    
                    # 查找默认通道
                    default_channel_id = None
                    if calendar_data.get('default_channel_name'):
                        default_channel = db.query(UserChannel).filter_by(
                            user_id=current_user.id,
                            channel_name=calendar_data['default_channel_name']
                        ).first()
                        if default_channel:
                            default_channel_id = default_channel.id
                    
                    # 创建新日历
                    new_calendar = ExternalCalendar(
                        user_id=current_user.id,
                        name=calendar_data['name'],
                        url=calendar_data['url'],
                        default_channel_id=default_channel_id,
                        is_active=calendar_data.get('is_active', True),
                    )
                    db.add(new_calendar)
                    stats['calendars_imported'] += 1
            
            db.commit()
        
        return jsonify({
            'message': '导入成功',
            'stats': stats
        }), 200
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        app.logger.error(f'Import failed: {str(e)}\n{error_detail}')
        return jsonify({'error': f'导入失败: {str(e)}'}), 500


if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8080, debug=True)
    except KeyboardInterrupt:
        scheduler.shutdown()
