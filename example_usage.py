"""
通知定时发送系统使用示例
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://localhost:5000/api'


def create_wecom_webhook_task():
    """创建企业微信 Webhook 通知任务示例"""
    # 计划5分钟后发送
    scheduled_time = (datetime.now() + timedelta(minutes=5)).isoformat()
    
    task_data = {
        "title": "测试通知",
        "content": "这是一条定时测试通知，将在5分钟后发送",
        "channel": "wecom_webhook",
        "scheduled_time": scheduled_time,
        "channel_config": {
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
        }
    }
    
    response = requests.post(f'{BASE_URL}/tasks', json=task_data)
    print("创建任务响应:", response.json())
    return response.json()


def create_recurring_task():
    """创建重复任务示例 - 每天早上9点发送"""
    task_data = {
        "title": "每日提醒",
        "content": "这是每天早上9点的定时提醒",
        "channel": "wecom_webhook",
        "scheduled_time": datetime.now().isoformat(),  # 首次执行时间
        "channel_config": {
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
        },
        "is_recurring": True,
        "cron_expression": "0 9 * * *"  # 每天早上9点
    }
    
    response = requests.post(f'{BASE_URL}/tasks', json=task_data)
    print("创建重复任务响应:", response.json())
    return response.json()


def create_feishu_webhook_task():
    """创建飞书 Webhook 通知任务示例"""
    scheduled_time = (datetime.now() + timedelta(hours=1)).isoformat()
    
    task_data = {
        "title": "飞书通知测试",
        "content": "这是一条飞书测试通知，将在1小时后发送",
        "channel": "feishu_webhook",
        "scheduled_time": scheduled_time,
        "channel_config": {
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_HERE"
        }
    }
    
    response = requests.post(f'{BASE_URL}/tasks', json=task_data)
    print("创建飞书任务响应:", response.json())
    return response.json()


def list_tasks(status=None):
    """列出所有任务"""
    params = {}
    if status:
        params['status'] = status
    
    response = requests.get(f'{BASE_URL}/tasks', params=params)
    print("任务列表:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.json()


def get_task(task_id):
    """获取任务详情"""
    response = requests.get(f'{BASE_URL}/tasks/{task_id}')
    print("任务详情:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.json()


def update_task(task_id, updates):
    """更新任务"""
    response = requests.put(f'{BASE_URL}/tasks/{task_id}', json=updates)
    print("更新任务响应:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.json()


def cancel_task(task_id):
    """取消任务"""
    response = requests.delete(f'{BASE_URL}/tasks/{task_id}')
    print("取消任务响应:", response.json())
    return response.json()


def get_channels():
    """获取支持的通知渠道"""
    response = requests.get(f'{BASE_URL}/channels')
    print("支持的通知渠道:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.json()


def get_scheduler_jobs():
    """获取调度器中的任务"""
    response = requests.get(f'{BASE_URL}/scheduler/jobs')
    print("调度器任务:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.json()


if __name__ == '__main__':
    print("=== 通知定时发送系统使用示例 ===\n")
    
    # 1. 获取支持的通知渠道
    print("1. 获取支持的通知渠道")
    get_channels()
    print("\n" + "="*50 + "\n")
    
    # 2. 创建一个企业微信 Webhook 任务
    print("2. 创建企业微信 Webhook 通知任务")
    result = create_wecom_webhook_task()
    if 'task' in result:
        task_id = result['task']['id']
        print(f"任务 ID: {task_id}")
        print("\n" + "="*50 + "\n")
        
        # 3. 查看任务详情
        print("3. 查看任务详情")
        get_task(task_id)
        print("\n" + "="*50 + "\n")
        
        # 4. 更新任务
        print("4. 更新任务内容")
        update_task(task_id, {
            "content": "这是更新后的通知内容"
        })
        print("\n" + "="*50 + "\n")
    
    # 5. 列出所有待发送的任务
    print("5. 列出所有待发送的任务")
    list_tasks(status='pending')
    print("\n" + "="*50 + "\n")
    
    # 6. 查看调度器中的任务
    print("6. 查看调度器中的任务")
    get_scheduler_jobs()
    print("\n" + "="*50 + "\n")
    
    # 7. 创建重复任务示例（注释掉，避免实际创建）
    # print("7. 创建重复任务")
    # create_recurring_task()
    # print("\n" + "="*50 + "\n")
    
    print("示例执行完成！")
    print("\n注意：")
    print("1. 请在配置中填入真实的 Webhook URL 或 Token")
    print("2. 任务会在指定时间自动发送通知")
    print("3. 可以通过 API 随时取消或更新待发送的任务")
