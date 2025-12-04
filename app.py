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

        # 验证必填字段
        required_fields = ['title', 'content', 'channel', 'scheduled_time', 'channel_config']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

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
        db = get_db()
        try:
            task = NotifyTask(
                user_id=request.current_user.id,
                title=data['title'],
                content=data['content'],
                channel=channel,
                scheduled_time=scheduled_time,
                channel_config=json.dumps(data['channel_config'], ensure_ascii=False),
                is_recurring=data.get('is_recurring', False),
                cron_expression=data.get('cron_expression')
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

        finally:
            db.close()

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
    """
    try:
        db = get_db()
        try:
            query = db.query(NotifyTask).filter(NotifyTask.user_id == request.current_user.id)

            # 状态过滤
            status = request.args.get('status')
            if status:
                try:
                    status_enum = NotifyStatus(status)
                    query = query.filter(NotifyTask.status == status_enum)
                except ValueError:
                    return jsonify({'error': f'无效的状态值: {status}'}), 400

            # 分页
            page = int(request.args.get('page', 1))
            page_size = int(request.args.get('page_size', 20))

            total = query.count()
            tasks = query.order_by(NotifyTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

            return jsonify({
                'total': total,
                'page': page,
                'page_size': page_size,
                'tasks': [task.to_dict() for task in tasks]
            })

        finally:
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    """获取单个任务详情"""
    try:
        db = get_db()
        try:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            return jsonify(task.to_dict())

        finally:
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def cancel_task(task_id):
    """取消任务"""
    try:
        db = get_db()
        try:
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

        finally:
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    """
    更新任务

    可更新字段: title, content, scheduled_time, channel_config
    """
    try:
        data = request.get_json()
        db = get_db()
        try:
            task = db.query(NotifyTask).filter(
                NotifyTask.id == task_id,
                NotifyTask.user_id == request.current_user.id
            ).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            # 只允许更新待发送的任务
            if task.status != NotifyStatus.PENDING:
                return jsonify({'error': '只能更新待发送的任务'}), 400

            # 更新字段
            if 'title' in data:
                task.title = data['title']
            if 'content' in data:
                task.content = data['content']
            if 'scheduled_time' in data:
                try:
                    task.scheduled_time = datetime.fromisoformat(data['scheduled_time'])
                except ValueError:
                    return jsonify({'error': '时间格式错误'}), 400
            if 'channel_config' in data:
                task.channel_config = json.dumps(data['channel_config'], ensure_ascii=False)

            db.commit()

            # 重新添加到调度器
            scheduler.remove_task(task_id, task.is_recurring)
            scheduler.add_task(task)

            return jsonify({
                'message': '任务更新成功',
                'task': task.to_dict()
            })

        finally:
            db.close()

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
        db = get_db()
        try:
            user_channels = db.query(UserChannel).filter(
                UserChannel.user_id == request.current_user.id
            ).all()

            return jsonify({
                'channels': [channel.to_dict() for channel in user_channels]
            })

        finally:
            db.close()

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

        db = get_db()
        try:
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

        finally:
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/channels/<int:channel_id>', methods=['PUT'])
@login_required
def update_user_channel(channel_id):
    """更新用户通知渠道配置"""
    try:
        data = request.get_json()
        db = get_db()
        try:
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

        finally:
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/channels/<int:channel_id>', methods=['DELETE'])
@login_required
def delete_user_channel(channel_id):
    """删除用户通知渠道配置"""
    try:
        db = get_db()
        try:
            channel = db.query(UserChannel).filter(
                UserChannel.id == channel_id,
                UserChannel.user_id == request.current_user.id
            ).first()
            if not channel:
                return jsonify({'error': '通知渠道配置不存在'}), 404

            db.delete(channel)
            db.commit()

            return jsonify({'message': '通知渠道配置删除成功'})

        finally:
            db.close()

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
