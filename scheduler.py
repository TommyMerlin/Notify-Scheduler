from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from models import NotifyTask, NotifyStatus, ExternalCalendar, UserChannel, get_db, DATABASE_URL
from notifier import NotificationSender, parse_config
from hooks import execute_hook
import logging
import queue
import requests
import re
import traceback
import socket
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventManager:
    def __init__(self):
        # listeners: list of (queue, user_id)
        self.listeners = []

    def listen(self, user_id):
        q = queue.Queue(maxsize=10)
        self.listeners.append((q, user_id))
        return q

    def announce(self, user_id, msg):
        for i in range(len(self.listeners) - 1, -1, -1):
            q, uid = self.listeners[i]
            if uid == user_id:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    del self.listeners[i]

event_manager = EventManager()


def get_cron_trigger(expression):
    """根据 cron 表达式获取触发器，支持 5 位 (分时日月周) 和 6 位 (秒分时日月周)"""
    values = expression.strip().split()
    if len(values) == 6:
        return CronTrigger(
            second=values[0],
            minute=values[1],
            hour=values[2],
            day=values[3],
            month=values[4],
            day_of_week=values[5]
        )
    return CronTrigger.from_crontab(expression)


# ============ 模块级函数（用于 APScheduler job，避免序列化问题） ============

