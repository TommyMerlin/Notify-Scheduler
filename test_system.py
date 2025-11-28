"""
系统功能测试脚本
这个脚本会测试基本的数据库和调度功能（不实际发送通知）
"""
from datetime import datetime, timedelta
from models import init_db, get_db, NotifyTask, NotifyChannel, NotifyStatus
from scheduler import scheduler
import json

def test_database():
    """测试数据库功能"""
    print("=" * 50)
    print("测试数据库功能")
    print("=" * 50)
    
    # 初始化数据库
    init_db()
    print("✓ 数据库初始化成功")
    
    # 创建测试任务
    db = get_db()
    try:
        task = NotifyTask(
            title="测试任务",
            content="这是一个测试任务",
            channel=NotifyChannel.WECOM_WEBHOOK,
            scheduled_time=datetime.now() + timedelta(minutes=1),
            channel_config=json.dumps({
                "webhook_url": "https://test.example.com/webhook"
            })
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"✓ 创建任务成功，任务 ID: {task.id}")
        
        # 查询任务
        retrieved_task = db.query(NotifyTask).filter(NotifyTask.id == task.id).first()
        if retrieved_task:
            print(f"✓ 查询任务成功: {retrieved_task.title}")
        
        # 更新任务
        retrieved_task.title = "更新后的任务标题"
        db.commit()
        print("✓ 更新任务成功")
        
        # 删除测试任务
        db.delete(retrieved_task)
        db.commit()
        print("✓ 删除任务成功")
        
        return True
    except Exception as e:
        print(f"✗ 数据库测试失败: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()


def test_scheduler():
    """测试调度器功能"""
    print("\n" + "=" * 50)
    print("测试调度器功能")
    print("=" * 50)
    
    try:
        # 创建一个测试任务
        db = get_db()
        task = NotifyTask(
            title="调度器测试任务",
            content="测试调度器是否正常工作",
            channel=NotifyChannel.WECOM_WEBHOOK,
            scheduled_time=datetime.now() + timedelta(seconds=30),
            channel_config=json.dumps({
                "webhook_url": "https://test.example.com/webhook"
            })
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"✓ 创建测试任务，ID: {task.id}")
        
        # 添加到调度器
        scheduler.add_task(task)
        print("✓ 任务添加到调度器成功")
        
        # 获取调度器中的任务
        jobs = scheduler.get_scheduled_jobs()
        print(f"✓ 调度器中有 {len(jobs)} 个任务")
        
        if jobs:
            for job in jobs:
                print(f"  - 任务: {job['id']}, 下次执行: {job['next_run_time']}")
        
        # 从调度器移除任务
        scheduler.remove_task(task.id)
        print("✓ 从调度器移除任务成功")
        
        # 清理测试数据
        db.delete(task)
        db.commit()
        
        db.close()
        return True
    except Exception as e:
        print(f"✗ 调度器测试失败: {str(e)}")
        return False


def test_task_to_dict():
    """测试任务对象转字典"""
    print("\n" + "=" * 50)
    print("测试任务序列化")
    print("=" * 50)
    
    try:
        db = get_db()
        task = NotifyTask(
            title="序列化测试",
            content="测试 to_dict 方法",
            channel=NotifyChannel.PUSHPLUS,
            scheduled_time=datetime.now() + timedelta(hours=1),
            channel_config=json.dumps({"token": "test_token"})
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 转换为字典
        task_dict = task.to_dict()
        print("✓ 任务转字典成功:")
        print(json.dumps(task_dict, indent=2, ensure_ascii=False))
        
        # 清理
        db.delete(task)
        db.commit()
        db.close()
        
        return True
    except Exception as e:
        print(f"✗ 序列化测试失败: {str(e)}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "🚀 开始系统功能测试\n")
    
    results = []
    
    # 测试数据库
    results.append(("数据库功能", test_database()))
    
    # 测试调度器
    results.append(("调度器功能", test_scheduler()))
    
    # 测试序列化
    results.append(("任务序列化", test_task_to_dict()))
    
    # 输出测试结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    all_passed = True
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查错误信息")
    print("=" * 50 + "\n")
    
    # 关闭调度器
    scheduler.shutdown()


if __name__ == '__main__':
    main()
