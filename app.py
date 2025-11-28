from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
from models import init_db, get_db, NotifyTask, NotifyChannel, NotifyStatus
from scheduler import scheduler
import json
import os

app = Flask(__name__, static_folder='static')
CORS(app)  # 启用跨域支持

# 初始化数据库
init_db()

# 加载待发送任务
scheduler.load_pending_tasks()


@app.route('/')
def index():
    """首页"""
    return send_from_directory('static', 'index.html')


@app.route('/api/tasks', methods=['POST'])
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
            query = db.query(NotifyTask)
            
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
def get_task(task_id):
    """获取单个任务详情"""
    try:
        db = get_db()
        try:
            task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
            if not task:
                return jsonify({'error': '任务不存在'}), 404
            
            return jsonify(task.to_dict())
            
        finally:
            db.close()
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def cancel_task(task_id):
    """取消任务"""
    try:
        db = get_db()
        try:
            task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
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
def update_task(task_id):
    """
    更新任务
    
    可更新字段: title, content, scheduled_time, channel_config
    """
    try:
        data = request.get_json()
        db = get_db()
        try:
            task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
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
def get_channels():
    """获取支持的通知渠道列表"""
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
    ]
    return jsonify({'channels': channels})


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'scheduler_running': scheduler.scheduler.running
    })


if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        scheduler.shutdown()