def execute_task(task_id: int):
    """
    执行通知任务（模块级函数，可被序列化）
    
    Args:
        task_id: 任务ID
    """
    from models import TaskExecutionLog
    
    execution_start = datetime.now()
    worker_id = f"{os.getpid()}"
    hostname = socket.gethostname()
    job_id = None
    log = None
    
    with get_db() as db:
        try:
            # 获取任务
            task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return

            job_id = f"recurring_task_{task_id}" if task.is_recurring else f"task_{task_id}"
            
            # 生成重复检测键（精确到秒）
            duplicate_check_key = f"{task_id}_{execution_start.strftime('%Y%m%d%H%M%S')}"
            
            # 重复执行检测 - 检查最近3秒内是否有相同任务执行
            recent_logs = db.query(TaskExecutionLog).filter(
                TaskExecutionLog.task_id == task_id,
                TaskExecutionLog.execution_start >= execution_start - timedelta(seconds=3),
                TaskExecutionLog.status.in_(['started', 'success'])
            ).all()
            
            is_duplicate = len(recent_logs) > 0
            if is_duplicate:
                logger.warning(f"⚠️ 检测到任务 {task_id} 重复执行（最近3秒内已执行），本次跳过")
                # 不记录跳过的日志，直接返回
                
                # 触发告警
                try:
                    check_and_alert(task_id, 'duplicate_execution', db)
                except Exception as alert_err:
                    logger.error(f"触发告警失败: {str(alert_err)}")
                return

            # 如果任务已取消，跳过执行
            if task.status == NotifyStatus.CANCELLED:
                logger.info(f"任务 {task_id} 已取消，跳过执行")
                return

            # 检查暂停状态
            if task.status == NotifyStatus.PAUSED:
                logger.info(f"任务 {task_id} 已暂停，跳过执行")
                return
            
            # 记录开始执行
            log = TaskExecutionLog(
                task_id=task_id,
                job_id=job_id,
                execution_start=execution_start,
                status='started',
                worker_id=worker_id,
                hostname=hostname,
                duplicate_check_key=duplicate_check_key
            )
            db.add(log)
            db.commit()

            logger.info(f"✓ 开始执行任务 {task_id}: {task.title} (Worker: {worker_id})")

            # 执行 before_execute 钩子
            try:
                hook_result = execute_hook(
                    hook_type='before_execute',
                    task_id=task_id,
                    task=task,
                    context={},
                    db_session=db,
                    task_execution_log_id=log.id
                )
                if not hook_result.get('success') and not hook_result.get('skipped'):
                    logger.warning(f"before_execute 钩子执行失败: {hook_result.get('error')}")
            except Exception as hook_err:
                logger.error(f"执行 before_execute 钩子时出错: {str(hook_err)}")

            # 检测是多渠道还是单渠道任务
            is_multi_channel = task.channels_json is not None
            
            if is_multi_channel:
                # 多渠道模式
                try:
                    channels = json.loads(task.channels_json)
                    channels_config = json.loads(task.channels_config_json)
                except (json.JSONDecodeError, TypeError) as e:
                    raise Exception(f"配置解析失败: {str(e)}")
                
                send_results = {}
                success_count = 0
                fail_count = 0
                
                # 遍历所有渠道发送通知
                for channel_str in channels:
                    try:
                        from models import NotifyChannel
                        channel = NotifyChannel(channel_str)
                        config = parse_config(channels_config.get(channel_str, {}))
                        
                        logger.info(f"任务 {task_id} 向渠道 {channel_str} 发送通知")
                        NotificationSender.send(
                            channel=channel,
                            config=config,
                            title=task.title,
                            content=task.content
                        )
                        
                        send_results[channel_str] = {
                            'status': 'sent',
                            'message': '发送成功',
                            'sent_time': datetime.now().isoformat()
                        }
                        success_count += 1
                        logger.info(f"任务 {task_id} 渠道 {channel_str} 发送成功")
                        
                    except Exception as e:
                        send_results[channel_str] = {
                            'status': 'failed',
                            'message': str(e),
                            'sent_time': datetime.now().isoformat()
                        }
                        fail_count += 1
                        logger.error(f"任务 {task_id} 渠道 {channel_str} 发送失败: {str(e)}")
                
                # 更新任务状态
                if not task.is_recurring:
                    if success_count > 0:
                        task.status = NotifyStatus.SENT
                    else:
                        task.status = NotifyStatus.FAILED
                
                task.sent_time = datetime.now()
                task.send_results = json.dumps(send_results, ensure_ascii=False)
                
                # 设置错误信息（如果有失败）
                if fail_count > 0:
                    task.error_msg = f"{success_count}/{len(channels)} 个渠道发送成功，{fail_count} 个失败"
                else:
                    task.error_msg = None
                
                # 重复任务执行成功后，滚动更新下一次执行时间
                if task.is_recurring and task.cron_expression:
                    try:
                        trigger = get_cron_trigger(task.cron_expression)
                        base_time = datetime.now()
                        next_run = trigger.get_next_fire_time(None, base_time)
                        if next_run:
                            task.scheduled_time = next_run
                    except Exception as e:
                        logger.warning(f"任务 {task_id} 更新下一次执行时间失败: {str(e)}")
                
                # 更新执行日志
                execution_end = datetime.now()
                duration = (execution_end - execution_start).total_seconds()
                log.execution_end = execution_end
                log.execution_duration = duration
                log.status = 'success' if success_count > 0 else 'failed'
                log.result_summary = f"多渠道执行完成: {success_count} 成功, {fail_count} 失败"
                log.channel_results = json.dumps(send_results, ensure_ascii=False)
                log.success_count = success_count
                log.failed_count = fail_count
                
                logger.info(f"✓ 任务 {task_id} 多渠道执行完成: {success_count} 成功, {fail_count} 失败，耗时 {duration:.2f}秒")
                
                # 执行 after_success 钩子
                if success_count > 0:
                    try:
                        hook_result = execute_hook(
                            hook_type='after_success',
                            task_id=task_id,
                            task=task,
                            context={'send_results': send_results},
                            db_session=db,
                            task_execution_log_id=log.id
                        )
                        if not hook_result.get('success') and not hook_result.get('skipped'):
                            logger.warning(f"after_success 钩子执行失败: {hook_result.get('error')}")
                    except Exception as hook_err:
                        logger.error(f"执行 after_success 钩子时出错: {str(hook_err)}")
                
                # 通知前端
                event_manager.announce(task.user_id, {
                    'type': 'task_executed',
                    'task_id': task.id,
                    'title': task.title,
                    'status': 'sent' if success_count > 0 else 'failed',
                    'message': f'{success_count}/{len(channels)} 个渠道发送成功'
                })
                
            else:
                # 单渠道模式（向后兼容）
                config = parse_config(task.channel_config)

                # 发送通知
                NotificationSender.send(
                    channel=task.channel,
                    config=config,
                    title=task.title,
                    content=task.content
                )

                # 更新任务状态
                if not task.is_recurring:
                    task.status = NotifyStatus.SENT
                task.sent_time = datetime.now()
                task.error_msg = None

                # 重复任务执行成功后，滚动更新下一次执行时间
                if task.is_recurring and task.cron_expression:
                    try:
                        trigger = get_cron_trigger(task.cron_expression)
                        base_time = datetime.now()
                        next_run = trigger.get_next_fire_time(None, base_time)
                        if next_run:
                            task.scheduled_time = next_run
                    except Exception as e:
                        logger.warning(f"任务 {task_id} 更新下一次执行时间失败: {str(e)}")
                
                # 更新执行日志
                execution_end = datetime.now()
                duration = (execution_end - execution_start).total_seconds()
                log.execution_end = execution_end
                log.execution_duration = duration
                log.status = 'success'
                log.result_summary = '单渠道发送成功'
                log.success_count = 1
                log.failed_count = 0

                logger.info(f"✓ 任务 {task_id} 执行成功，耗时 {duration:.2f}秒")
                
                # 执行 after_success 钩子
                try:
                    hook_result = execute_hook(
                        hook_type='after_success',
                        task_id=task_id,
                        task=task,
                        context={'send_results': {'single_channel': {'status': 'sent'}}},
                        db_session=db,
                        task_execution_log_id=log.id
                    )
                    if not hook_result.get('success') and not hook_result.get('skipped'):
                        logger.warning(f"after_success 钩子执行失败: {hook_result.get('error')}")
                except Exception as hook_err:
                    logger.error(f"执行 after_success 钩子时出错: {str(hook_err)}")
                
                # 通知前端
                event_manager.announce(task.user_id, {
                    'type': 'task_executed',
                    'task_id': task.id,
                    'title': task.title,
                    'status': 'sent',
                    'message': '发送成功'
                })

            db.commit()

        except Exception as e:
            # 执行失败
            execution_end = datetime.now()
            duration = (execution_end - execution_start).total_seconds() if execution_start else 0
            
            if log:
                log.execution_end = execution_end
                log.execution_duration = duration
                log.status = 'failed'
                log.error_message = str(e)
                log.error_traceback = traceback.format_exc()
            
            # 更新任务状态
            try:
                task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
                if task:
                    task.status = NotifyStatus.FAILED
                    task.error_msg = str(e)
                    
                    # 通知前端
                    event_manager.announce(task.user_id, {
                        'type': 'task_executed',
                        'task_id': task.id,
                        'title': task.title,
                        'status': 'failed',
                        'message': str(e)
                    })
            except:
                pass
            
            db.commit()
            logger.error(f"✗ 任务 {task_id} 执行失败: {str(e)}\n{traceback.format_exc()}")
            
            # 执行 after_failure 钩子
            try:
                task_obj = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
                if task_obj:
                    hook_result = execute_hook(
                        hook_type='after_failure',
                        task_id=task_id,
                        task=task_obj,
                        context={'error': str(e), 'traceback': traceback.format_exc()},
                        db_session=db,
                        task_execution_log_id=log.id if log else None
                    )
                    if not hook_result.get('success') and not hook_result.get('skipped'):
                        logger.warning(f"after_failure 钩子执行失败: {hook_result.get('error')}")
            except Exception as hook_err:
                logger.error(f"执行 after_failure 钩子时出错: {str(hook_err)}")
            
            # 触发告警
            try:
                check_and_alert(task_id, 'execution_failure', db)
            except Exception as alert_err:
                logger.error(f"触发告警失败: {str(alert_err)}")


def check_and_alert(task_id: int, alert_type: str, db_session):
    """
    检查并触发告警（模块级函数）
    
    Args:
        task_id: 任务ID
        alert_type: 告警类型 (duplicate_execution, execution_failure)
        db_session: 数据库会话
    """
    try:
        from models import AlertRule, TaskExecutionLog
        
        # 查询任务和用户的告警规则
        task = db_session.query(NotifyTask).filter(NotifyTask.id == task_id).first()
        if not task:
            return
        
        rules = db_session.query(AlertRule).filter(
            AlertRule.user_id == task.user_id,
            AlertRule.rule_type == alert_type,
            AlertRule.is_enabled == True
        ).all()
        
        for rule in rules:
            params = json.loads(rule.rule_params) if rule.rule_params else {}
            
            if alert_type == 'duplicate_execution':
                # 检查时间窗口内的重复执行次数
                time_window = params.get('time_window', 300)  # 默认5分钟
                threshold = params.get('threshold', 2)
                
                recent_duplicates = db_session.query(TaskExecutionLog).filter(
                    TaskExecutionLog.task_id == task_id,
                    TaskExecutionLog.is_duplicate == True,
                    TaskExecutionLog.execution_start >= datetime.now() - timedelta(seconds=time_window)
                ).count()
                
                if recent_duplicates >= threshold:
                    send_alert(rule, task, f"任务在{time_window}秒内重复执行{recent_duplicates}次", db_session)
            
            elif alert_type == 'execution_failure':
                # 检查失败率
                time_window = params.get('time_window', 3600)  # 默认1小时
                failure_threshold = params.get('threshold', 3)
                
                recent_failures = db_session.query(TaskExecutionLog).filter(
                    TaskExecutionLog.task_id == task_id,
                    TaskExecutionLog.status == 'failed',
                    TaskExecutionLog.execution_start >= datetime.now() - timedelta(seconds=time_window)
                ).count()
                
                if recent_failures >= failure_threshold:
                    send_alert(rule, task, f"任务在{time_window}秒内失败{recent_failures}次", db_session)
    
    except Exception as e:
        logger.error(f"告警检查失败: {str(e)}")


def send_alert(rule, task: NotifyTask, message: str, db_session):
    """
    发送告警通知（模块级函数）
    
    Args:
        rule: 告警规则对象
        task: 任务对象
        message: 告警消息
        db_session: 数据库会话
    """
    try:
        if not rule.alert_channel:
            logger.warning(f"告警规则 {rule.id} 未配置告警渠道")
            return
        
        config = parse_config(rule.alert_channel.channel_config)
        title = f"⚠️ 任务告警: {task.title}"
        content = f"""
任务ID: {task.id}
任务名称: {task.title}
告警类型: {rule.rule_type}
告警信息: {message}
告警时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

请及时检查任务状态。
"""
        
        NotificationSender.send(
            channel=rule.alert_channel.channel_type,
            config=config,
            title=title,
            content=content
        )
        logger.info(f"✓ 告警通知已发送: {message}")
    except Exception as e:
        logger.error(f"✗ 发送告警失败: {str(e)}")


class NotifyScheduler:
    """通知调度器"""
    
    def __init__(self):
        # 配置 jobstore - 使用 SQLAlchemy 持久化存储
        jobstores = {
            'default': SQLAlchemyJobStore(url=DATABASE_URL, tablename='apscheduler_jobs')
        }
        
        # 配置执行器
        executors = {
            'default': ThreadPoolExecutor(max_workers=10)
        }
        
        # 调度器全局配置 - 防止任务重复执行的关键配置
        job_defaults = {
            'coalesce': True,           # 合并错过的执行，只执行最新一次
            'max_instances': 1,         # 每个任务最多同时运行1个实例（防重复关键）
            'misfire_grace_time': 60    # 错过时间容忍度60秒
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Shanghai'
        )
        self.scheduler.start()
        logger.info("通知调度器已启动（使用SQLAlchemyJobStore防重复执行）")
    
    def add_task(self, task: NotifyTask):
        """
        添加通知任务到调度器
        
        Args:
            task: 通知任务对象
        """
        if task.is_recurring and task.cron_expression:
            # 重复任务，使用 cron 表达式
            try:
                trigger = get_cron_trigger(task.cron_expression)
                job_id = f"recurring_task_{task.id}"
                
                self.scheduler.add_job(
                    func=execute_task,
                    trigger=trigger,
                    args=[task.id],
                    id=job_id,
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=60
                )
                logger.info(f"任务 {task.id} 已添加到调度器，计划执行时间: {task.scheduled_time}")
            except Exception as e:
                logger.error(f"添加任务 {task.id} 失败，Cron 表达式无效: {e}")
        else:
            # 一次性任务，使用指定时间
            trigger = DateTrigger(run_date=task.scheduled_time)
            job_id = f"task_{task.id}"
        
            self.scheduler.add_job(
                func=execute_task,
                trigger=trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=60
            )
            
            logger.info(f"任务 {task.id} 已添加到调度器，计划执行时间: {task.scheduled_time}")
    
    def remove_task(self, task_id: int, is_recurring: bool = False):
        """
        从调度器中移除任务
        
        Args:
            task_id: 任务ID
            is_recurring: 是否为重复任务
        """
        try:
            job_id = f"recurring_task_{task_id}" if is_recurring else f"task_{task_id}"
            self.scheduler.remove_job(job_id)
            logger.info(f"任务 {task_id} 已从调度器移除")
        except Exception as e:
            logger.warning(f"移除任务 {task_id} 失败: {str(e)}")
    
    def load_pending_tasks(self):
        """
        加载所有待发送的任务到调度器
        """
        with get_db() as db:
            try:
                # 查询所有待发送的任务
                pending_tasks = db.query(NotifyTask).filter(
                    NotifyTask.status == NotifyStatus.PENDING
                ).all()

                logger.info(f"找到 {len(pending_tasks)} 个待发送任务")

                for task in pending_tasks:
                    try:
                        # 验证任务配置：单渠道任务必须有channel，多渠道任务必须有channels_json
                        is_multi_channel = task.channels_json is not None
                        if not is_multi_channel and task.channel is None:
                            logger.warning(f"任务 {task.id} 配置无效（单渠道和多渠道字段都为空），跳过加载")
                            continue
                        
                        # 如果是一次性任务且计划时间已过，跳过
                        if not task.is_recurring and task.scheduled_time < datetime.now():
                            logger.warning(f"任务 {task.id} 计划时间已过，跳过加载")
                            continue

                        # 如果是重复任务且计划时间已过，重新计算下一次执行时间
                        if task.is_recurring and task.cron_expression and task.scheduled_time < datetime.now():
                            try:
                                trigger = get_cron_trigger(task.cron_expression)
                                next_run = trigger.get_next_fire_time(None, datetime.now())
                                if next_run:
                                    task.scheduled_time = next_run
                                    db.commit()
                                    logger.info(f"重复任务 {task.id} 的执行时间已过期，已更新为下一次执行时间: {next_run}")
                            except Exception as e:
                                logger.warning(f"重复任务 {task.id} 更新下一次执行时间失败: {str(e)}")

                        self.add_task(task)
                    except Exception as e:
                        logger.error(f"加载任务 {task.id} 失败: {str(e)}")
                        continue

                logger.info("待发送任务加载完成")

            except Exception as e:
                logger.error(f"加载待发送任务失败: {str(e)}")
    
    def get_scheduled_jobs(self):
        """获取所有已调度的任务"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("通知调度器已关闭")

    def add_external_calendar_sync_job(self):
        """添加外部日历同步定时任务"""
        if not self.scheduler.get_job('sync_external_calendars'):
            self.scheduler.add_job(
                sync_all_external_calendars,
                'interval',
                minutes=15,
                id='sync_external_calendars',
                replace_existing=True,
                coalesce=True,
                max_instances=1
            )
            logger.info("外部日历同步任务已启动 (每15分钟)")


# 全局调度器实例
scheduler = NotifyScheduler()

# --- 外部日历同步逻辑 ---

def parse_ics_content(content):
    """简易 ICS 解析器 (避免引入 heavy 依赖)"""
    events = []
    lines = content.replace('\r\n', '\n').split('\n')
    
    # 处理折行 (line unfolding)
    unfolded_lines = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t'):
            if unfolded_lines:
                unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)
            
    current_event = {}
    in_event = False
    
    for line in unfolded_lines:
        if line == 'BEGIN:VEVENT':
            in_event = True
            current_event = {}
        elif line == 'END:VEVENT':
            in_event = False
            if 'DTSTART' in current_event and 'SUMMARY' in current_event:
                events.append(current_event)
        elif in_event:
            if ':' in line:
                key, val = line.split(':', 1)
                # 处理参数 (如 DTSTART;TZID=...)
                prop_name = key.split(';')[0]
                current_event[prop_name] = val
                
    return events

def parse_ics_date(date_str):
    """解析 ICS 日期字符串"""
    try:
        # 格式: 20230101T120000Z 或 20230101T120000
        clean_str = date_str.replace('Z', '')
        if len(clean_str) == 8: # 仅日期
            return datetime.strptime(clean_str, '%Y%m%d')
        return datetime.strptime(clean_str, '%Y%m%dT%H%M%S')
    except Exception:
        return None

def sync_single_calendar(cal_id):
    """同步单个外部日历"""
    with get_db() as db:
        try:
            cal = db.query(ExternalCalendar).filter(ExternalCalendar.id == cal_id).first()
            if not cal or not cal.is_active:
                return

            logger.info(f"开始同步日历: {cal.name} ({cal.url})")
            
            # 获取默认渠道配置
            channel_config = "{}"
            channel_type = "email" # 默认 fallback
            if cal.channel_id:
                channel = db.query(UserChannel).filter(UserChannel.id == cal.channel_id).first()
                if channel:
                    channel_config = channel.channel_config
                    channel_type = channel.channel_type
            
            # 下载 ICS
            resp = requests.get(cal.url, timeout=30)
            resp.raise_for_status()
            
            events = parse_ics_content(resp.text)
            count = 0
            
            for event in events:
                uid = event.get('UID')
                if not uid:
                    continue
                    
                ext_uid = f"ext-{cal.id}-{uid}"
                summary = event.get('SUMMARY', '无标题')
                desc = event.get('DESCRIPTION', '')
                dt_start_str = event.get('DTSTART')
                
                dt_start = parse_ics_date(dt_start_str)
                if not dt_start or dt_start < datetime.now():
                    continue # 跳过过去的任务
                
                # 检查是否存在
                existing = db.query(NotifyTask).filter(NotifyTask.external_uid == ext_uid).first()
                
                if existing:
                    # 更新
                    if existing.scheduled_time != dt_start or existing.title != summary:
                        existing.scheduled_time = dt_start
                        existing.title = summary
                        existing.content = desc or summary
                        # 如果任务之前已发送或取消，重新激活
                        if existing.status in [NotifyStatus.SENT, NotifyStatus.CANCELLED]:
                            existing.status = NotifyStatus.PENDING
                        scheduler.add_task(existing)
                        count += 1
                else:
                    # 创建新任务
                    new_task = NotifyTask(
                        user_id=cal.user_id,
                        title=summary,
                        content=desc or summary,
                        channel=channel_type,
                        channel_config=channel_config,
                        scheduled_time=dt_start,
                        status=NotifyStatus.PENDING,
                        external_uid=ext_uid,
                        is_recurring=False # 外部日历的重复由外部处理，这里只同步具体事件
                    )
                    db.add(new_task)
                    db.commit() # 提交以获取 ID
                    scheduler.add_task(new_task)
                    count += 1
            
            cal.last_sync = datetime.now()
            db.commit()
            logger.info(f"日历 {cal.name} 同步完成，更新/创建 {count} 个任务")
            
            # 通知前端
            event_manager.announce(cal.user_id, {
                'type': 'calendar_synced',
                'message': f'日历 "{cal.name}" 同步完成'
            })
            
        except Exception as e:
            logger.error(f"同步日历 {cal_id} 失败: {str(e)}")

def sync_all_external_calendars():
    """同步所有活跃的外部日历"""
    with get_db() as db:
        cals = db.query(ExternalCalendar).filter(ExternalCalendar.is_active == True).all()
        for cal in cals:
            # 为每个日历创建一个单独的 job 立即执行，避免阻塞
            scheduler.scheduler.add_job(
                sync_single_calendar,
                args=[cal.id],
                id=f"sync_cal_{cal.id}_auto",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=60
            )
